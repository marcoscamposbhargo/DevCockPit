"""Rotas de serviços, health check e ações de sistema operacional."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_health_service,
    get_project_service,
    get_system_service,
)
from app.models.project import ProjectService as ProjectServiceModel
from app.schemas.health import (
    OpenBrowserRequest,
    OpenResult,
    PortMap,
    PortUsage,
    ServiceList,
    ServicesReplace,
    ServiceStateOut,
)
from app.services.health_service import HealthService, targets_from_project
from app.services.project_service import ProjectService
from app.services.system_action_service import SystemActionService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["services"])
global_router = APIRouter(prefix="/api/services", tags=["services"])


def _to_out(service, resultado) -> ServiceStateOut:  # type: ignore[no-untyped-def]
    return ServiceStateOut(
        key=service.key,
        label=service.label,
        host=service.host,
        port=service.port,
        url=service.url,
        health_kind=service.health_kind,
        state=resultado.state.value,
        latency_ms=resultado.latency_ms,
        detail=resultado.detail,
        checked_at=resultado.checked_at,
    )


@router.get("/services", response_model=ServiceList)
def list_services(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    health: HealthService = Depends(get_health_service),
) -> ServiceList:
    """Serviços com o **último estado conhecido**, sempre de cache.

    Verificar aqui transformaria cada carga de tela em N conexões (NFR-011).
    """
    project = projects.get(project_id)
    return ServiceList(
        items=[
            _to_out(service, health.last_known(project.id, service.key))
            for service in project.services
        ]
    )


@router.put("/services", response_model=ServiceList)
def replace_services(
    project_id: str,
    payload: ServicesReplace,
    projects: ProjectService = Depends(get_project_service),
    health: HealthService = Depends(get_health_service),
) -> ServiceList:
    project = projects.get(project_id)

    project.services.clear()
    for item in payload.items:
        project.services.append(
            ProjectServiceModel(
                key=item.key,
                label=item.label,
                host=item.host,
                port=item.port,
                url=item.url,
                health_url=item.health_url,
                health_kind=item.health_kind.value,
                open_in_browser=item.open_in_browser,
            )
        )

    health.invalidate(project.id)

    return ServiceList(
        items=[
            _to_out(service, health.last_known(project.id, service.key))
            for service in project.services
        ]
    )


@router.post("/services/check", response_model=ServiceList)
async def check_services(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    health: HealthService = Depends(get_health_service),
) -> ServiceList:
    """Reverificação sob demanda (FR-063). Único caminho que verifica na hora."""
    project = projects.get(project_id)
    await health.check_many(targets_from_project(project))

    return ServiceList(
        items=[
            _to_out(service, health.last_known(project.id, service.key))
            for service in project.services
        ]
    )


# --- ações de sistema operacional ---


@router.post("/open/vscode", response_model=OpenResult)
def open_vscode(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    system: SystemActionService = Depends(get_system_service),
) -> OpenResult:
    system.open_in_editor(projects.get(project_id, touch=True))
    return OpenResult(opened=True, action="system.vscode")


@router.post("/open/folder", response_model=OpenResult)
def open_folder(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    system: SystemActionService = Depends(get_system_service),
) -> OpenResult:
    system.open_folder(projects.get(project_id, touch=True))
    return OpenResult(opened=True, action="system.folder")


@router.post("/open/terminal", response_model=OpenResult)
def open_terminal(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    system: SystemActionService = Depends(get_system_service),
) -> OpenResult:
    system.open_terminal(projects.get(project_id, touch=True))
    return OpenResult(opened=True, action="system.terminal")


@router.post("/open/browser", response_model=OpenResult)
def open_browser(
    project_id: str,
    payload: OpenBrowserRequest,
    projects: ProjectService = Depends(get_project_service),
    system: SystemActionService = Depends(get_system_service),
) -> OpenResult:
    project = projects.get(project_id, touch=True)
    url = system.open_service_url(project, payload.service_key)
    return OpenResult(opened=True, action="system.browser", detail=url)


# --- mapa de portas ---


@global_router.get("/ports", response_model=PortMap)
def port_map(projects: ProjectService = Depends(get_project_service)) -> PortMap:
    todos, _ = projects.list(limit=500)

    por_porta: dict[int, set[str]] = defaultdict(set)
    for project in todos:
        for service in project.services:
            if service.port:
                por_porta[service.port].add(project.name)

    items = [
        PortUsage(port=porta, projects=sorted(nomes), conflict=len(nomes) > 1)
        for porta, nomes in sorted(por_porta.items())
    ]
    return PortMap(items=items, conflicts=sum(1 for item in items if item.conflict))
