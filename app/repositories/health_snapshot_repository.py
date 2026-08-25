"""Escrita e leitura do histórico de verificação de serviços."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import HealthSnapshot


class HealthSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def last_per_service(self) -> dict[tuple[str, str], tuple[str, datetime]]:
        """Último estado gravado por (projeto, serviço).

        Serve à política de escrita: só grava quem mudou ou quem está sem
        registro há tempo demais. Ler o último de cada um custa uma consulta;
        gravar tudo a cada 30 s custaria 2.880 linhas por serviço por dia.
        """
        stmt = select(
            HealthSnapshot.project_id,
            HealthSnapshot.service_key,
            HealthSnapshot.state,
            HealthSnapshot.checked_at,
        ).order_by(HealthSnapshot.checked_at)

        ultimo: dict[tuple[str, str], tuple[str, datetime]] = {}
        for project_id, service_key, state, checked_at in self.session.execute(stmt):
            ultimo[(str(project_id), str(service_key))] = (str(state), checked_at)
        return ultimo

    def add_many(self, snapshots: list[HealthSnapshot]) -> int:
        if not snapshots:
            return 0
        self.session.add_all(snapshots)
        self.session.flush()
        return len(snapshots)
