"""Schemas de serviços, health, dashboard e ações de sistema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.project import ServiceIn


class ServiceStateOut(BaseModel):
    key: str
    label: str
    host: str
    port: int | None = None
    url: str | None = None
    health_kind: str
    state: str
    latency_ms: int | None = None
    detail: str | None = None
    checked_at: datetime | None = None


class ServiceList(BaseModel):
    items: list[ServiceStateOut] = Field(default_factory=list)


class ServicesReplace(BaseModel):
    items: list[ServiceIn] = Field(default_factory=list, max_length=50)


class PortUsage(BaseModel):
    port: int
    projects: list[str]
    conflict: bool


class PortBinding(BaseModel):
    """Quem ocupa a porta, no detalhe que a tela precisa para editá-la.

    `PortUsage` responde "esta porta está em conflito?" com nomes de projeto.
    Para *trocar* a porta a tela precisa do id do projeto e da chave do
    serviço — sem isso ela teria que buscar cada projeto para descobrir a
    quem a porta pertence.
    """

    project_id: str
    project_name: str
    service_key: str
    service_label: str
    host: str
    port: int
    url: str | None = None
    conflict: bool = False


class PortMap(BaseModel):
    items: list[PortUsage] = Field(default_factory=list)
    bindings: list[PortBinding] = Field(default_factory=list)
    conflicts: int = 0


class OpenBrowserRequest(BaseModel):
    #: Chave do serviço, nunca a URL (decisão D-13).
    service_key: str = Field(min_length=1, max_length=32)


class OpenResult(BaseModel):
    opened: bool
    action: str
    detail: str | None = None


# --- dashboard ---


class TotalsOut(BaseModel):
    projects: int = 0
    running: int = 0
    stopped: int = 0
    missing: int = 0
    with_docker: int = 0
    pinned: int = 0


class PendingChangeOut(BaseModel):
    project_id: str
    name: str
    branch: str | None = None
    dirty_count: int


class ActiveServiceOut(BaseModel):
    project_id: str
    project_name: str
    label: str
    url: str | None = None
    port: int | None = None
    state: str


class PortConflictOut(BaseModel):
    port: int
    projects: list[str]


class RecentProjectOut(BaseModel):
    id: str
    name: str
    status: str
    last_accessed_at: datetime | None = None


class DashboardOut(BaseModel):
    totals: TotalsOut
    pending_changes: list[PendingChangeOut] = Field(default_factory=list)
    active_services: list[ActiveServiceOut] = Field(default_factory=list)
    port_conflicts: list[PortConflictOut] = Field(default_factory=list)
    recent_projects: list[RecentProjectOut] = Field(default_factory=list)
    generated_at: datetime
    #: Explícito de propósito: a UI mostra a idade do dado em vez de fingir
    #: tempo real (decisão D-18).
    from_cache: bool
