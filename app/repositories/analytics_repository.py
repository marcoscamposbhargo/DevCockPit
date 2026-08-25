"""Leituras agregadas para a tela de análise.

As consultas devolvem **linhas cruas** dentro de uma janela, e quem agrega é o
serviço. A escolha é deliberada: o agrupamento por dia depende do fuso local de
quem olha a tela, e o banco guarda tudo em UTC. Fazer o bucket em SQL exigiria
`strftime` com deslocamento fixo — que erra no dia da virada de horário e não
sobrevive a uma troca de banco.

O volume permite: a janela padrão é de duas semanas e o teto de linhas é
explícito. Passando do teto a resposta diz que truncou, em vez de mentir por
omissão.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.project import ActivityLog, HealthSnapshot, Project, ProjectTechnology

#: Teto de linhas lidas por consulta. Duas semanas de uso pesado do painel não
#: chegam perto disso; um banco que passe daqui indica retenção quebrada, e a
#: tela precisa dizer isso em vez de travar carregando.
ROW_LIMIT = 50_000


@dataclass(frozen=True)
class ActivityRow:
    created_at: datetime
    action: str
    status: str
    duration_ms: int | None


@dataclass(frozen=True)
class HealthRow:
    project_id: str
    service_key: str
    state: str
    latency_ms: int | None
    checked_at: datetime


class AnalyticsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def activity_since(
        self, since: datetime, limit: int = ROW_LIMIT
    ) -> tuple[list[ActivityRow], bool]:
        stmt = (
            select(
                ActivityLog.created_at,
                ActivityLog.action,
                ActivityLog.status,
                ActivityLog.duration_ms,
            )
            .where(ActivityLog.created_at >= since)
            .order_by(ActivityLog.created_at)
            .limit(limit + 1)
        )
        linhas = [ActivityRow(*row) for row in self.session.execute(stmt)]
        truncado = len(linhas) > limit
        return linhas[:limit], truncado

    def health_since(self, since: datetime, limit: int = ROW_LIMIT) -> tuple[list[HealthRow], bool]:
        stmt = (
            select(
                HealthSnapshot.project_id,
                HealthSnapshot.service_key,
                HealthSnapshot.state,
                HealthSnapshot.latency_ms,
                HealthSnapshot.checked_at,
            )
            .where(HealthSnapshot.checked_at >= since)
            .order_by(
                HealthSnapshot.project_id,
                HealthSnapshot.service_key,
                HealthSnapshot.checked_at,
            )
            .limit(limit + 1)
        )
        linhas = [HealthRow(*row) for row in self.session.execute(stmt)]
        truncado = len(linhas) > limit
        return linhas[:limit], truncado

    def technology_counts(self) -> list[tuple[str, str, int]]:
        """(categoria, nome, projetos) — quantos projetos usam cada tecnologia."""
        stmt = (
            select(
                ProjectTechnology.category,
                ProjectTechnology.name,
                func.count(func.distinct(ProjectTechnology.project_id)),
            )
            .group_by(ProjectTechnology.category, ProjectTechnology.name)
            .order_by(func.count(func.distinct(ProjectTechnology.project_id)).desc())
        )
        return [(str(c), str(n), int(q)) for c, n, q in self.session.execute(stmt)]

    def project_names(self) -> dict[str, str]:
        return {
            str(pid): str(nome)
            for pid, nome in self.session.execute(select(Project.id, Project.name))
        }

    # --- poda ---

    def prune_activity(self, before: datetime) -> int:
        result = self.session.execute(delete(ActivityLog).where(ActivityLog.created_at < before))
        return int(result.rowcount or 0)

    def prune_health(self, before: datetime) -> int:
        result = self.session.execute(
            delete(HealthSnapshot).where(HealthSnapshot.checked_at < before)
        )
        return int(result.rowcount or 0)
