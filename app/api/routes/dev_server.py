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
from app.schemas.health import (
    DevServerLogs,
    DevServerOut,
    RunningServerList,
    RunningServerOut,
)
from app.services.dev_server_service import DevServerService, DevServerState
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects/{project_id}/server", tags=["server"])
#: Visão de todos os servidores de uma vez. Sem ela, saber o que está rodando
#: exige abrir projeto por projeto — e no fim do dia, lembrar quais foram.
global_router = APIRouter(prefix="/api/servers", tags=["server"])


@global_router.get("", response_model=RunningServerList)
def running_servers(
    servers: DevServerService = Depends(get_dev_server_service),
    projects: ProjectService = Depends(get_project_service),
) -> RunningServerList:
    """Todos os servidores de desenvolvimento no ar agora.

    Uma consulta só, e registro de processo morto é descartado no caminho —
    quem abre esta tela depois de um `Ctrl+C` no console do servidor não pode
    ver um processo que já não existe.
    """
    cadastrados, _total = projects.list(limit=500)
    nomes = {project.id: project.name for project in cadastrados}

    return RunningServerList(
        items=[
            RunningServerOut(
                project_id=registro.project_id,
                project_name=nomes.get(registro.project_id, registro.project_id),
                pid=registro.pid,
                command=registro.command,
                started_at=registro.started_at,
            )
            for registro in servers.running_project_ids()
        ]
    )


def _to_out(estado: DevServerState) -> DevServerOut:
    return DevServerOut(
        running=estado.running,
        pid=estado.pid,
        command=estado.command,
        source=estado.source,
        evidence=estado.evidence,
        started_at=estado.started_at,
        can_start=estado.can_start,
        port_warning=estado.port_warning,
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


@router.post("/restart", response_model=DevServerOut)
def server_restart(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerOut:
    """Para e sobe de novo, sem passar pelo ambiente.

    Existe porque é o gesto mais repetido de um dia de trabalho em backend, e
    fazê-lo com dois cliques e uma espera no meio é atrito puro. Não mexe nos
    containers: quem reinicia o backend quer o banco exatamente onde estava.
    """
    project = projects.get(project_id, touch=True)
    servers.stop(project)
    return _to_out(servers.start(project))


@router.get("/logs", response_model=DevServerLogs)
def server_logs(
    project_id: str,
    lines: int = Query(default=200, ge=1, le=2000),
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerLogs:
    project = projects.get(project_id)
    return DevServerLogs(lines=servers.logs(project, lines=lines))
