"""Contratos de sessão, memória e briefing do dia."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GitMarkOut(BaseModel):
    branch: str | None = None
    head_sha: str | None = None
    dirty_count: int | None = None
    is_repo: bool = False


class SessionFactsOut(BaseModel):
    """O que o painel observou — e só isso.

    Nada aqui é redigido: são commits, ações e quedas lidos de quem registrou.
    """

    git_start: GitMarkOut = Field(default_factory=GitMarkOut)
    git_end: GitMarkOut | None = None
    commits: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    services_down: list[dict] = Field(default_factory=list)
    duration_minutes: int | None = None


class SessionOut(BaseModel):
    id: str
    project_id: str
    started_at: datetime
    ended_at: datetime | None = None
    objective: str | None = None
    summary: str | None = None
    next_steps: str | None = None
    is_open: bool
    facts: SessionFactsOut = Field(default_factory=SessionFactsOut)


class SessionStart(BaseModel):
    #: Opcional de propósito: obrigar a declarar objetivo antes de começar
    #: transformaria o gesto de abrir numa burocracia, e o registro morreria.
    objective: str | None = Field(default=None, max_length=500)


class SessionEnd(BaseModel):
    #: Vazio faz o painel montar o resumo dos fatos. Preenchido, vale o texto
    #: de quem viveu a sessão — que sabe coisas que nenhum log registra.
    summary: str | None = Field(default=None, max_length=4000)
    next_steps: str | None = Field(default=None, max_length=2000)


class SessionList(BaseModel):
    items: list[SessionOut] = Field(default_factory=list)
    current: SessionOut | None = None
    previous: SessionOut | None = None


class MemoryOut(BaseModel):
    id: int
    project_id: str | None = None
    kind: str
    title: str
    body: str
    #: `observed` | `human` | `ai_suggested` — o que separa registro de palpite.
    source: str
    confirmed: bool
    session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    kind: str = Field(max_length=20)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=8000)
    session_id: str | None = None


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=8000)


class MemoryList(BaseModel):
    items: list[MemoryOut] = Field(default_factory=list)


class TaskOut(BaseModel):
    id: int
    project_id: str
    title: str
    detail: str | None = None
    status: str
    priority: int
    source: str
    session_id: str | None = None
    created_at: datetime
    done_at: datetime | None = None
    is_open: bool


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=4000)
    #: 1 alta, 2 média, 3 baixa.
    priority: int = Field(default=2, ge=1, le=3)
    session_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    detail: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=10)
    priority: int | None = Field(default=None, ge=1, le=3)


class TaskList(BaseModel):
    items: list[TaskOut] = Field(default_factory=list)
    open_count: int = 0


class DayItemOut(BaseModel):
    project_id: str
    name: str
    #: Por que este projeto está nesta posição. A tela explica em vez de só
    #: ordenar: ranking sem motivo é adivinhação com aparência de método.
    reason: str
    next_step: str | None = None
    last_session_at: datetime | None = None
    last_summary: str | None = None
    open_session: bool = False
    dirty_count: int | None = None
    services_online: int = 0
    #: A próxima tarefa aberta deste projeto, quando existir. É o que faz a
    #: tela do dia falar de trabalho concreto, e não só do que a última sessão
    #: deixou escrito.
    next_task: TaskOut | None = None
    open_tasks: int = 0


class BriefingOut(BaseModel):
    generated_at: datetime
    total_projects: int
    open_sessions: list[str] = Field(default_factory=list)
    items: list[DayItemOut] = Field(default_factory=list)
    suggestion: str | None = None


# --- chat -----------------------------------------------------------------


class AiStatusOut(BaseModel):
    """O que a tela precisa saber antes de oferecer o chat.

    Nunca inclui a chave, nem parte dela: a chave não sai do processo por
    nenhuma rota (defesa D-A5).
    """

    enabled: bool
    configured: bool
    #: Quando não configurado, o que fazer para configurar.
    reason: str | None = None
    provider: str
    model: str
    tokens_today: int = 0
    daily_budget: int = 0
    calls_today: int = 0


class ChatAsk(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    #: Que camadas de contexto entraram — proveniência, não o conteúdo.
    context_summary: str | None = None
    context_tokens: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: datetime


class ChatHistoryOut(BaseModel):
    items: list[ChatMessageOut] = Field(default_factory=list)
