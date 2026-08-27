"""Aplica a detecção ao projeto cadastrado (FR-020, FR-024, FR-025).

Regra que define o comportamento: **edição manual do usuário vence sempre**.
Uma nova detecção substitui apenas linhas `DETECTED`; o que o usuário marcou
como `MANUAL` nunca é desfeito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.detection.registry import DetectionRegistry
from app.models.project import (
    ActivityStatus,
    Project,
    ProjectTechnology,
    TechnologySource,
)
from app.models.project import (
    ProjectService as ProjectServiceModel,
)
from app.services.activity_service import ActivityService


@dataclass
class PortDrift:
    """O arquivo do projeto diz uma porta; o cadastro diz outra.

    Não é erro de ninguém: o `.env` muda, o Compose muda, e o cadastro fica
    onde estava. Vira problema quando o painel passa a verificar um número que
    o projeto abandonou — o serviço aparece offline para sempre, e o motivo não
    está em lugar nenhum da tela.
    """

    key: str
    label: str
    declared: int
    detected: int


@dataclass
class DetectionDiff:
    added: list[str]
    removed: list[str]
    kept_manual: list[str]
    services_added: list[str]
    compose_file: str | None
    warnings: list[str]
    skipped: bool = False
    #: Serviços já cadastrados cuja porta não bate com a do arquivo. Só
    #: relatados — a decisão de adotar é de quem conhece o projeto.
    port_drift: list[PortDrift] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.services_added)


class DetectionService:
    def __init__(
        self,
        session: Session,
        registry: DetectionRegistry | None = None,
        activity: ActivityService | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or DetectionRegistry()
        self.activity = activity or ActivityService(session)

    def run_for(self, project: Project, *, record: bool = True) -> DetectionDiff:
        if project.detection_locked:
            diff = DetectionDiff([], [], [], [], None, [], skipped=True)
            if record:
                self.activity.record(
                    action="project.detect",
                    status=ActivityStatus.SUCCESS,
                    project_id=project.id,
                    message="Detecção ignorada: o projeto está com a stack travada.",
                )
            return diff

        detection = self.registry.run(Path(project.path))

        manual = {
            tech.name: tech
            for tech in project.technologies
            if tech.source == TechnologySource.MANUAL.value
        }
        previous_detected = {
            tech.name: tech
            for tech in project.technologies
            if tech.source == TechnologySource.DETECTED.value
        }
        found = {tech.name: tech for tech in detection.technologies}

        for name, tech in previous_detected.items():
            if name not in found:
                project.technologies.remove(tech)
                self.session.delete(tech)

        added: list[str] = []
        for name, tech in found.items():
            if name in manual or name in previous_detected:
                continue
            project.technologies.append(
                ProjectTechnology(
                    name=name,
                    category=tech.category,
                    source=TechnologySource.DETECTED.value,
                    evidence=tech.evidence,
                )
            )
            added.append(name)

        services_added, port_drift, ignorados = self._apply_services(project, detection.services)

        diff = DetectionDiff(
            added=sorted(added),
            removed=sorted(name for name in previous_detected if name not in found),
            kept_manual=sorted(manual),
            services_added=sorted(services_added),
            compose_file=detection.compose_file,
            warnings=[
                *detection.warnings,
                *(
                    [f"Serviço não cadastrado, porta já ocupada: {', '.join(ignorados)}."]
                    if ignorados
                    else []
                ),
            ],
            port_drift=port_drift,
        )

        if record:
            self.activity.record(
                action="project.detect",
                status=ActivityStatus.SUCCESS,
                project_id=project.id,
                message=_summary(diff),
            )
        return diff

    def _apply_services(
        self, project: Project, suggestions: list
    ) -> tuple[list[str], list[PortDrift], list[str]]:
        """Só adiciona serviço que ainda não existe. Nunca sobrescreve o do usuário.

        Nunca sobrescrever é a regra certa e continua valendo. O que faltava era
        o outro lado dela: **não sobrescrever não é motivo para não contar**.

        Um serviço já cadastrado cuja porta mudou no arquivo do projeto era
        ignorado em silêncio. A detecção respondia "nada mudou" e o painel
        seguia verificando um número que o projeto já tinha abandonado — o
        serviço aparecia offline indefinidamente, sem que tela nenhuma tivesse
        como dizer por quê. Foi o caso da PLATAFORMA: o `.env` diz
        `POSTGRES_PORT=5434`, o cadastro dizia 5433, e rodar a detecção não
        adiantava nada.
        """
        por_chave = {service.key: service for service in project.services}
        existing = set(por_chave)
        # Uma porta tem um ouvinte só, e a rota de edição já recusa duplicata
        # desde a sessão passada. A detecção entrava pela outra porta da mesma
        # casa: sugestão com chave nova e porta ocupada criava o estado que a
        # API proíbe — `postgres 5442` ao lado de `servico-5442`, os dois na
        # mesma porta, e a tela acusando inconsistência que o painel gravou.
        por_porta = {s.port: s for s in project.services if s.port}
        added: list[str] = []
        drift: list[PortDrift] = []
        ignorados: list[str] = []

        for suggestion in suggestions:
            if suggestion.key in existing:
                atual = por_chave[suggestion.key]
                # Só porta lida de arquivo contradiz o cadastro. A porta
                # convencional do framework não sabe nada sobre este projeto:
                # acusar "o padrão do uvicorn é 8000" contra um serviço
                # cadastrado em 3001 transformaria toda porta escolhida a mão
                # num alerta permanente — foi o que aconteceu na primeira
                # versão desta checagem, que acusou os três projetos de uma vez.
                if (
                    suggestion.port_source == "file"
                    and suggestion.port
                    and atual.port
                    and suggestion.port != atual.port
                ):
                    drift.append(
                        PortDrift(
                            key=atual.key,
                            label=atual.label,
                            declared=atual.port,
                            detected=suggestion.port,
                        )
                    )
                continue

            if suggestion.port and suggestion.port in por_porta:
                # Quase sempre é o mesmo serviço com outro nome: o painel
                # cadastrou `servico-5442` a partir de uma porta observada, e o
                # Compose chama de `postgres`. Renomear seria decidir sozinho;
                # duplicar seria mentir. Fica de fora, e o resumo diz por quê.
                dono = por_porta[suggestion.port]
                ignorados.append(
                    f"{suggestion.key} (porta {suggestion.port} já é de '{dono.key}')"
                )
                continue

            project.services.append(
                ProjectServiceModel(
                    key=suggestion.key,
                    label=suggestion.label,
                    port=suggestion.port,
                    url=suggestion.url,
                    health_url=suggestion.url if suggestion.health_kind == "HTTP" else None,
                    health_kind=suggestion.health_kind,
                )
            )
            existing.add(suggestion.key)
            if suggestion.port:
                por_porta[suggestion.port] = project.services[-1]
            added.append(suggestion.key)

        return added, drift, ignorados


def _summary(diff: DetectionDiff) -> str:
    if not diff.changed and not diff.port_drift:
        return "Detecção executada; nada mudou."
    parts = []
    if diff.port_drift:
        # No registro de atividade, e não só na resposta: quem for entender
        # depois por que o serviço vivia offline precisa achar isso no histórico.
        parts.append(
            f"{len(diff.port_drift)} porta(s) divergindo do arquivo: "
            + ", ".join(f"{d.key} {d.declared}->{d.detected}" for d in diff.port_drift)
        )
    if diff.added:
        parts.append(f"+{len(diff.added)} tecnologia(s): {', '.join(diff.added)}")
    if diff.removed:
        parts.append(f"-{len(diff.removed)}: {', '.join(diff.removed)}")
    if diff.services_added:
        parts.append(f"+{len(diff.services_added)} serviço(s)")
    return "; ".join(parts)
