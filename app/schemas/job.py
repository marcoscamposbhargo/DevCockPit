"""Schemas de job."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.jobs.job import JobStatus


class JobOut(BaseModel):
    id: str
    action: str
    project_id: str | None = None
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    message: str | None = None
    output: str = ""
    #: Número de linhas já produzidas. O cliente manda de volta em `after`
    #: para receber só o que falta.
    revision: int = 0
    line_count: int = 0
    output_truncated: bool = False


class JobList(BaseModel):
    items: list[JobOut] = Field(default_factory=list)


class JobAccepted(BaseModel):
    job_id: str
    action: str
    status: JobStatus
