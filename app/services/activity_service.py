"""Auditoria — escrita e leitura do log de ações (FR-100 a FR-103)."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.logging import get_correlation_id, redact_argv
from app.models.project import ActivityLog, ActivityStatus
from app.repositories.activity_repository import ActivityRepository


class ActivityService:
    def __init__(self, session: Session) -> None:
        self.repo = ActivityRepository(session)

    def record(
        self,
        *,
        action: str,
        status: ActivityStatus,
        project_id: str | None = None,
        duration_ms: int | None = None,
        exit_code: int | None = None,
        argv: list[str] | None = None,
        message: str | None = None,
    ) -> ActivityLog:
        entry = ActivityLog(
            project_id=project_id,
            action=action,
            status=status.value,
            duration_ms=duration_ms,
            exit_code=exit_code,
            argv=json.dumps(redact_argv(argv), ensure_ascii=False) if argv else None,
            message=message,
            correlation_id=get_correlation_id(),
        )
        return self.repo.add(entry)

    def record_denied(self, *, action: str, message: str, project_id: str | None = None) -> None:
        """Ação recusada pela allowlist.

        É o sinal mais importante do sistema: significa tentativa de ação não
        prevista (`docs/07-security-model.md`).
        """
        self.record(
            action=action,
            status=ActivityStatus.DENIED,
            project_id=project_id,
            message=message,
        )

    def list(
        self,
        *,
        project_id: str | None = None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActivityLog], int]:
        return self.repo.list(
            project_id=project_id,
            action=action,
            status=status,
            limit=limit,
            offset=offset,
        )
