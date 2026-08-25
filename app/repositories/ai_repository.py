"""Acesso a dados de sessão e memória."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai import AiMemory, AiSession


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
