"""Contratos da tela de análise."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ActivityDayOut(BaseModel):
    day: str
    success: int
    failed: int
    timeout: int
    denied: int
    total: int


class ActionSummaryOut(BaseModel):
    action: str
    total: int
    failures: int
    error_rate: float
    p50_ms: int | None
    p95_ms: int | None


class TechnologyOut(BaseModel):
    category: str
    name: str
    projects: int


class ServiceUptimeOut(BaseModel):
    project_id: str
    project_name: str
    service_key: str
    samples: int
    #: `None` quando não há amostra suficiente. Ausência de dado não é 0% nem
    #: 100% — as duas leituras seriam afirmação sem lastro.
    uptime_pct: float | None
    coverage_pct: float
    last_state: str
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    latency_series: list[float | None]


class AnalyticsOut(BaseModel):
    days: int
    since: datetime
    until: datetime
    activity_daily: list[ActivityDayOut] = Field(default_factory=list)
    activity_by_hour: list[int] = Field(default_factory=list)
    actions: list[ActionSummaryOut] = Field(default_factory=list)
    technologies: list[TechnologyOut] = Field(default_factory=list)
    uptime: list[ServiceUptimeOut] = Field(default_factory=list)
    activity_total: int
    failure_rate: float
    truncated: bool
    generated_at: datetime
    from_cache: bool
