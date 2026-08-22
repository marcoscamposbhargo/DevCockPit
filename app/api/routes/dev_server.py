"""Rotas do servidor de desenvolvimento do projeto.

Diferente das rotas de Docker, aqui não há job: subir um servidor de
desenvolvimento é instantâneo do ponto de vista do painel — o processo nasce e a
requisição acaba. O que demora é o servidor ficar pronto, e quem responde isso é
o verificador de porta, não esta rota.

O cliente manda o id do projeto e mais nada. Não existe campo de comando na
requisição; o comando sai do `devcockpit.yml` ou da detecção, e passa pelas
guardas de `app/services/run_plan.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_dev_server_service, get_project_service
from app.schemas.health import DevServerLogs, DevServerOut
from app.services.dev_server_service import DevServerService, DevServerState
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects/{project_id}/server", tags=["server"])


def _to_out(estado: DevServerState) -> DevServerOut:
    return DevServerOut(
        running=estado.running,
        pid=estado.pid,
        command=estado.command,
        source=estado.source,
        evidence=estado.evidence,
        started_at=estado.started_at,
        can_start=estado.can_start,
    )


@router.get("", response_model=DevServerOut)
def server_status(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerOut:
    return _to_out(servers.status(projects.get(project_id)))


@router.post("/start", response_model=DevServerOut)
def server_start(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerOut:
    return _to_out(servers.start(projects.get(project_id, touch=True)))


@router.post("/stop", response_model=DevServerOut)
def server_stop(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerOut:
    return _to_out(servers.stop(projects.get(project_id)))


@router.get("/logs", response_model=DevServerLogs)
def server_logs(
    project_id: str,
    lines: int = Query(default=200, ge=1, le=2000),
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerLogs:
    project = projects.get(project_id)
    return DevServerLogs(lines=servers.logs(project, lines=lines))
