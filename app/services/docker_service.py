"""Casos de uso de Docker (FR-050 a FR-057).

Leitura é síncrona e cacheada; ação é sempre job (ADR-006). A fronteira entre
as duas coisas é o que mantém a UI responsiva enquanto um `compose up` de dois
minutos acontece.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.docker.adapter import COMPOSE_ACTIONS, DockerAdapter
from app.adapters.docker.models import ComposeStatus
from app.core.cache import TTLCache
from app.core.errors import (
    ActionNotAllowed,
    DockerUnavailable,
    NoComposeFile,
    ProjectDirMissing,
    ValidationError,
)
from app.core.paths import resolve_within_project
from app.detection.detectors.docker_stack import COMPOSE_FILENAMES, find_compose_relativo
from app.jobs.job import Job
from app.jobs.job_manager import JobManager
from app.models.project import DockerConfig, Project


class DockerService:
    def __init__(
        self,
        adapter: DockerAdapter,
        cache: TTLCache,
        jobs: JobManager,
        timeouts: dict[str, float] | None = None,
        session: Session | None = None,
    ) -> None:
        self.adapter = adapter
        self.cache = cache
        self.jobs = jobs
        self.timeouts = timeouts or {}
        self.session = session

    def configured_compose_file(self, project: Project) -> str | None:
        """O `compose_file` que o manifesto gravou em `docker_config`.

        Sem esta leitura o campo era escrito pelo import do `devcockpit.yml` e
        nunca lido: um projeto com dois arquivos Compose subia sempre o que a
        detecção escolhia, ignorando o que o manifesto declarava.
        """
        if self.session is None:
            return None
        config = self.session.execute(
            select(DockerConfig).where(DockerConfig.project_id == project.id)
        ).scalar_one_or_none()
        return config.compose_file if config is not None else None

    # --- resolução do arquivo Compose ---

    def _project_dir(self, project: Project) -> Path:
        project_dir = Path(project.path)
        if not project_dir.is_dir():
            raise ProjectDirMissing(f"O diretório {project.path} não existe mais.")
        return project_dir

    def compose_file_for(self, project: Project, configured: str | None = None) -> str:
        """Devolve o nome do arquivo Compose, relativo ao projeto.

        Configurado vence a detecção, mas passa por `resolve_within_project`:
        um `compose_file` que escape do diretório é recusado (defesa D4).
        """
        project_dir = self._project_dir(project)
        configured = configured or self.configured_compose_file(project)

        if configured:
            resolved = resolve_within_project(project_dir, configured)
            if not resolved.is_file():
                raise NoComposeFile(f"Arquivo Compose não encontrado: {configured}")
            return configured

        found = find_compose_relativo(project_dir)
        if found is None:
            raise NoComposeFile(
                "Nenhum arquivo Compose encontrado na raiz nem nas subpastas de "
                "projeto. Procurados: " + ", ".join(COMPOSE_FILENAMES)
            )
        return found

    def declared_services(self, project: Project, compose_file: str) -> list[str]:
        """Serviços declarados no Compose — o conjunto fechado que valida a entrada.

        É isto que impede um nome de serviço vindo do cliente de virar argumento
        arbitrário de comando (defesa D2).
        """
        project_dir = self._project_dir(project)
        path = resolve_within_project(project_dir, compose_file)

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        except (yaml.YAMLError, OSError):
            return []

        services = data.get("services")
        return sorted(str(name) for name in services) if isinstance(services, dict) else []

    # --- leitura ---

    def status(self, project: Project, configured: str | None = None) -> ComposeStatus:
        key = f"docker.status:{project.id}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        try:
            compose_file = self.compose_file_for(project, configured)
        except NoComposeFile as exc:
            status = ComposeStatus(available=True, compose_file=None, detail=exc.message)
            self.cache.set(key, status)
            return status

        status = self.adapter.status(self._project_dir(project), compose_file)
        self.cache.set(key, status)
        return status

    def logs(
        self,
        project: Project,
        service: str | None,
        tail: int,
        configured: str | None = None,
    ) -> str:
        compose_file = self.compose_file_for(project, configured)
        validated = self._validate_services(project, compose_file, [service] if service else [])

        ok, output = self.adapter.logs(
            self._project_dir(project),
            compose_file,
            validated[0] if validated else None,
            tail=tail,
        )
        if not ok:
            raise DockerUnavailable(output)
        return output

    # --- ações (sempre job) ---

    def run_action(
        self,
        project: Project,
        action: str,
        services: list[str] | None = None,
        configured: str | None = None,
    ) -> Job:
        if action not in COMPOSE_ACTIONS:
            raise ActionNotAllowed(f"Ação Docker não permitida: {action!r}")

        compose_file = self.compose_file_for(project, configured)
        validated = self._validate_services(project, compose_file, services or [])

        timeout = self.timeouts.get(action) or self.timeouts.get("default") or 120.0
        spec = self.adapter.action_spec(
            self._project_dir(project),
            compose_file,
            action,
            validated,
            timeout_s=timeout,
        )

        self.cache.invalidate(f"docker.status:{project.id}")

        # A chave é por projeto: dois `up` no mesmo projeto não coexistem, mas
        # projetos diferentes sobem em paralelo (FR-057).
        return self.jobs.submit(
            spec,
            key=f"docker:{project.id}",
            action=f"docker.{action}",
            project_id=project.id,
        )

    def _validate_services(
        self,
        project: Project,
        compose_file: str,
        services: list[str],
    ) -> list[str]:
        if not services:
            return []

        declared = set(self.declared_services(project, compose_file))
        if not declared:
            raise ValidationError(
                "Não foi possível ler os serviços do arquivo Compose para validar o pedido."
            )

        unknown = [name for name in services if name not in declared]
        if unknown:
            raise ValidationError(
                f"Serviço(s) inexistente(s) no Compose: {', '.join(sorted(unknown))}. "
                f"Disponíveis: {', '.join(sorted(declared))}."
            )
        return list(services)

    def invalidate(self, project_id: str) -> None:
        self.cache.invalidate(f"docker.status:{project_id}")
