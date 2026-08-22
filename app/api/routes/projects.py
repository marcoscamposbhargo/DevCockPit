"""Rotas de projeto.

Esta camada valida payload, chama o service e devolve schema. Não conhece
`subprocess`, path de sistema operacional nem sintaxe de comando (NFR-020).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import get_project_service
from app.models.project import Project
from app.schemas.git import DetectionResult
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectList,
    ProjectSummary,
    ProjectUpdate,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _to_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        path=project.path,
        status=project.status,  # type: ignore[arg-type]
        is_pinned=project.is_pinned,
        technologies=[tech.name for tech in project.technologies],
        services_total=len(project.services),
        last_accessed_at=project.last_accessed_at,
    )


@router.get("", response_model=ProjectList)
def list_projects(
    service: ProjectService = Depends(get_project_service),
    status_filter: str | None = Query(default=None, alias="status"),
    tech: str | None = Query(default=None),
    pinned: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ProjectList:
    projects, total = service.list(
        status=status_filter, tech=tech, pinned=pinned, query=q, limit=limit, offset=offset
    )
    return ProjectList(items=[_to_summary(p) for p in projects], total=total)


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return service.create(payload)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return service.get(project_id, touch=True)


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return service.update(project_id, payload)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> Response:
    service.delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/detect", response_model=DetectionResult)
def detect_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> DetectionResult:
    """Reexecuta a detecção. Respeita `detection_locked` (FR-024, FR-025)."""
    diff = service.detect(project_id)
    return DetectionResult(
        skipped=diff.skipped,
        added=diff.added,
        removed=diff.removed,
        kept_manual=diff.kept_manual,
        services_added=diff.services_added,
        compose_file=diff.compose_file,
        warnings=diff.warnings,
    )
