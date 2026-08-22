"""Importação, exportação e comparação do `devcockpit.yml` (US-090, US-091).

Três regras governam este módulo, todas de `docs/08-project-configuration-spec.md`:

1. **O manifesto nunca quebra o projeto.** YAML inválido, versão desconhecida
   ou campo estranho viram aviso; o projeto continua funcionando pelo banco.
2. **Sincronização é sempre ação do usuário.** Nada aqui roda em background.
   Sobrescrita silenciosa de configuração destrói a confiança na ferramenta
   (FR-112).
3. **Exportar é a única escrita do DevCockpit dentro de pasta de projeto**, e
   exige confirmação explícita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.paths import resolve_within_project
from app.detection.detectors.docker_stack import find_compose_file
from app.models.project import (
    ActivityStatus,
    DockerConfig,
    HealthKind,
    Project,
    ProjectTechnology,
    TechnologySource,
)
from app.models.project import (
    ProjectService as ProjectServiceModel,
)
from app.schemas.manifest import (
    MANIFEST_VERSION,
    SUPPORTED_VERSIONS,
    Manifest,
    ManifestDocker,
    ManifestFieldDiff,
    ManifestServiceEntry,
)
from app.services.activity_service import ActivityService

#: Nome canônico primeiro: é o que a exportação escreve.
MANIFEST_FILENAMES = ("devcockpit.yml", "devcockpit.yaml")

#: Categoria das tecnologias que vêm do manifesto. Distingue-as das detectadas
#: na UI sem precisar de outra coluna.
DECLARED_CATEGORY = "declared"

_HEADER = (
    "# devcockpit.yml — manifesto do projeto.\n"
    "# Gerado pelo DevCockpit, versionável e editável à mão.\n"
    "# O DevCockpit funciona sem este arquivo: ele é conveniência, não requisito.\n"
)


@dataclass
class ManifestRead:
    """Resultado tolerante da leitura: nunca levanta por conteúdo do arquivo."""

    exists: bool
    filename: str | None = None
    manifest: Manifest | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.manifest is not None


class ManifestService:
    def __init__(self, session: Session, activity: ActivityService | None = None) -> None:
        self.session = session
        self.activity = activity or ActivityService(session)

    # --- leitura ---

    def locate(self, project: Project) -> Path | None:
        project_dir = Path(project.path)
        for name in MANIFEST_FILENAMES:
            candidate = project_dir / name
            if candidate.is_file():
                return candidate
        return None

    def read(self, project: Project) -> ManifestRead:
        path = self.locate(project)
        if path is None:
            return ManifestRead(exists=False)

        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ManifestRead(
                exists=True,
                filename=path.name,
                warnings=[f"Não foi possível ler o arquivo: {exc.strerror or exc}"],
            )

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            # Regra 1: YAML quebrado é aviso, não erro fatal.
            return ManifestRead(
                exists=True,
                filename=path.name,
                warnings=[f"YAML inválido, arquivo ignorado: {_short(exc)}"],
            )

        if data is None:
            return ManifestRead(
                exists=True, filename=path.name, warnings=["O arquivo está vazio."]
            )
        if not isinstance(data, dict):
            return ManifestRead(
                exists=True,
                filename=path.name,
                warnings=["A raiz do manifesto precisa ser um mapa de chaves."],
            )

        warnings = _unknown_keys_warnings(data)

        version = data.get("version")
        if version not in SUPPORTED_VERSIONS:
            warnings.append(
                f"Versão de schema desconhecida ({version!r}), arquivo ignorado. "
                f"Esta versão do DevCockpit lê: {sorted(SUPPORTED_VERSIONS)}."
            )
            return ManifestRead(exists=True, filename=path.name, warnings=warnings)

        try:
            manifest = Manifest.model_validate(data)
        except Exception as exc:  # noqa: BLE001 — qualquer erro vira aviso, nunca 500
            warnings.append(f"Manifesto inválido, arquivo ignorado: {_short(exc)}")
            return ManifestRead(exists=True, filename=path.name, warnings=warnings)

        if manifest.repository is not None:
            warnings.append(
                "A seção `repository` é informativa: o estado do Git vem sempre do disco."
            )

        return ManifestRead(
            exists=True, filename=path.name, manifest=manifest, warnings=warnings
        )

    # --- importação ---

    def import_into(self, project: Project, read: ManifestRead | None = None) -> list[str]:
        """Aplica o manifesto ao banco e devolve o que mudou, campo a campo.

        Manifesto ausente ou inválido é recusado com `422`: importar é ação
        explícita do usuário, então o silêncio aqui seria enganoso — diferente
        da leitura, que precisa degradar.
        """
        read = read or self.read(project)

        if not read.exists:
            raise ValidationError(
                f"O projeto não tem {MANIFEST_FILENAMES[0]} na raiz.",
            )
        if read.manifest is None:
            raise ValidationError(
                "O manifesto não pôde ser lido. " + " ".join(read.warnings)
            )

        manifest = read.manifest
        applied: list[str] = []

        if manifest.name and manifest.name != project.name:
            project.name = manifest.name
            applied.append("name")

        if manifest.description is not None and manifest.description != project.description:
            project.description = manifest.description
            applied.append("description")

        if manifest.stack:
            novos = self._apply_stack(project, manifest.stack)
            if novos:
                applied.append(f"stack (+{len(novos)})")

        if manifest.docker is not None and self._apply_docker(project, manifest.docker):
            applied.append("docker")

        for key in self._apply_services(project, manifest.services):
            applied.append(f"service:{key}")

        self.activity.record(
            action="manifest.import",
            status=ActivityStatus.SUCCESS,
            project_id=project.id,
            message=(
                f"Manifesto {read.filename} importado. "
                f"Alterados: {', '.join(applied) if applied else 'nada'}."
            ),
        )
        return applied

    def _apply_stack(self, project: Project, stack: list[str]) -> list[str]:
        """Tecnologia declarada entra como `MANUAL` — nova detecção não a apaga.

        O manifesto complementa a detecção; sobrescrevê-la seria contrariar a
        precedência da spec 08, em que a edição do usuário vence sempre.
        """
        existentes = {tech.name.lower() for tech in project.technologies}
        novos: list[str] = []
        for nome in stack:
            if nome.lower() in existentes:
                continue
            project.technologies.append(
                ProjectTechnology(
                    name=nome,
                    category=DECLARED_CATEGORY,
                    source=TechnologySource.MANUAL.value,
                    evidence="devcockpit.yml",
                )
            )
            existentes.add(nome.lower())
            novos.append(nome)
        return novos

    def _apply_docker(self, project: Project, docker: ManifestDocker) -> bool:
        compose_file = docker.compose_file
        if compose_file:
            # Defesa D4: `compose_file` que escape do projeto é recusado aqui,
            # não lá na frente onde já viraria argumento de comando.
            resolve_within_project(Path(project.path), compose_file)

        config = self._docker_config(project)
        antes = (
            (config.enabled, config.compose_file, config.project_name)
            if config is not None
            else None
        )

        if config is None:
            config = DockerConfig(project_id=project.id)
            self.session.add(config)

        config.enabled = docker.enabled
        config.compose_file = compose_file
        config.project_name = docker.project_name
        config.has_dockerfile = (Path(project.path) / "Dockerfile").is_file()

        return antes != (config.enabled, config.compose_file, config.project_name)

    def _apply_services(
        self, project: Project, services: dict[str, ManifestServiceEntry]
    ) -> list[str]:
        """Upsert por chave. Serviço que só existe no banco é preservado.

        Apagar o que o manifesto não menciona seria resolução automática de
        conflito, justamente o que FR-112 proíbe.
        """
        por_chave = {service.key: service for service in project.services}
        alterados: list[str] = []

        for key, entry in services.items():
            desejado = _entry_to_values(key, entry)
            atual = por_chave.get(key)

            if atual is None:
                project.services.append(ProjectServiceModel(key=key, **desejado))
                alterados.append(key)
                continue

            if any(getattr(atual, campo) != valor for campo, valor in desejado.items()):
                for campo, valor in desejado.items():
                    setattr(atual, campo, valor)
                alterados.append(key)

        return alterados

    # --- exportação ---

    def build_document(self, project: Project) -> dict:
        """Monta o manifesto a partir do banco, na ordem em que um humano lê."""
        docker = self._docker_section(project)

        document: dict = {
            "version": MANIFEST_VERSION,
            "name": project.name,
        }
        if project.description:
            document["description"] = project.description

        stack = [tech.name for tech in sorted(project.technologies, key=lambda t: t.name)]
        if stack:
            document["stack"] = stack

        if docker:
            document["docker"] = docker

        services: dict[str, dict] = {}
        for service in sorted(project.services, key=lambda s: s.key):
            entrada: dict = {"label": service.label}
            if service.port:
                entrada["port"] = service.port
            if service.url:
                entrada["url"] = service.url
            if service.health_url:
                entrada["health"] = service.health_url
            entrada["health_kind"] = service.health_kind
            if not service.open_in_browser:
                entrada["open_in_browser"] = False
            services[service.key] = entrada

        if services:
            document["services"] = services

        return document

    def render(self, project: Project) -> str:
        body = yaml.safe_dump(
            self.build_document(project),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        return _HEADER + "\n" + body

    def export(self, project: Project, *, confirm: bool) -> tuple[Path, int, bool]:
        if not confirm:
            raise ValidationError(
                "Escrever devcockpit.yml na pasta do projeto exige confirmação explícita."
            )

        project_dir = Path(project.path)
        if not project_dir.is_dir():
            raise ValidationError(f"O diretório do projeto não existe: {project_dir}")

        # Path fixo, mas resolvido pelo mesmo guarda de sempre: o dia em que o
        # nome virar configurável, a defesa já está no caminho.
        destino = resolve_within_project(project_dir, MANIFEST_FILENAMES[0])
        overwritten = destino.is_file()

        conteudo = self.render(project)
        destino.write_text(conteudo, encoding="utf-8")

        self.activity.record(
            action="manifest.export",
            status=ActivityStatus.SUCCESS,
            project_id=project.id,
            message=(
                f"{'Substituído' if overwritten else 'Criado'} {destino.name} "
                f"em {project_dir.as_posix()}"
            ),
        )
        return destino, len(conteudo.encode("utf-8")), overwritten

    # --- comparação ---

    def compare(
        self, project: Project, read: ManifestRead | None = None
    ) -> list[ManifestFieldDiff]:
        """Diferenças campo a campo, sem alterar nada (FR-112)."""
        read = read or self.read(project)
        if read.manifest is None:
            return []

        manifest = read.manifest
        no_banco = self.build_document(project)
        no_arquivo = manifest.model_dump(exclude_none=True)

        diffs: list[ManifestFieldDiff] = []

        def compara(campo: str, banco: object, arquivo: object) -> None:
            if _norm(banco) != _norm(arquivo):
                diffs.append(
                    ManifestFieldDiff(
                        field=campo, database=_norm(banco), manifest=_norm(arquivo)
                    )
                )

        compara("name", no_banco.get("name"), no_arquivo.get("name"))
        compara("description", no_banco.get("description"), no_arquivo.get("description"))
        compara("stack", sorted(no_banco.get("stack", [])), sorted(manifest.stack))

        docker_banco = no_banco.get("docker") or {}
        docker_arquivo = no_arquivo.get("docker") or {}
        for campo in ("enabled", "compose_file", "project_name"):
            compara(
                f"docker.{campo}", docker_banco.get(campo), docker_arquivo.get(campo)
            )

        servicos_banco: dict[str, dict] = no_banco.get("services", {})
        for key in sorted(set(servicos_banco) | set(manifest.services)):
            do_banco = servicos_banco.get(key)
            do_arquivo = (
                _entry_document(manifest.services[key]) if key in manifest.services else None
            )
            compara(f"services.{key}", do_banco, do_arquivo)

        return diffs

    # --- apoio ---

    def _docker_config(self, project: Project) -> DockerConfig | None:
        return self.session.execute(
            select(DockerConfig).where(DockerConfig.project_id == project.id)
        ).scalar_one_or_none()

    def _docker_section(self, project: Project) -> dict | None:
        config = self._docker_config(project)
        if config is not None:
            secao: dict = {"enabled": config.enabled}
            if config.compose_file:
                secao["compose_file"] = config.compose_file
            if config.project_name:
                secao["project_name"] = config.project_name
            return secao

        # Sem linha no banco, o disco responde: exportar um projeto com Compose
        # sem a seção `docker` produziria um manifesto incompleto.
        encontrado = find_compose_file(Path(project.path))
        if encontrado is None:
            return None
        return {"enabled": True, "compose_file": encontrado.name}


def _entry_to_values(key: str, entry: ManifestServiceEntry) -> dict:
    """Converte a entrada do manifesto nos campos do modelo."""
    health_kind = entry.health_kind
    if health_kind is None:
        if entry.health:
            health_kind = HealthKind.HTTP
        elif entry.port:
            health_kind = HealthKind.TCP
        else:
            health_kind = HealthKind.NONE

    return {
        "label": entry.label or key.replace("_", " ").replace("-", " ").title(),
        "host": "localhost",
        "port": entry.port,
        "url": entry.url,
        "health_url": entry.health,
        "health_kind": health_kind.value,
        "open_in_browser": entry.open_in_browser,
    }


def _entry_document(entry: ManifestServiceEntry) -> dict:
    """Mesma forma que `build_document` produz, para a comparação bater."""
    values = _entry_to_values("", entry)
    documento: dict = {"label": entry.label or values["label"]}
    if values["port"]:
        documento["port"] = values["port"]
    if values["url"]:
        documento["url"] = values["url"]
    if values["health_url"]:
        documento["health"] = values["health_url"]
    documento["health_kind"] = values["health_kind"]
    if not values["open_in_browser"]:
        documento["open_in_browser"] = False
    return documento


def _norm(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or None
    if isinstance(value, dict):
        return ", ".join(f"{k}={_norm(v)}" for k, v in sorted(value.items())) or None
    return str(value)


def _unknown_keys_warnings(data: dict) -> list[str]:
    conhecidas = set(Manifest.model_fields)
    desconhecidas = sorted(str(key) for key in data if str(key) not in conhecidas)
    if not desconhecidas:
        return []
    return [f"Campos desconhecidos ignorados: {', '.join(desconhecidas)}."]


def _short(exc: object, limit: int = 200) -> str:
    texto = " ".join(str(exc).split())
    return texto if len(texto) <= limit else texto[:limit] + "…"
