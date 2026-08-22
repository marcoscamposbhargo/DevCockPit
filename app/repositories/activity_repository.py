"""Acesso a dados do log de auditoria."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import ActivityLog


class ActivityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: ActivityLog) -> ActivityLog:
        self.session.add(entry)
        self.session.flush()
        return entry

    def list(
        self,
        *,
        project_id: str | None = None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActivityLog], int]:
        stmt = select(ActivityLog)
        if project_id is not None:
            stmt = stmt.where(ActivityLog.project_id == project_id)
        if action is not None:
            stmt = stmt.where(ActivityLog.action == action)
        if status is not None:
            stmt = stmt.where(ActivityLog.status == status)

        total = self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()

        stmt = stmt.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars()), int(total)
