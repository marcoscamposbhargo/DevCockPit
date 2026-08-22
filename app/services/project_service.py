"""Casos de uso de projeto (FR-001 a FR-008)."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProjectAlreadyExists, ProjectNotFound, ValidationError
from app.core.paths import validate_project_dir
from app.models.project import (
    ActivityStatus,
    DevServer,
    Project,
    ProjectStatus,
)
from app.repositories.project_repository import ProjectRepository
from app.runner.background import stop_background
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.activity_service import ActivityService
from app.services.detection_service import DetectionDiff, DetectionService
from app.services.manifest_service import ManifestService

logger = logging.getLogger(__name__)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_only.lower()).strip("-")
    return slug or "projeto"


class ProjectService:
    def __init__(
        self,
        session: Session,
        allowed_roots: list[Path],
        activity: ActivityService | None = None,
        detection: DetectionService | None = None,
        manifests: ManifestService | None = None,
    ) -> None:
        self.session = session
        self.repo = ProjectRepository(session)
        self.allowed_roots = allowed_roots
        self.activity = activity or ActivityService(session)
        self.detection = detection or DetectionService(session, activity=self.activity)
        self.manifests = manifests or ManifestService(session, activity=self.activity)

    # --- criação ---

    def create(self, payload: ProjectCreate) -> Project:
        resolved = validate_project_dir(payload.path, self.allowed_roots)
        stored_path = resolved.as_posix()

        if self.repo.get_by_path(stored_path) is not None:
            raise ProjectAlreadyExists(f"O diretório {stored_path} já está cadastrado.")

        name = (payload.name or resolved.name).strip()
        if not name:
            raise ValidationError("O nome do projeto não pode ser vazio.")

        project = Project(
            id=self._unique_id(name),
            name=name,
            description=payload.description,
            path=stored_path,
            status=ProjectStatus.REGISTERED.value,
        )
        self.repo.add(project)

        if payload.run_detection:
            # Mesma política do manifesto logo abaixo: quem acabou de apontar
            # uma pasta quer o projeto na lista. Detecção que falha vira
            # projeto sem stack — que a tela oferece redetectar num clique —,
            # nunca um cadastro recusado.
            try:
                self.detection.run_for(project, record=False)
            except Exception:  # noqa: BLE001 - detecção não bloqueia cadastro
                logger.exception(
                    "detecção falhou no cadastro",
                    extra={"extra_fields": {"project_id": project.id, "path": stored_path}},
                )
            self.session.flush()

        if payload.import_manifest:
            # Manifesto ausente ou inválido não impede o cadastro: quem acabou
            # de apontar uma pasta quer o projeto na lista, não uma recusa.
            read = self.manifests.read(project)
            if read.valid:
                self.manifests.import_into(project, read)
                self.session.flush()

        self.activity.record(
            action="project.create",
            status=ActivityStatus.SUCCESS,
            project_id=project.id,
            message=f"Projeto cadastrado em {stored_path}",
        )
        return project

    def detect(self, project_id: str) -> DetectionDiff:
        project = self.get(project_id)
        return self.detection.run_for(project)

    def _unique_id(self, name: str) -> str:
        base = slugify(name)
        candidate = base
        suffix = 2
        while self.repo.id_exists(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    # --- leitura ---

    def get(self, project_id: str, *, touch: bool = False) -> Project:
        project = self.repo.get(project_id)
        if project is None:
            raise ProjectNotFound(f"Projeto {project_id!r} não encontrado.")
        if touch:
            self.repo.touch_access(project)
        self._refresh_missing_status(project)
        return project

    def list(
        self,
        *,
        status: str | None = None,
        tech: str | None = None,
        pinned: bool | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        projects, total = self.repo.list(
            status=status, tech=tech, pinned=pinned, query=query, limit=limit, offset=offset
        )
        for project in projects:
            self._refresh_missing_status(project)
        return projects, total

    # --- atualização e remoção ---

    def update(self, project_id: str, payload: ProjectUpdate) -> Project:
        project = self.get(project_id)
        data = payload.model_dump(exclude_unset=True)

        for field, value in data.items():
            setattr(project, field, value)

        self.activity.record(
            action="project.update",
            status=ActivityStatus.SUCCESS,
            project_id=project.id,
            message=f"Campos alterados: {', '.join(sorted(data)) or 'nenhum'}",
        )
        return project

    def delete(self, project_id: str) -> None:
        project = self.get(project_id)
        path = project.path

        # O servidor de desenvolvimento sobrevive ao painel de propósito, e a
        # linha em `dev_server` é o único lugar onde o PID dele existe. Apagar
        # o projeto sem parar o processo apagava justamente esse PID: sobrava
        # um `uvicorn` de pé que só o Gerenciador de Tarefas alcança, ocupando
        # a porta e sem nenhum caminho de volta pela interface.
        #
        # Remover é o momento certo para parar: quem tira o projeto do painel
        # não vai voltar para desligá-lo depois.
        parado = self._stop_dev_server(project)

        self.repo.delete(project)

        detalhe = f"Registro removido. O diretório {path} não foi tocado."
        if parado:
            detalhe += f" O servidor de desenvolvimento (pid {parado}) foi encerrado junto."

        self.activity.record(
            action="project.delete",
            status=ActivityStatus.SUCCESS,
            project_id=project_id,
            message=detalhe,
        )

    def _stop_dev_server(self, project: Project) -> int | None:
        """Encerra o servidor do projeto, se houver. Devolve o PID encerrado.

        Falha em encerrar não impede a remoção: o registro sai de qualquer
        forma, e o que aconteceu fica na auditoria. Travar a remoção por causa
        de um processo teimoso deixaria o usuário com um projeto que ele não
        consegue tirar da tela.
        """
        registro = self.session.execute(
            select(DevServer).where(DevServer.project_id == project.id)
        ).scalar_one_or_none()
        if registro is None:
            return None

        pid = registro.pid
        try:
            encerrado = stop_background(pid)
        except Exception:  # noqa: BLE001 - remoção não pode falhar por isto
            logger.exception(
                "falha ao encerrar o servidor durante a remoção",
                extra={"extra_fields": {"project_id": project.id, "pid": pid}},
            )
            encerrado = False

        if not encerrado:
            self.activity.record(
                action="server.stop",
                status=ActivityStatus.FAILED,
                project_id=project.id,
                message=f"pid {pid} não encerrou durante a remoção do projeto.",
            )
            return None

        return pid

    # --- estado observado ---

    def _refresh_missing_status(self, project: Project) -> None:
        """NFR-062: diretório sumiu vira MISSING, sem quebrar nada em cascata."""
        exists = Path(project.path).is_dir()
        if not exists and project.status != ProjectStatus.MISSING.value:
            project.status = ProjectStatus.MISSING.value
        elif exists and project.status == ProjectStatus.MISSING.value:
            project.status = ProjectStatus.STOPPED.value
