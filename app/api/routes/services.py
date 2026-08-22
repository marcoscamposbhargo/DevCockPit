"""Rotas de serviços, health check e ações de sistema operacional."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_health_service,
    get_port_discovery,
    get_project_service,
    get_system_service,
)
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
from app.services.health_service import HealthService, targets_from_project
from app.services.port_discovery_service import PortDiscoveryService
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

        for service in project.services:
            if not service.port or service.port in portas_observadas:
                continue

            # O projeto está no ar em outra porta. Sugere a primeira observada
            # que ainda não corresponde a nenhum serviço declarado dele.
            declaradas = {s.port for s in project.services if s.port}
            candidatas = [p for p in observadas if p.port not in declaradas]
            sugestao = candidatas[0] if candidatas else None

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
