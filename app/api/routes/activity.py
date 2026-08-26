"""Rota do log de auditoria (FR-102)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_activity_service
from app.schemas.project import ActivityList, ActivityOut
from app.services.activity_service import ActivityService

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=ActivityList)
def list_activity(
    service: ActivityService = Depends(get_activity_service),
    project_id: str | None = Query(default=None),
    action: str | None = Query(default=None, max_length=60),
    status: str | None = Query(default=None, max_length=10),
    actor: str | None = Query(default=None, max_length=10),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ActivityList:
    entries, total = service.list(
        project_id=project_id,
        action=action,
        status=status,
        actor=actor,
        limit=limit,
        offset=offset,
    )
    return ActivityList(items=[ActivityOut.model_validate(e) for e in entries], total=total)
