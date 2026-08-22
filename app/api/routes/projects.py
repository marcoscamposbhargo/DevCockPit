"""Rotas de projeto.

Esta camada valida payload, chama o service e devolve schema. Não conhece
`subprocess`, path de sistema operacional nem sintaxe de comando (NFR-020).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import get_dev_server_service, get_project_service
from app.models.project import Project
from app.schemas.git import DetectionResult
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectList,
    ProjectSummary,
    ProjectUpdate,
)
from app.services.dev_server_service import DevServerService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _to_summary(
    project: Project,
    *,
    can_start: bool = False,
    app_running: bool | None = None,
) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        path=project.path,
        status=project.status,  # type: ignore[arg-type]
        is_pinned=project.is_pinned,
        technologies=[tech.name for tech in project.technologies],
        services_total=len(project.services),
        last_accessed_at=project.last_accessed_at,
        can_start=can_start,
        app_running=app_running,
    )


@router.get("", response_model=ProjectList)
def list_projects(
    service: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
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

    # Uma consulta só para todos os projetos, não uma por card. A lista não
    # pode disparar trabalho por projeto (NFR-010), e ler a tabela inteira de
    # servidores é mais barato que ler uma linha sete vezes.
    rodando = {registro.project_id for registro in servers.running_project_ids()}

    return ProjectList(
        items=[
            _to_summary(p, **_capacidades(p, servers, rodando))
            for p in projects
        ],
        total=total,
    )


def _capacidades(project: Project, servers, rodando: set[str]) -> dict:  # type: ignore[no-untyped-def]
    """O que o painel sabe fazer com este projeto, e em que estado ele está.

    Leitura de disco pequena e local — os mesmos arquivos que a detecção já lê,
    e da mesma ordem de custo que o `is_dir()` que a listagem já faz por
    projeto. Nada de rede, nada de subprocess (NFR-010).
    """
    tem_app = servers.plan(project) is not None

    return {
        "can_start": tem_app or _has_compose(project),
        # `None` de propósito quando não há aplicação separada: ver o comentário
        # do campo em `ProjectSummary`.
        "app_running": (project.id in rodando) if tem_app else None,
    }


def _has_compose(project: Project) -> bool:
    from pathlib import Path

    from app.detection.detectors.docker_stack import find_compose_file

    diretorio = Path(project.path)
    return diretorio.is_dir() and find_compose_file(diretorio) is not None


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
