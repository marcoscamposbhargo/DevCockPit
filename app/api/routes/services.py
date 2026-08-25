"""Rotas de serviços, health check e ações de sistema operacional."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_cache,
    get_docker_service,
    get_health_service,
    get_port_discovery,
    get_project_service,
    get_system_service,
)
from app.core.cache import TTLCache
from app.core.errors import DomainError
from app.models.project import ProjectService as ProjectServiceModel
from app.schemas.health import (
    ObservedPortOut,
    OpenBrowserRequest,
    OpenResult,
    PortBinding,
    PortMap,
    PortMismatch,
    PortUsage,
    ServiceList,
    ServicesReplace,
    ServiceStateOut,
)
from app.services.dashboard_service import CACHE_KEY as DASHBOARD_CACHE_KEY
from app.services.docker_service import DockerService
from app.services.health_service import HealthService, targets_from_project
from app.services.port_discovery_service import PortDiscoveryService
from app.services.project_service import ProjectService
from app.services.system_action_service import SystemActionService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["services"])
global_router = APIRouter(prefix="/api/services", tags=["services"])


def _to_out(service, resultado, dono_incerto: str | None = None) -> ServiceStateOut:  # type: ignore[no-untyped-def]
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
        unverified_owner=dono_incerto,
    )


def _published_by_own_container(project, service, docker) -> bool:  # type: ignore[no-untyped-def]
    """Um container **deste projeto** publica esta porta no host.

    É a prova que faltava para porta de container. O `cwd` de um container
    aponta para a instalação do Docker, então nenhuma das regras de atribuição
    da descoberta consegue provar dono — e sem esta consulta todo serviço em
    container ficaria marcado como "responde, mas não sei de quem", o que num
    fluxo de trabalho baseado em Compose é ruído puro e não aviso.

    O `docker ps` daqui é o mesmo que a aba Docker já faz, e sai do mesmo cache
    (NFR-010): a rota não executa subprocess por conta própria.
    """
    if not service.port:
        return False
    try:
        estado = docker.status(project)
    except DomainError:
        # Sem Docker, ou sem Compose: nada a confirmar, e o aviso segue seu
        # curso normal. Falha aqui nunca vira erro da tela de serviços.
        return False

    return any(
        publicada.host_port == service.port
        for container in estado.containers
        if container.is_running
        for publicada in container.ports
    )


def _unverified(project, service, resultado, observacao, docker=None) -> str | None:  # type: ignore[no-untyped-def]
    """Responde na porta, mas o painel não prova que é deste projeto.

    A verificação de saúde abre um socket e pergunta "tem alguém aí?". Nunca
    soube perguntar "quem?" — e as duas perguntas têm respostas diferentes
    quando outro projeto ocupa a mesma porta.

    O caso que motivou isto: o SmartDash declara o banco em 5432, todos os
    containers dele foram removidos, o `uvicorn` estava parado, e mesmo assim o
    card dizia "1/2 online". Quem respondia na 5432 era o `ecommerce_postgres`,
    container de um projeto que nem está cadastrado aqui. O SmartDash já estava
    desligado; o painel é que não sabia dizer.

    Só acusa com base em evidência **fraca**: se a descoberta casou o processo
    por diretório ou linha de comando, é prova e não há o que avisar. Sem
    observação nenhuma — antes do primeiro ciclo do poller — também se cala,
    porque não saber não é o mesmo que desconfiar.
    """
    if resultado.state.value != "ONLINE" or not service.port:
        return None

    porta = next((p for p in observacao.ports if p.port == service.port), None)
    if porta is None or porta.strong_evidence:
        return None

    # Container do próprio projeto publicando esta porta é prova, e vale mais
    # que a inferência pelo número que a descoberta faz. Sem isto, o SmartDash
    # com os dois containers de pé continuaria marcado — e o aviso perderia o
    # sentido de tanto aparecer.
    if docker is not None and _published_by_own_container(project, service, docker):
        return None

    quem = porta.process_name or "um processo"
    if porta.project_id and porta.project_id != project.id:
        return f"Responde, mas quem ocupa a {service.port} é {quem}, do {porta.project_name}."
    return (
        f"Responde, mas o painel não consegue provar que é deste projeto — "
        f"quem ocupa a {service.port} é {quem}."
    )


@router.get("/services", response_model=ServiceList)
def list_services(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    health: HealthService = Depends(get_health_service),
    discovery: PortDiscoveryService = Depends(get_port_discovery),
    docker: DockerService = Depends(get_docker_service),
) -> ServiceList:
    """Serviços com o **último estado conhecido**, sempre de cache.

    Verificar aqui transformaria cada carga de tela em N conexões (NFR-011). A
    observação de portas também vem de cache, pelo mesmo motivo: quem varre é o
    poller, nunca o caminho da requisição (NFR-010).
    """
    project = projects.get(project_id)
    observacao = discovery.last_known()

    items = []
    for service in project.services:
        resultado = health.last_known(project.id, service.key)
        aviso = _unverified(project, service, resultado, observacao, docker)
        items.append(_to_out(service, resultado, aviso))

    return ServiceList(items=items)


@router.put("/services", response_model=ServiceList)
def replace_services(
    project_id: str,
    payload: ServicesReplace,
    projects: ProjectService = Depends(get_project_service),
    health: HealthService = Depends(get_health_service),
) -> ServiceList:
    project = projects.get(project_id)

    project.services.clear()
    #: O flush precisa acontecer **entre** o clear e os appends. Sem ele o
    #: SQLAlchemy emite os INSERT antes dos DELETE na mesma descarga, e
    #: reenviar a lista com as mesmas chaves estoura
    #: `UNIQUE(project_id, key)` — o PUT respondia 200 e a transação era
    #: desfeita depois da resposta, então a tela mostrava salvo e o banco
    #: continuava com o valor velho.
    projects.session.flush()

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
    cache: TTLCache = Depends(get_cache),
    discovery: PortDiscoveryService = Depends(get_port_discovery),
    docker: DockerService = Depends(get_docker_service),
) -> ServiceList:
    """Reverificação sob demanda (FR-063). Único caminho que verifica na hora."""
    project = projects.get(project_id)
    await health.check_many(targets_from_project(project))

    # O dashboard é o que alimenta os sinais do card, e tem cache próprio. Sem
    # descartá-lo aqui, a tela continuava mostrando "1/2 online" logo depois de
    # uma verificação que encontrou os dois no ar — o número certo só aparecia
    # no ciclo seguinte, e quem clicou concluía que a ação não pegou.
    cache.invalidate(DASHBOARD_CACHE_KEY)

    observacao = discovery.last_known()
    items = []
    for service in project.services:
        resultado = health.last_known(project.id, service.key)
        aviso = _unverified(project, service, resultado, observacao, docker)
        items.append(_to_out(service, resultado, aviso))

    return ServiceList(items=items)


# --- ações de sistema operacional ---


@router.post("/open/vscode", response_model=OpenResult)
def open_vscode(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    system: SystemActionService = Depends(get_system_service),
) -> OpenResult:
    system.open_in_editor(projects.get(project_id, touch=True))
    return OpenResult(opened=True, action="system.vscode")


@global_router.post("/open/vscode", response_model=OpenResult)
def open_vscode_blank(
    system: SystemActionService = Depends(get_system_service),
) -> OpenResult:
    """Abre o VS Code sem projeto — o atalho de começar o dia.

    Não recebe corpo nem parâmetro: não há caminho para o cliente informar, e
    por isso não há caminho para o cliente forjar.
    """
    system.open_editor_blank()
    return OpenResult(opened=True, action="system.vscode_blank")


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
def port_map(
    projects: ProjectService = Depends(get_project_service),
    discovery: PortDiscoveryService = Depends(get_port_discovery),
) -> PortMap:
    """Mapa de portas: o que os projetos declaram e o que está de fato no ar.

    Nada aqui abre socket nem varre processo (NFR-010). O lado declarado vem do
    banco; o lado observado vem do cache que o poller preenche a cada ciclo, e
    vem vazio até o primeiro deles.

    Cruzar os dois é o ponto da tela. Conflito entre dois declarados é conflito
    de configuração. Divergência entre declarado e observado é a mentira que
    fazia um projeto aparecer parado com o servidor no ar — e é a única das
    duas que o painel não sabia contar.
    """
    todos, _ = projects.list(limit=500)
    observacao = discovery.last_known()

    por_porta: dict[int, set[str]] = defaultdict(set)
    #: Conflito é contado por **serviço**, não por projeto: dois serviços do
    #: mesmo projeto na mesma porta também não sobem juntos, e por nome de
    #: projeto esse caso passava despercebido.
    quantos: dict[int, int] = defaultdict(int)
    brutos: list[tuple[int, str, str, str, str, str, str | None]] = []

    for project in todos:
        for service in project.services:
            if not service.port:
                continue
            por_porta[service.port].add(project.name)
            quantos[service.port] += 1
            brutos.append(
                (
                    service.port,
                    project.id,
                    project.name,
                    service.key,
                    service.label,
                    service.host,
                    service.url,
                )
            )

    items = [
        PortUsage(port=porta, projects=sorted(nomes), conflict=quantos[porta] > 1)
        for porta, nomes in sorted(por_porta.items())
    ]
    conflitantes = {item.port for item in items if item.conflict}

    bindings = [
        PortBinding(
            port=porta,
            project_id=project_id,
            project_name=project_name,
            service_key=key,
            service_label=label,
            host=host,
            url=url,
            conflict=porta in conflitantes,
        )
        for porta, project_id, project_name, key, label, host, url in sorted(
            brutos, key=lambda linha: (linha[0], linha[2], linha[4])
        )
    ]

    return PortMap(
        items=items,
        bindings=bindings,
        conflicts=sum(1 for item in items if item.conflict),
        observed=[
            ObservedPortOut(
                port=porta.port,
                pid=porta.pid,
                process_name=porta.process_name,
                project_id=porta.project_id,
                project_name=porta.project_name,
                matched_by=porta.matched_by,
                cwd=porta.cwd,
                orphan=porta.orphan,
                unmanaged=porta.unmanaged,
                strong_evidence=porta.strong_evidence,
            )
            for porta in observacao.ports
        ],
        observation_available=observacao.available,
        mismatches=_mismatches(todos, observacao),
    )


def _mismatches(projects, observacao) -> list[PortMismatch]:  # type: ignore[no-untyped-def]
    """Serviço cuja porta declarada não é a que o projeto está usando.

    Duas formas do mesmo problema, e a distinção importa para o texto da tela:

    - o projeto tem porta escutando, só que **outra** — o número no cadastro
      está velho e dá para corrigir apontando qual é o certo;
    - o projeto não tem nada escutando — pode ser que esteja mesmo parado, e
      afirmar "porta errada" aí seria chute.

    O segundo caso só é reportado quando *alguma* porta do projeto foi
    observada, para não transformar todo projeto desligado em alerta.

    **Uma porta observada só pode ser sugerida a um serviço.** A primeira
    versão sugeria a mesma porta a todos os serviços divergentes do projeto: um
    projeto com backend e banco desalinhados recebia "usar 8000" nos dois, e
    aceitar as duas sugestões colocaria os dois serviços na mesma porta — um
    conflito criado pela própria ferramenta que existe para apontar conflitos.

    Sobrando ambiguidade — mais serviços divergentes que portas candidatas —, a
    divergência é reportada **sem** sugestão. Dizer "está errado" sem chutar o
    certo é honesto; chutar errado custa uma porta trocada à toa.
    """
    por_projeto: dict[str, list] = {}
    for porta in observacao.ports:
        if porta.project_id:
            por_projeto.setdefault(porta.project_id, []).append(porta)

    divergencias: list[PortMismatch] = []

    for project in projects:
        observadas = por_projeto.get(project.id, [])
        if not observadas:
            # Nada deste projeto está escutando: silêncio é o estado esperado
            # de um projeto parado, não uma divergência.
            continue

        portas_observadas = {porta.port for porta in observadas}
        declaradas = {s.port for s in project.services if s.port}

        candidatas = [p for p in observadas if p.port not in declaradas]

        # **Só há divergência se alguma porta do projeto estiver escutando sem
        # que serviço declarado nenhum a explique.** Sem esta condição, um
        # projeto com o banco em container e a aplicação parada acusava o
        # backend de "porta errada" — quando ele só estava desligado, que é o
        # estado normal de metade dos projetos em qualquer momento do dia.
        #
        # O caso que a tela existe para pegar continua pegando: o DevCockpit
        # declarava 3003 e escutava em 8765, e a 8765 é exatamente uma porta
        # observada que nenhum serviço declarado explicava.
        if not candidatas:
            continue

        divergentes = [
            service
            for service in project.services
            if service.port and service.port not in portas_observadas
        ]

        # Com um só serviço divergente, a porta que sobra é dele. Com vários,
        # não há como saber qual porta é de qual — e a resposta certa a "não
        # sei" é não sugerir, não sugerir a mesma para todos.
        pode_sugerir = len(divergentes) == 1

        for indice, service in enumerate(divergentes):
            sugestao = candidatas[indice] if pode_sugerir and indice < len(candidatas) else None

            divergencias.append(
                PortMismatch(
                    project_id=project.id,
                    project_name=project.name,
                    service_key=service.key,
                    service_label=service.label,
                    declared_port=service.port,
                    observed_port=sugestao.port if sugestao else None,
                    process_name=sugestao.process_name if sugestao else None,
                )
            )

    return divergencias
