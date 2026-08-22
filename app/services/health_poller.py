"""Poller de health em background (FR-062).

Existe para que a API responda de cache. É a peça que faz o dashboard caber em
500 ms com 30 projetos, em vez de disparar dezenas de conexões por carga de
tela (NFR-010, NFR-011).

Falha do poller nunca derruba a aplicação: erro é registrado e a próxima volta
tenta de novo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy.orm import sessionmaker

from app.repositories.project_repository import ProjectRepository
from app.services.health_service import (
    HealthService,
    should_poll,
    targets_from_project,
)

logger = logging.getLogger(__name__)


class HealthPoller:
    def __init__(
        self,
        session_factory: sessionmaker,
        health: HealthService,
        interval_s: float = 30.0,
        recent_days: int = 7,
    ) -> None:
        self.session_factory = session_factory
        self.health = health
        self.interval_s = interval_s
        self.recent_days = recent_days
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "poller de health iniciado",
            extra={"extra_fields": {"interval_s": self.interval_s}},
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:  # noqa: BLE001 - o poller não pode derrubar o servidor
                logger.exception("ciclo do poller falhou")

            with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)

    async def run_once(self) -> int:
        """Verifica os projetos elegíveis. Devolve quantos serviços checou."""
        targets = await asyncio.to_thread(self._collect_targets)
        if not targets:
            return 0

        await self.health.check_many(targets)
        return len(targets)

    def _collect_targets(self) -> list:
        """Lê o banco numa thread: sessão do SQLAlchemy é síncrona."""
        session = self.session_factory()
        try:
            projects, _ = ProjectRepository(session).list(limit=500)
            targets: list = []
            for project in projects:
                if should_poll(project, self.recent_days):
                    targets.extend(targets_from_project(project))
            return targets
        finally:
            session.close()
