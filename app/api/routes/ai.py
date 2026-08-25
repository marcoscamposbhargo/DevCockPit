"""Sessão de trabalho, memória e briefing do dia.

Fase 1 do Cockpit AI: tudo aqui funciona **sem provedor de IA configurado**.
Nenhuma rota deste arquivo fala com modelo nenhum — o que existe é registro do
que o painel observou e do que a pessoa declarou.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_briefing_service,
    get_memory_service,
    get_project_service,
    get_session_service,
)
from app.models.ai import AiMemory, AiSession
from app.schemas.ai import (
    BriefingOut,
    DayItemOut,
    MemoryCreate,
    MemoryList,
    MemoryOut,
    MemoryUpdate,
    SessionEnd,
    SessionFactsOut,
    SessionList,
    SessionOut,
    SessionStart,
)
from app.services.briefing_service import BriefingService
from app.services.memory_service import MemoryService
from app.services.project_service import ProjectService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["ai"])
#: Fora do projeto: o briefing olha todos, e a memória global não pertence a
#: nenhum.
global_router = APIRouter(prefix="/api/ai", tags=["ai"])


def _sessao_out(registro: AiSession) -> SessionOut:
    fatos = SessionService.facts_of(registro)
    return SessionOut(
        id=registro.id,
        project_id=registro.project_id,
        started_at=registro.started_at,
        ended_at=registro.ended_at,
        objective=registro.objective,
        summary=registro.summary,
        next_steps=registro.next_steps,
        is_open=registro.is_open,
        facts=SessionFactsOut(**asdict(fatos)),
    )


def _memoria_out(registro: AiMemory) -> MemoryOut:
    return MemoryOut(
        id=registro.id,
        project_id=registro.project_id,
        kind=registro.kind,
        title=registro.title,
        body=registro.body,
        source=registro.source,
        confirmed=registro.is_confirmed,
        session_id=registro.session_id,
        created_at=registro.created_at,
        updated_at=registro.updated_at,
    )


# --- sessão ---------------------------------------------------------------


@router.get("/sessions", response_model=SessionList)
def list_sessions(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    sessions: SessionService = Depends(get_session_service),
    limit: int = Query(default=20, ge=1, le=100),
) -> SessionList:
    project = projects.get(project_id)
    atual = sessions.current(project)
    anterior = sessions.previous(project)
    return SessionList(
        items=[_sessao_out(s) for s in sessions.history(project, limit=limit)],
        current=_sessao_out(atual) if atual else None,
        previous=_sessao_out(anterior) if anterior else None,
    )


@router.post("/sessions/start", response_model=SessionOut)
def start_session(
    project_id: str,
    payload: SessionStart,
    projects: ProjectService = Depends(get_project_service),
    sessions: SessionService = Depends(get_session_service),
) -> SessionOut:
    """Abre a sessão e registra o marco inicial do Git.

    `touch=True`: abrir sessão é acessar o projeto, e o dashboard usa isso para
    ordenar o que foi mexido por último.
    """
    project = projects.get(project_id, touch=True)
    return _sessao_out(sessions.start(project, objective=payload.objective))


@router.post("/sessions/end", response_model=SessionOut)
def end_session(
    project_id: str,
    payload: SessionEnd,
    projects: ProjectService = Depends(get_project_service),
    sessions: SessionService = Depends(get_session_service),
) -> SessionOut:
    project = projects.get(project_id)
    return _sessao_out(
        sessions.end(project, summary=payload.summary, next_steps=payload.next_steps)
    )


# --- memória --------------------------------------------------------------


@router.get("/memory", response_model=MemoryList)
def list_memory(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    memory: MemoryService = Depends(get_memory_service),
    kind: str | None = Query(default=None, max_length=20),
) -> MemoryList:
    project = projects.get(project_id)
    itens = memory.list(project_id=project.id, kind=kind)
    return MemoryList(items=[_memoria_out(m) for m in itens])


@router.post("/memory", response_model=MemoryOut, status_code=201)
def create_memory(
    project_id: str,
    payload: MemoryCreate,
    projects: ProjectService = Depends(get_project_service),
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    project = projects.get(project_id)
    registro = memory.write(
        kind=payload.kind,
        title=payload.title,
        body=payload.body,
        project_id=project.id,
        session_id=payload.session_id,
    )
    return _memoria_out(registro)


@global_router.get("/memory", response_model=MemoryList)
def list_global_memory(
    memory: MemoryService = Depends(get_memory_service),
    kind: str | None = Query(default=None, max_length=20),
) -> MemoryList:
    """Memória do desenvolvedor: o que vale em todos os projetos."""
    return MemoryList(items=[_memoria_out(m) for m in memory.list(global_only=True, kind=kind)])


@global_router.post("/memory", response_model=MemoryOut, status_code=201)
def create_global_memory(
    payload: MemoryCreate,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    registro = memory.write(kind=payload.kind, title=payload.title, body=payload.body)
    return _memoria_out(registro)


@global_router.patch("/memory/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    return _memoria_out(memory.update(memory_id, title=payload.title, body=payload.body))


@global_router.post("/memory/{memory_id}/confirm", response_model=MemoryOut)
def confirm_memory(
    memory_id: int,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    """Promove sugestão a afirmação.

    Existe desde já, embora só a Fase 2 vá produzir sugestão: sem este botão, a
    distinção entre `ai_suggested` e `human` seria decorativa.
    """
    return _memoria_out(memory.confirm(memory_id))


@global_router.delete("/memory/{memory_id}", status_code=204)
def delete_memory(
    memory_id: int,
    memory: MemoryService = Depends(get_memory_service),
) -> None:
    memory.delete(memory_id)


# --- o dia ----------------------------------------------------------------


@global_router.get("/day", response_model=BriefingOut)
def start_my_day(briefing: BriefingService = Depends(get_briefing_service)) -> BriefingOut:
    """O que merece atenção hoje, ordenado por motivo declarado."""
    dados = briefing.build()
    return BriefingOut(
        generated_at=dados.generated_at,
        total_projects=dados.total_projects,
        open_sessions=dados.open_sessions,
        # `score` fica de fora: é como a tela decide a ordem, não informação
        # para quem lê. Número de ranking exposto vira discussão sobre o número.
        items=[
            DayItemOut(**{k: v for k, v in asdict(item).items() if k != "score"})
            for item in dados.items
        ],
        suggestion=dados.suggestion,
    )
