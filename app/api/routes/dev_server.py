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

from app.api.deps import (
    get_cache,
    get_dev_server_service,
    get_health_service,
    get_port_discovery,
    get_project_service,
)
from app.core.cache import TTLCache
from app.schemas.health import (
    DevServerLogs,
    DevServerOut,
    RunningServerList,
    RunningServerOut,
)
from app.services.dashboard_service import CACHE_KEY as DASHBOARD_CACHE_KEY
from app.services.dev_server_service import DevServerService, DevServerState
from app.services.health_service import HealthService
from app.services.port_discovery_service import PortDiscoveryService
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


def _to_out(estado: DevServerState, undeclared: list[int] | None = None) -> DevServerOut:
    return DevServerOut(
        running=estado.running,
        pid=estado.pid,
        command=estado.command,
        source=estado.source,
        evidence=estado.evidence,
        started_at=estado.started_at,
        can_start=estado.can_start,
        port_warning=estado.port_warning,
        undeclared_ports=undeclared or [],
    )


def _portas_sem_cadastro(project, ports) -> list[int]:  # type: ignore[no-untyped-def]
    """Portas deste projeto que ninguém declarou.

    Só com prova de dono: atribuir pela porta declarada seria circular, e
    atribuir por palpite já custou a este projeto duas sessões de conserto.
    """
    if ports is None:
        return []

    declaradas = {service.port for service in project.services if service.port}
    return sorted(
        {
            porta.port
            for porta in ports.last_known().for_project(project.id)
            if porta.strong_evidence and porta.port not in declaradas
        }
    )


@router.get("", response_model=DevServerOut)
def server_status(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    ports: PortDiscoveryService = Depends(get_port_discovery),
) -> DevServerOut:
    project = projects.get(project_id)
    return _to_out(servers.status(project), _portas_sem_cadastro(project, ports))


def _esquecer_estado(cache: TTLCache, health: HealthService, project_id: str) -> None:
    """Joga fora o que o painel achava saber sobre este projeto.

    Ligar e desligar mudam exatamente o que o dashboard mostra, e o cache dele
    dura mais que a paciência de quem clicou: o botão respondia sucesso e a
    tela continuava dizendo o contrário por meio minuto. Pior no desligar — a
    impressão que fica é a de um projeto que não desliga.

    Só se apaga o que se sabe estar velho; o valor novo vem do próximo ciclo do
    verificador, ou de um "Verificar agora".
    """
    cache.invalidate(DASHBOARD_CACHE_KEY)
    health.invalidate(project_id)


@router.post("/start", response_model=DevServerOut)
def server_start(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    cache: TTLCache = Depends(get_cache),
    health: HealthService = Depends(get_health_service),
) -> DevServerOut:
    estado = servers.start(projects.get(project_id, touch=True))
    _esquecer_estado(cache, health, project_id)
    return _to_out(estado)


@router.post("/stop", response_model=DevServerOut)
def server_stop(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    cache: TTLCache = Depends(get_cache),
    health: HealthService = Depends(get_health_service),
) -> DevServerOut:
    estado = servers.stop(projects.get(project_id))
    _esquecer_estado(cache, health, project_id)
    return _to_out(estado)


@router.post("/restart", response_model=DevServerOut)
def server_restart(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    cache: TTLCache = Depends(get_cache),
    health: HealthService = Depends(get_health_service),
) -> DevServerOut:
    """Para e sobe de novo, sem passar pelo ambiente.

    Existe porque é o gesto mais repetido de um dia de trabalho em backend, e
    fazê-lo com dois cliques e uma espera no meio é atrito puro. Não mexe nos
    containers: quem reinicia o backend quer o banco exatamente onde estava.
    """
    project = projects.get(project_id, touch=True)
    servers.stop(project)
    estado = servers.start(project)
    _esquecer_estado(cache, health, project_id)
    return _to_out(estado)


@router.get("/logs", response_model=DevServerLogs)
def server_logs(
    project_id: str,
    lines: int = Query(default=200, ge=1, le=2000),
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> DevServerLogs:
    project = projects.get(project_id)
    return DevServerLogs(lines=servers.logs(project, lines=lines))
