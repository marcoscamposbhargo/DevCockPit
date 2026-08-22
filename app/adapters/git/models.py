"""Objetos de domínio do Git. Sem SQLAlchemy, sem Pydantic — só dados."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ChangedFile:
    path: str
    change: str  # modified | added | deleted | renamed | untracked | conflicted
    staged: bool


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str
    date: datetime | None
    subject: str


@dataclass(frozen=True)
class Remote:
    name: str
    url: str


@dataclass
class GitStatus:
    is_repo: bool
    #: Raiz do repositório que contém o diretório, quando existe.
    repo_root: str | None = None
    #: True quando o diretório está DENTRO de um repositório cuja raiz é outra.
    #: Ver `GitAdapter.locate_repo` para o motivo de isso importar.
    inside_other_repo: bool = False
    current_branch: str | None = None
    detached: bool = False
    head_sha: str | None = None
    ahead: int | None = None
    behind: int | None = None
    counts: dict[str, int] = field(default_factory=dict)
    files: list[ChangedFile] = field(default_factory=list)
    files_truncated: bool = False

    @property
    def dirty_count(self) -> int:
        return sum(self.counts.values())


def provider_from_url(url: str | None) -> str | None:
    if not url:
        return None
    lowered = url.lower()
    if "github.com" in lowered:
        return "github"
    if "gitlab" in lowered:
        return "gitlab"
    if "bitbucket" in lowered:
        return "bitbucket"
    return "other"
