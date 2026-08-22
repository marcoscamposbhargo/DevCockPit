"""Rotas de Docker.

Leitura é síncrona e degrada com elegância: daemon fora do ar devolve `200`
com `available: false`, nunca erro (NFR-060) — o dashboard precisa continuar
carregando.

Ação é sempre `202` com `job_id`. As rotas de ação são `async def` por
necessidade: enfileirar job exige event loop.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Path, Query

from app.api.deps import get_docker_service, get_project_service
from app.core.errors import NoComposeFile
from app.schemas.docker import (
    ContainerOut,
    DockerActionRequest,
    DockerLogsOut,
    DockerStatusOut,
    PortOut,
)
from app.schemas.job import JobAccepted
from app.services.docker_service import DockerService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects/{project_id}/docker", tags=["docker"])

#: Ações expostas. A tabela é fechada: não existe caminho para `down -v`,
#: `system prune` ou `volume rm` (defesa D6, decisão D-16).
ALLOWED_ACTIONS = ("up", "down", "start", "stop", "restart")


@router.get("/status", response_model=DockerStatusOut)
def docker_status(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    docker: DockerService = Depends(get_docker_service),
) -> DockerStatusOut:
    project = projects.get(project_id)
    status = docker.status(project)

    declared: list[str] = []
    if status.compose_file:
        try:
            declared = docker.declared_services(project, status.compose_file)
        except NoComposeFile:
            declared = []

    return DockerStatusOut(
        available=status.available,
        compose_file=status.compose_file,
        detail=status.detail,
        running_count=status.running_count,
        declared_services=declared,
        containers=[
            ContainerOut(
                name=container.name,
                service=container.service,
                state=container.state,
                image=container.image,
                status=container.status,
                health=container.health,
                exit_code=container.exit_code,
                ports=[
                    PortOut(
                        host_port=port.host_port,
                        container_port=port.container_port,
                        protocol=port.protocol,
                    )
                    for port in container.ports
                ],
            )
            for container in status.containers
        ],
    )


@router.post("/{action}", response_model=JobAccepted, status_code=202)
async def docker_action(
    project_id: str,
    action: str = Path(pattern="^(up|down|start|stop|restart)$"),
    payload: DockerActionRequest = Body(default=DockerActionRequest()),
    projects: ProjectService = Depends(get_project_service),
    docker: DockerService = Depends(get_docker_service),
) -> JobAccepted:
    """Executa uma ação do Compose como job.

    O `pattern` na rota já rejeita qualquer verbo fora do conjunto; o service
    confere de novo contra `COMPOSE_ACTIONS`. Duas barreiras porque esta é a
    superfície mais perigosa da aplicação.
    """
    project = projects.get(project_id)
    job = docker.run_action(project, action, payload.services)
    return JobAccepted(job_id=job.id, action=job.action, status=job.status)


@router.get("/logs", response_model=DockerLogsOut)
def docker_logs(
    project_id: str,
    service: str | None = Query(default=None, max_length=64),
    tail: int = Query(default=200, ge=1, le=2000),
    projects: ProjectService = Depends(get_project_service),
    docker: DockerService = Depends(get_docker_service),
) -> DockerLogsOut:
    project = projects.get(project_id)
    output = docker.logs(project, service, tail)
    lines = [line for line in output.splitlines() if line.strip()]
    return DockerLogsOut(service=service, tail=tail, lines=lines)
