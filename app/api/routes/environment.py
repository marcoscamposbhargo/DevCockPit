"""Subir e baixar o ambiente inteiro de um projeto.

`POST /up` devolve `202` com `job_id`, e não o resultado: a sequência pode
levar minutos — `compose up` puxando imagem, banco abrindo — e uma requisição
HTTP pendurada por dois minutos é a forma errada de esperar. O job já traz
console ao vivo, cancelamento e exclusão mútua por projeto.

`POST /down` responde na hora quando o alvo é a aplicação — encerrar processo é
imediato. Quando o alvo são os containers, devolve `job_id`: `compose down`
demora, e é o mesmo motivo do `/up`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_dev_server_service,
    get_docker_service,
    get_environment_service,
    get_job_manager,
    get_preflight_service,
    get_project_service,
)
from app.core.errors import PortsBusy
from app.jobs.job import Job
from app.jobs.job_manager import JobManager
from app.schemas.health import EnvironmentPlanOut, EnvironmentStopped, PreflightOut
from app.schemas.job import JobAccepted
from app.services.dev_server_service import DevServerService
from app.services.docker_service import DockerService
from app.services.environment_service import EnvironmentService
from app.services.preflight_service import PreflightService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects/{project_id}/environment", tags=["environment"])


@router.get("", response_model=EnvironmentPlanOut)
def environment_plan(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    environment: EnvironmentService = Depends(get_environment_service),
) -> EnvironmentPlanOut:
    """O que "Ligar" faria aqui — antes de fazer.

    A tela usa isto para dizer o que vai acontecer e para decidir se o botão de
    parar derruba a aplicação ou o Compose.
    """
    project = projects.get(project_id)
    plano = environment.plan(project, servers)
    estado = servers.status(project)

    return EnvironmentPlanOut(
        compose_file=plano.compose_file,
        app_command=plano.app_command,
        app_source=plano.app_source,
        dependencies=plano.dependencies,
        app_running=estado.running,
    )


@router.get("/preflight", response_model=PreflightOut)
def environment_preflight(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    preflight: PreflightService = Depends(get_preflight_service),
) -> PreflightOut:
    """O que impede este projeto de subir — antes de tentar.

    Existe para a tela poder avisar no lugar certo: a porta ocupada aparece
    quando se olha o projeto, e não no meio de um `compose up` que falha.
    """
    resultado = preflight.check(projects.get(project_id))
    return PreflightOut(**resultado.to_dict(), message=resultado.message())


@router.post("/up", response_model=JobAccepted, status_code=202)
async def environment_up(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    environment: EnvironmentService = Depends(get_environment_service),
    preflight: PreflightService = Depends(get_preflight_service),
    jobs: JobManager = Depends(get_job_manager),
    force: bool = Query(
        default=False,
        description="sobe mesmo com porta ocupada; a decisão passa a ser sua",
    ),
) -> JobAccepted:
    """Sobe o ambiente e depois a aplicação, nessa ordem.

    Antes de enfileirar, confere as portas: descobrir pelo erro do Compose, no
    meio da subida, custa a espera inteira para chegar a uma informação que já
    estava disponível. Com `force=true` a recusa é dispensada — a decisão passa
    a ser de quem clicou, e fica registrada como tal.

    `async def` por necessidade: enfileirar job exige event loop, e rota
    síncrona roda em threadpool onde não há um.
    """
    project = projects.get(project_id, touch=True)

    if not force:
        checagem = preflight.check(project)
        if not checagem.ready:
            # A recusa carrega só a frase: o envelope de erro é contrato
            # estável (`code`, `message`, `correlation_id`) e não vira saco de
            # dados. Quem quiser o detalhe chama `GET /preflight`, que existe
            # exatamente para isso.
            raise PortsBusy(
                checagem.message()
                + " Troque a porta em Ports, encerre quem está nela, ou suba mesmo assim."
            )

    async def work(job: Job) -> str:
        return await environment.up(job, project.id)

    # A mesma chave do Docker: subir o ambiente e rodar `compose up` pela aba
    # Docker são a mesma disputa, e deixá-las em chaves diferentes permitiria
    # as duas ao mesmo tempo no mesmo projeto.
    job = jobs.submit_callable(
        work,
        key=f"docker:{project.id}",
        action="environment.up",
        project_id=project.id,
    )
    return JobAccepted(job_id=job.id, action=job.action, status=job.status)


@router.post("/down", response_model=EnvironmentStopped)
async def environment_down(
    project_id: str,
    include_docker: bool = Query(
        default=False,
        description="derruba os containers também; por padrão só a aplicação para",
    ),
    projects: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    environment: EnvironmentService = Depends(get_environment_service),
    docker: DockerService = Depends(get_docker_service),
) -> EnvironmentStopped:
    """Para a aplicação. O ambiente só cai se for pedido.

    Banco e fila são caros de subir e não mudam entre uma execução e outra da
    aplicação; derrubá-los a cada parada do backend trocaria um ciclo de dois
    segundos por um de trinta.

    A rota **executa** o que decide. Antes ela devolvia `stopped: "docker"` sem
    tocar em container nenhum: o serviço decidia o alvo, ninguém rodava o
    `compose down`, e o cliente anunciava "ambiente derrubado" com os containers
    de pé. Uma resposta de sucesso descrevendo algo que não aconteceu é pior que
    um erro — o erro pelo menos manda olhar.
    """
    project = projects.get(project_id)
    alvo = environment.down(project, servers, include_docker=include_docker)

    if alvo == "docker":
        job = docker.run_action(project, "down", [])
        return EnvironmentStopped(stopped=alvo, job_id=job.id)

    return EnvironmentStopped(stopped=alvo)
