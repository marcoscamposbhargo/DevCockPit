"""Poda das tabelas que crescem sozinhas.

`activity_retention_days` estava configurado desde a Fase 0 e **nunca era
consultado**: o log de auditoria crescia sem limite num banco que vive na
máquina do usuário. Com o histórico de health passando a ser gravado, seriam
duas tabelas na mesma situação.

A poda roda dentro do poller, que já é o laço de background da aplicação — um
segundo laço só para apagar linha seria mais peça para manter e mais um lugar
onde uma exceção pode ficar em silêncio.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from app.models.base import session_scope, utcnow
from app.repositories.analytics_repository import AnalyticsRepository

logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        activity_days: int = 90,
        health_days: int = 14,
        interval_s: float = 3600.0,
    ) -> None:
        self.session_factory = session_factory
        self.activity_days = activity_days
        self.health_days = health_days
        self.interval_s = interval_s
        self._ultima_poda: float | None = None

    def prune_if_due(self) -> dict[str, int] | None:
        """Poda se já passou o intervalo. Devolve o que apagou, ou `None`."""
        agora = utcnow().timestamp()
        if self._ultima_poda is not None and (agora - self._ultima_poda) < self.interval_s:
            return None
        self._ultima_poda = agora
        return self.prune()

    def prune(self) -> dict[str, int]:
        agora = utcnow()
        with session_scope(self.session_factory) as session:
            repo = AnalyticsRepository(session)
            apagados = {
                "activity": repo.prune_activity(agora - timedelta(days=self.activity_days)),
                "health": repo.prune_health(agora - timedelta(days=self.health_days)),
            }

        if any(apagados.values()):
            logger.info("poda de retenção", extra={"extra_fields": apagados})
        return apagados
