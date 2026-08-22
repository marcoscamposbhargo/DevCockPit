"""Schemas de Git, detecção e descoberta."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChangedFileOut(BaseModel):
    path: str
    change: str
    staged: bool


class CommitOut(BaseModel):
    sha: str
    author: str
    date: datetime | None = None
    subject: str


class GitStatusOut(BaseModel):
    is_repo: bool
    repo_root: str | None = None
    inside_other_repo: bool = False
    current_branch: str | None = None
    detached: bool = False
    head_sha: str | None = None
    ahead: int | None = None
    behind: int | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    dirty_count: int = 0
    files: list[ChangedFileOut] = Field(default_factory=list)
    files_truncated: bool = False
    checked_at: datetime


class CommitList(BaseModel):
    items: list[CommitOut]


class BranchList(BaseModel):
    items: list[str]
    current: str | None = None


class RemoteOut(BaseModel):
    name: str
    url: str
    provider: str | None = None


class RemoteList(BaseModel):
    items: list[RemoteOut]


class DetectionResult(BaseModel):
    skipped: bool = False
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    kept_manual: list[str] = Field(default_factory=list)
    services_added: list[str] = Field(default_factory=list)
    compose_file: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ScanRequest(BaseModel):
    root: str = Field(min_length=1, max_length=500)
    max_depth: int | None = Field(default=None, ge=0, le=6)


class CandidateOut(BaseModel):
    path: str
    suggested_name: str
    technologies: list[str]
    is_git_repo: bool
    already_registered: bool


class ScanResponse(BaseModel):
    root: str
    scanned_dirs: int
    truncated: bool
    skipped_dirs: list[str]
    items: list[CandidateOut]


class ImportRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=200)


class ImportItemResult(BaseModel):
    path: str
    ok: bool
    project_id: str | None = None
    error_code: str | None = None
    message: str | None = None


class ImportResponse(BaseModel):
    imported: int
    failed: int
    items: list[ImportItemResult]
