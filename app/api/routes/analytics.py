"""Análise histórica: atividade, ações e disponibilidade."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analytics_service
from app.schemas.analytics import (
    ActionSummaryOut,
    ActivityDayOut,
    AnalyticsOut,
    ServiceUptimeOut,
    TechnologyOut,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsOut)
def analytics(
    service: AnalyticsService = Depends(get_analytics_service),
    days: int = Query(default=14, ge=1, le=90),
) -> AnalyticsOut:
    data = service.build(days=days)

    return AnalyticsOut(
        days=data.days,
        since=data.since,
        until=data.until,
        activity_daily=[
            ActivityDayOut(
                day=dia.day,
                success=dia.success,
                failed=dia.failed,
                timeout=dia.timeout,
                denied=dia.denied,
                total=dia.total,
            )
            for dia in data.activity_daily
        ],
        activity_by_hour=data.activity_by_hour,
        actions=[ActionSummaryOut(**vars(item)) for item in data.actions],
        technologies=[TechnologyOut(**vars(item)) for item in data.technologies],
        uptime=[ServiceUptimeOut(**vars(item)) for item in data.uptime],
        activity_total=data.activity_total,
        failure_rate=data.failure_rate,
        truncated=data.truncated,
        generated_at=data.generated_at,
        from_cache=data.from_cache,
    )
