"""Acesso a dados de sessão e memória."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai import AiMemory, AiMessage, AiSession, AiUsageDay
from app.models.base import utcnow


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiSession) -> AiSession:
        self.session.add(registro)
        self.session.flush()
        return registro

    def get(self, session_id: str) -> AiSession | None:
        return self.session.get(AiSession, session_id)

    def open_for(self, project_id: str) -> AiSession | None:
        """A sessão aberta deste projeto, se houver.

        Uma por projeto: abrir a segunda encerra a primeira. Sessão esquecida
        aberta por três dias não mede nada.
        """
        stmt = (
            select(AiSession)
            .where(AiSession.project_id == project_id, AiSession.ended_at.is_(None))
            .order_by(AiSession.started_at.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def last_closed(self, project_id: str) -> AiSession | None:
        stmt = (
            select(AiSession)
            .where(AiSession.project_id == project_id, AiSession.ended_at.is_not(None))
            .order_by(AiSession.ended_at.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def list_for(self, project_id: str, limit: int = 20) -> list[AiSession]:
        stmt = (
            select(AiSession)
            .where(AiSession.project_id == project_id)
            .order_by(AiSession.started_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def open_sessions(self) -> list[AiSession]:
        stmt = select(AiSession).where(AiSession.ended_at.is_(None))
        return list(self.session.execute(stmt).scalars())

    def last_closed_by_project(self) -> dict[str, AiSession]:
        """A última sessão encerrada de cada projeto, numa consulta só.

        O briefing do dia precisa disso para 19 projetos; perguntar um a um
        seriam 19 consultas no caminho da requisição (NFR-010).
        """
        recente = (
            select(AiSession.project_id, func.max(AiSession.ended_at).label("fim"))
            .where(AiSession.ended_at.is_not(None))
            .group_by(AiSession.project_id)
            .subquery()
        )
        stmt = select(AiSession).join(
            recente,
            (AiSession.project_id == recente.c.project_id)
            & (AiSession.ended_at == recente.c.fim),
        )
        return {s.project_id: s for s in self.session.execute(stmt).scalars()}


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiMemory) -> AiMemory:
        self.session.add(registro)
        self.session.flush()
        return registro

    def get(self, memory_id: int) -> AiMemory | None:
        return self.session.get(AiMemory, memory_id)

    def delete(self, registro: AiMemory) -> None:
        self.session.delete(registro)
        self.session.flush()

    def list(
        self,
        *,
        project_id: str | None = None,
        global_only: bool = False,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[AiMemory]:
        stmt = select(AiMemory)
        if global_only:
            stmt = stmt.where(AiMemory.project_id.is_(None))
        elif project_id is not None:
            stmt = stmt.where(AiMemory.project_id == project_id)
        if kind is not None:
            stmt = stmt.where(AiMemory.kind == kind)

        # Confirmada antes de sugerida, e mais nova antes de mais velha: o que
        # alguém afirmou vale mais que o que ainda é palpite.
        stmt = stmt.order_by(
            AiMemory.confirmed_at.is_(None), AiMemory.updated_at.desc()
        ).limit(limit)
        return list(self.session.execute(stmt).scalars())

    def prune_unconfirmed(self, before: datetime) -> int:
        """Apaga sugestão que ninguém confirmou e já envelheceu."""
        alvos = self.session.execute(
            select(AiMemory).where(
                AiMemory.confirmed_at.is_(None), AiMemory.created_at < before
            )
        ).scalars()

        apagados = 0
        for registro in alvos:
            self.session.delete(registro)
            apagados += 1

        # `autoflush` está desligado nesta sessão: sem descarregar, a linha
        # apagada continua voltando na consulta seguinte, e a poda pareceria
        # não ter funcionado.
        self.session.flush()
        return apagados


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiMessage) -> AiMessage:
        self.session.add(registro)
        self.session.flush()
        return registro

    def list_for(self, session_id: str, limit: int = 50) -> list[AiMessage]:
        """As mensagens de uma sessão, em ordem de conversa.

        A consulta pega as **últimas** e devolve na ordem certa: numa conversa
        longa, o que interessa é o fim, mas ler de trás para a frente não é
        conversa.
        """
        stmt = (
            select(AiMessage)
            .where(AiMessage.session_id == session_id)
            .order_by(AiMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(list(self.session.execute(stmt).scalars())))


class UsageRepository:
    """Gasto por dia. Uma linha, criada na primeira chamada do dia."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _hoje() -> str:
        # Dia **local**: quem lê a tela pensa no próprio calendário, não em UTC.
        return utcnow().astimezone().date().isoformat()

    def today(self) -> AiUsageDay:
        dia = self._hoje()
        registro = self.session.get(AiUsageDay, dia)
        if registro is None:
            registro = AiUsageDay(day=dia)
            self.session.add(registro)
            self.session.flush()
        return registro

    def add(self, *, tokens_in: int = 0, tokens_out: int = 0) -> AiUsageDay:
        registro = self.today()
        registro.tokens_in += max(0, int(tokens_in))
        registro.tokens_out += max(0, int(tokens_out))
        registro.calls += 1
        self.session.flush()
        return registro

    def recent(self, days: int = 14) -> list[AiUsageDay]:
        stmt = select(AiUsageDay).order_by(AiUsageDay.day.desc()).limit(days)
        return list(self.session.execute(stmt).scalars())
