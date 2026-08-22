"""Casos de uso de Git (FR-030 a FR-039). Somente leitura, sempre."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from app.adapters.git.adapter import GitAdapter
from app.adapters.git.models import GitStatus, provider_from_url
from app.core.cache import TTLCache
from app.core.errors import ProjectDirMissing


class GitService:
    def __init__(self, adapter: GitAdapter, cache: TTLCache) -> None:
        self.adapter = adapter
        self.cache = cache

    def _project_dir(self, path: str) -> Path:
        project_dir = Path(path)
        if not project_dir.is_dir():
            raise ProjectDirMissing(f"O diretório {path} não existe mais.")
        return project_dir

    def status(self, project_id: str, path: str, file_limit: int = 50) -> GitStatus:
        key = f"git.status:{project_id}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        result = self.adapter.status(self._project_dir(path), file_limit=file_limit)
        self.cache.set(key, result)
        return result

    def commits(self, project_id: str, path: str, limit: int = 20) -> list[dict]:
        key = f"git.log:{project_id}:{limit}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        project_dir = self._project_dir(path)
        if not self.adapter.is_repo(project_dir):
            self.cache.set(key, [])
            return []

        commits = [
            {**asdict(commit), "date": commit.date.isoformat() if commit.date else None}
            for commit in self.adapter.log(project_dir, limit=limit)
        ]
        self.cache.set(key, commits)
        return commits

    def branches(self, project_id: str, path: str) -> list[str]:
        key = f"git.branches:{project_id}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        project_dir = self._project_dir(path)
        branches = self.adapter.branches(project_dir) if self.adapter.is_repo(project_dir) else []
        self.cache.set(key, branches)
        return branches

    def remotes(self, project_id: str, path: str) -> list[dict]:
        key = f"git.remotes:{project_id}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        project_dir = self._project_dir(path)
        found = self.adapter.remotes(project_dir) if self.adapter.is_repo(project_dir) else []
        remotes = [
            {"name": remote.name, "url": remote.url, "provider": provider_from_url(remote.url)}
            for remote in found
        ]
        self.cache.set(key, remotes)
        return remotes

    def invalidate(self, project_id: str) -> None:
        for prefix in ("git.status:", "git.log:", "git.branches:", "git.remotes:"):
            self.cache.invalidate_prefix(f"{prefix}{project_id}")
