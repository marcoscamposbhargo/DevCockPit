"""Métricas da máquina e dos servidores que o painel subiu.

Rota de leitura pura: nada aqui muda estado. É consultada com frequência pela
tela, então o custo importa — processador, memória e disco vêm de `psutil` em
milissegundos, e a temperatura tem cache próprio no serviço.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_dev_server_service,
    get_metrics_service,
    get_port_discovery,
    get_project_service,
)
from app.schemas.health import (
    MachineMetricsOut,
    MetricsOut,
    ProcessStopped,
    ServerMetricsOut,
)
from app.services.dev_server_service import DevServerService
from app.services.metrics_service import MetricsService
from app.services.port_discovery_service import PortDiscoveryService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/metrics", response_model=MetricsOut)
def system_metrics(
    metrics: MetricsService = Depends(get_metrics_service),
    servers: DevServerService = Depends(get_dev_server_service),
    projects: ProjectService = Depends(get_project_service),
) -> MetricsOut:
    """Como está a máquina, e quanto cada servidor está custando.

    A segunda metade é o que só este painel sabe responder: o Gerenciador de
    Tarefas mostra dezoito `node.exe` e nenhum nome de projeto.
    """
    cadastrados, _total = projects.list(limit=500)
    nomes = {project.id: project.name for project in cadastrados}

    registros = [
        (registro, nomes.get(registro.project_id, registro.project_id))
        for registro in servers.running_project_ids()
    ]

    dados = metrics.snapshot(registros)

    return MetricsOut(
        machine=MachineMetricsOut(
            cpu_percent=dados.machine.cpu_percent,
            cpu_count=dados.machine.cpu_count,
            memory_percent=dados.machine.memory_percent,
            memory_used_gb=dados.machine.memory_used_gb,
            memory_total_gb=dados.machine.memory_total_gb,
            disk_percent=dados.machine.disk_percent,
            disk_free_gb=dados.machine.disk_free_gb,
            temperature_c=dados.machine.temperature_c,
        ),
        servers=[
            ServerMetricsOut(
                project_id=s.project_id,
                project_name=s.project_name,
                pid=s.pid,
                cpu_percent=s.cpu_percent,
                memory_mb=s.memory_mb,
                process_count=s.process_count,
            )
            for s in dados.servers
        ],
    )


@router.post("/processes/{pid}/stop", response_model=ProcessStopped)
def stop_orphan_process(
    pid: int,
    discovery: PortDiscoveryService = Depends(get_port_discovery),
) -> ProcessStopped:
    """Encerra um servidor de desenvolvimento largado.

    Rota fina de propósito: quem valida se aquele PID pode ser tocado é o
    serviço que o classificou como órfão, e não esta camada.
    """
    observada = discovery.stop_orphan(pid)
    return ProcessStopped(stopped=True, pid=pid, port=observada.port)
