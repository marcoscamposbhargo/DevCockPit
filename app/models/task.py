"""Tarefa de projeto — o que falta fazer.

Deliberadamente mínima: sem sprint, sem estimativa, sem responsável, sem
epic. É um painel de um desenvolvedor só, e um Jira embutido seria a forma mais
rápida de ninguém usar. O que precisa existir é o suficiente para responder
"qual é a próxima?" — título, prioridade e estado.

Era Fase 3 no plano. Foi adiantada porque não depende de provedor de IA e
porque sem ela o "Meu dia" só sabe do próximo passo declarado na última sessão:
uma linha de texto por projeto, que some quando a sessão seguinte a substitui.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UtcDateTime, utcnow


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    DOING = "DOING"
    DONE = "DONE"
    #: Desistiu — e isso é diferente de feito. Apagar perderia a informação de
    #: que a ideia foi considerada e descartada, que é justamente o que evita
    #: reabrir a mesma discussão daqui a três meses.
    DROPPED = "DROPPED"

    @property
    def is_final(self) -> bool:
        return self in (TaskStatus.DONE, TaskStatus.DROPPED)


class TaskPriority(StrEnum):
    HIGH = "1"
    NORMAL = "2"
    LOW = "3"


class AiTask(Base):
    __tablename__ = "ai_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=TaskStatus.OPEN.value
    )
    #: 1 alta, 2 média, 3 baixa. Inteiro e não enum de texto porque a ordenação
    #: é o uso principal desta coluna.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    #: `human` ou `ai_suggested`, com a mesma regra da memória: sugestão que
    #: ninguém confirmou aparece marcada, nunca como tarefa do projeto.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="human")

    #: De qual sessão a tarefa nasceu, quando nasceu de uma. Serve para o
    #: resumo poder dizer "abri três tarefas e fechei duas".
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_session.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    __table_args__ = (
        Index("ix_ai_task_project_status", "project_id", "status", "priority"),
    )

    @property
    def is_open(self) -> bool:
        return self.status in (TaskStatus.OPEN.value, TaskStatus.DOING.value)
