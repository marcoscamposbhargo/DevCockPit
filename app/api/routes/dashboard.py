"""Dashboard agregado (FR-080 a FR-084)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_dashboard_service
from app.schemas.health import (
    ActiveServiceOut,
    DashboardOut,
    PendingChangeOut,
    PortConflictOut,
    RecentProjectOut,
    TotalsOut,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(service: DashboardService = Depends(get_dashboard_service)) -> DashboardOut:
    data = service.build()

    return DashboardOut(
        totals=TotalsOut(**data.totals),
        pending_changes=[PendingChangeOut(**vars(item)) for item in data.pending_changes],
        active_services=[ActiveServiceOut(**vars(item)) for item in data.active_services],
        port_conflicts=[PortConflictOut(**vars(item)) for item in data.port_conflicts],
        recent_projects=[RecentProjectOut(**vars(item)) for item in data.recent_projects],
        # Sem isto o campo saía sempre vazio, e toda tela lia "ninguém mediu"
        # — inclusive para projeto recém-verificado. O serviço calculava, o
        # schema declarava, e a rota esquecia de passar.
        checked_project_ids=data.checked_project_ids,
        generated_at=data.generated_at,
        from_cache=data.from_cache,
    )
