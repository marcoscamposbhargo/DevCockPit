"""Casos de uso de projeto (FR-001 a FR-008)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import ProjectAlreadyExists, ProjectNotFound, ValidationError
from app.core.paths import validate_project_dir
from app.models.project import (
    ActivityStatus,
    Project,
    ProjectStatus,
)
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.activity_service import ActivityService
from app.services.detection_service import DetectionDiff, DetectionService
from app.services.manifest_service import ManifestService

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
            self.detection.run_for(project, record=False)
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
        self.repo.delete(project)
        self.activity.record(
            action="project.delete",
            status=ActivityStatus.SUCCESS,
            project_id=project_id,
            message=f"Registro removido. O diretório {path} não foi tocado.",
        )

    # --- estado observado ---

    def _refresh_missing_status(self, project: Project) -> None:
        """NFR-062: diretório sumiu vira MISSING, sem quebrar nada em cascata."""
        exists = Path(project.path).is_dir()
        if not exists and project.status != ProjectStatus.MISSING.value:
            project.status = ProjectStatus.MISSING.value
        elif exists and project.status == ProjectStatus.MISSING.value:
            project.status = ProjectStatus.STOPPED.value
