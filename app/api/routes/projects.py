"""Rotas de projeto.

Esta camada valida payload, chama o service e devolve schema. Não conhece
`subprocess`, path de sistema operacional nem sintaxe de comando (NFR-020).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import (
    get_dev_server_service,
    get_health_service,
    get_port_discovery,
    get_project_service,
)
from app.models.project import Project
from app.schemas.git import DetectionResult, PortDriftOut
from app.schemas.project import (
    HealthScoreOut,
    IndicadorOut,
    ProjectCreate,
    ProjectDetail,
    ProjectList,
    ProjectSummary,
    ProjectUpdate,
    RecomendacaoOut,
)
from app.services.dashboard_service import avaliar_dono
from app.services.dev_server_service import DevServerService
from app.services.health_service import HealthService
from app.services.intelligence_service import IntelligenceService
from app.services.port_discovery_service import PortDiscoveryService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _to_summary(
    project: Project,
    *,
    can_start: bool = False,
    app_running: bool | None = None,
    open_service_key: str | None = None,
    open_service_label: str | None = None,
    app_online: bool | None = None,
) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        path=project.path,
        status=project.status,  # type: ignore[arg-type]
        is_pinned=project.is_pinned,
        ai_enabled=project.ai_enabled,
        technologies=[tech.name for tech in project.technologies],
        services_total=len(project.services),
        last_accessed_at=project.last_accessed_at,
        can_start=can_start,
        app_running=app_running,
        open_service_key=open_service_key,
        open_service_label=open_service_label,
        app_online=app_online,
    )


@router.get("", response_model=ProjectList)
def list_projects(
    service: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
    health: HealthService = Depends(get_health_service),
    ports: PortDiscoveryService = Depends(get_port_discovery),
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

    # Quem ocupa cada porta, do cache que a descoberta preenche. Uma leitura
    # para a lista inteira, não uma por projeto.
    donos = ports.last_known().by_port() if ports is not None else None

    return ProjectList(
        items=[
            _to_summary(p, **_capacidades(p, servers, rodando, health, donos))
            for p in projects
        ],
        total=total,
    )


def _capacidades(  # type: ignore[no-untyped-def]
    project: Project,
    servers,
    rodando: set[str],
    health=None,
    dono_por_porta=None,
) -> dict:
    """O que o painel sabe fazer com este projeto, e em que estado ele está.

    Leitura de disco pequena e local — os mesmos arquivos que a detecção já lê,
    e da mesma ordem de custo que o `is_dir()` que a listagem já faz por
    projeto. Nada de rede, nada de subprocess (NFR-010).
    """
    tem_app = servers.plan(project) is not None

    # Depois de ligar, a próxima coisa que alguém quer é **ver** — e o card
    # sabia ligar sem saber abrir, o que obrigava a passar pela página do
    # projeto só para clicar num link.
    abrivel = next(
        (
            service
            for service in project.services
            if service.open_in_browser and (service.url or service.port)
        ),
        None,
    )

    # `app_running` fala do **processo nativo**, e continua sendo o que o botão
    # de ligar usa: ele liga e desliga esse processo, não o container. Mas um
    # projeto que roda inteiro em Docker tem `app_running=False` para sempre, e
    # quem só olha esse campo o desenha apagado com a aplicação atendendo — foi
    # o caso do APP INGRESSO, com os dois containers de pé e o grafo dizendo que
    # não havia nada no ar.
    #
    # `app_online` responde a outra pergunta: **a aplicação atende?** Vem do
    # cache que o poller preenche, sem rede nem disco aqui (NFR-010), e é `None`
    # enquanto ninguém verificou — que é diferente de "não".
    app_online: bool | None = None
    if health is not None and abrivel is not None:
        ultimo = health.last_known(project.id, abrivel.key)
        if ultimo is not None and ultimo.state in ("ONLINE", "OFFLINE", "ERROR", "STARTING"):
            online = ultimo.state == "ONLINE"
            # A verificação abre um socket e pergunta "tem alguém aí?", nunca
            # "quem?". Duas respostas divergem sempre que dois projetos
            # declaram a mesma porta — e foi o que aconteceu na primeira versão
            # disto: o crossperformance apareceu no ar mostrando o container do
            # APP INGRESSO, que é quem ocupa a 8000 de verdade.
            #
            # Sem prova de dono, o painel não afirma. É a mesma regra que o
            # Dashboard aplica com `proven`, e por isso ela mora num lugar só.
            if online and dono_por_porta is not None:
                provado, _ = avaliar_dono(project, dono_por_porta.get(abrivel.port))
                online = provado
            app_online = online

    return {
        "can_start": tem_app or _has_compose(project),
        # `None` de propósito quando não há aplicação separada: ver o comentário
        # do campo em `ProjectSummary`.
        "app_running": (project.id in rodando) if tem_app else None,
        "open_service_key": abrivel.key if abrivel else None,
        "open_service_label": abrivel.label if abrivel else None,
        "app_online": app_online,
    }


def _has_compose(project: Project) -> bool:
    from pathlib import Path

    from app.detection.detectors.docker_stack import find_compose_relativo

    diretorio = Path(project.path)
    return diretorio.is_dir() and find_compose_relativo(diretorio) is not None


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
        port_drift=[
            PortDriftOut(key=d.key, label=d.label, declared=d.declared, detected=d.detected)
            for d in diff.port_drift
        ],
    )

@router.get("/{project_id}/intelligence", response_model=HealthScoreOut)
def project_intelligence(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
    servers: DevServerService = Depends(get_dev_server_service),
) -> HealthScoreOut:
    """Health Score do projeto, indicador a indicador.

    Rota de projeto, e não de lista, de propósito: ela lê disco e agrega várias
    consultas. Fazer isso por card na listagem é exatamente o que a NFR-010
    proíbe.
    """
    project = service.get(project_id)
    inteligencia = IntelligenceService(service.session)
    resultado = inteligencia.score(project)

    # O aviso de porta vem do serviço que sabe montar o comando; a inteligência
    # não conhece plano de execução, e não deveria passar a conhecer só para
    # citar um fato que outro já apurou.
    aviso = servers.status(project).port_warning

    return HealthScoreOut(
        project_id=resultado.project_id,
        score=resultado.score,
        cobertura=resultado.cobertura,
        recomendacoes=[
            RecomendacaoOut(titulo=r.titulo, porque=r.porque, onde=r.onde)
            for r in inteligencia.recomendacoes(project, aviso_de_porta=aviso)
        ],
        indicadores=[
            IndicadorOut(
                chave=i.chave,
                rotulo=i.rotulo,
                nota=i.nota,
                evidencia=i.evidencia,
                sugestao=i.sugestao,
            )
            for i in resultado.indicadores
        ],
    )
