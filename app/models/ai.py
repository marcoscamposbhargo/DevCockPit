"""Sessão de trabalho e memória de projeto — a fundação do Cockpit AI.

Duas tabelas, e nenhuma delas depende de IA para valer: uma sessão registrada e
uma memória consultável respondem "onde eu parei?" com provedor nenhum
configurado. É o que a Fase 1 entrega (`docs/ai/AI_IMPLEMENTATION_PLAN.md`), e
é o que dá à Fase 2 fatos para ler em vez de deduzir.

`ai_message` e `ai_usage_day` entraram na Fase 2, quando o chat passou a
escrever nelas — e não antes. Tabela criada sem ninguém escrever é o defeito
que este projeto já corrigiu duas vezes (`health_snapshot` e `git_repository`
ficaram meses como schema sem escrita).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UtcDateTime, utcnow


class MemoryKind(StrEnum):
    """O que a linha de memória é.

    Uma tabela só com discriminador, e não nove tabelas: os campos são os
    mesmos e o custo de nove migrações não se paga.
    """

    CONTEXT = "context"
    ARCHITECTURE = "architecture"
    DECISION = "decision"
    BUG = "bug"
    DEBT = "debt"
    DISCOVERY = "discovery"
    NEXT_STEP = "next_step"
    #: Só em memória global (`project_id` nulo).
    PREFERENCE = "preference"
    PATTERN = "pattern"
    COMMAND = "command"


class MemorySource(StrEnum):
    """De onde a linha veio — o campo que impede memória virar ficção.

    A mesma doutrina que fez o painel parar de dizer "no ar" sem prova:
    `OBSERVED` é o que o DevCockpit mediu, `HUMAN` é o que a pessoa escreveu ou
    confirmou, `AI_SUGGESTED` é proposta que ninguém confirmou ainda — e a
    interface mostra os três de forma diferente.
    """

    OBSERVED = "observed"
    HUMAN = "human"
    AI_SUGGESTED = "ai_suggested"


class AiSession(Base):
    """Um período de trabalho num projeto, com começo, objetivo e fim."""

    __tablename__ = "ai_session"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    #: Nulo enquanto a sessão está aberta. Só uma por projeto de cada vez.
    ended_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    #: O que se pretendia fazer, declarado por quem abriu a sessão.
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: O que aconteceu, montado dos fatos e revisável por quem encerra.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: JSON com o que foi **observado**: sha e branch no começo e no fim,
    #: commits do período, ações executadas, serviços que caíram. É o que
    #: permite o resumo ser montado de fato, e não redigido do nada.
    facts: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_ai_session_project", "project_id", "started_at"),)

    @property
    def is_open(self) -> bool:
        return self.ended_at is None


class AiMemory(Base):
    """Uma linha de memória, de projeto ou global.

    `project_id` nulo é a memória global do desenvolvedor — mesma tabela, mesmo
    formato. Duas tabelas idênticas com nomes diferentes seriam duas migrações
    e dois repositórios para o mesmo comportamento.
    """

    __tablename__ = "ai_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MemorySource.HUMAN.value
    )
    #: Nulo em sugestão não confirmada. Sugestão velha é podada; confirmada,
    #: nunca — só o usuário apaga o que ele mesmo afirmou.
    confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_session.id", ondelete="SET NULL"), nullable=True
    )
    #: Quantas vezes esta linha entrou num contexto. Serve para priorizar
    #: quando o orçamento de tokens não couber com tudo (Fase 2).
    relevance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (Index("ix_ai_memory_project_kind", "project_id", "kind"),)

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class AiMessage(Base):
    """Uma fala do chat, e o que ela custou.

    Guarda o **resumo** do contexto enviado, não o conteúdo: o contexto inclui
    trecho de código e de documentação do projeto, e copiá-lo para cá dobraria
    o banco do painel para nada.
    """

    __tablename__ = "ai_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("ai_session.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(12), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)

    #: Que camadas de contexto entraram — proveniência sem o conteúdo.
    #: Qual chapéu atendeu — `devops`, `fullstack`, `qa`. Nulo nas mensagens
    #: anteriores à Fase 3.2, e em pergunta avulsa (que não tem perfil).
    agent: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: A versão do prompt que produziu esta resposta. Sem ela, uma resposta
    #: guardada não tem como ser explicada depois que o prompt muda.
    prompt_versao: Mapped[str | None] = mapped_column(String(10), nullable=True)
    #: Qual chapéu atendeu — `devops`, `fullstack`, `qa`. Nulo nas mensagens
    #: anteriores à Fase 3.2, e na pergunta avulsa, que não tem perfil.
    agent: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: A versão do prompt que produziu esta resposta. Sem ela, uma resposta
    #: guardada não tem como ser explicada depois que o prompt muda.
    prompt_versao: Mapped[str | None] = mapped_column(String(10), nullable=True)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_ai_message_session", "session_id", "id"),)


class AiUsageDay(Base):
    """Gasto do dia, numa linha.

    Uma linha por dia responde "quanto gastei esta semana?" sem varrer
    mensagem, e é o que sustenta o teto diário: ferramenta que gasta sem
    mostrar quanto é ferramenta que um dia assusta.
    """

    __tablename__ = "ai_usage_day"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)  # 2026-08-25, local
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
