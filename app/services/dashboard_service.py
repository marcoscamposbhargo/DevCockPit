"""Agregação do dashboard (FR-080 a FR-084).

Regra: **nada aqui toca disco, Git ou Docker**. Só banco e cache. Se um dado
não estiver no cache, aparece como desconhecido — não se paga o custo de
buscá-lo no caminho da requisição (NFR-010, NFR-011).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.models.base import utcnow
from app.models.project import Project, ProjectStatus
from app.repositories.project_repository import ProjectRepository
from app.services.health_service import HealthService, HealthState


@dataclass
class PendingChange:
    project_id: str
    name: str
    branch: str | None
    dirty_count: int


@dataclass
class ActiveService:
    project_id: str
    project_name: str
    label: str
    url: str | None
    port: int | None
    state: str


@dataclass
class PortConflict:
    port: int
    projects: list[str]


@dataclass
class RecentProject:
    id: str
    name: str
    status: str
    last_accessed_at: datetime | None


@dataclass
class Dashboard:
    totals: dict[str, int] = field(default_factory=dict)
    pending_changes: list[PendingChange] = field(default_factory=list)
    active_services: list[ActiveService] = field(default_factory=list)
    port_conflicts: list[PortConflict] = field(default_factory=list)
    recent_projects: list[RecentProject] = field(default_factory=list)
    generated_at: datetime = field(default_factory=utcnow)
    from_cache: bool = False


CACHE_KEY = "dashboard"


class DashboardService:
    def __init__(
        self,
        session: Session,
        cache: TTLCache,
        health: HealthService,
    ) -> None:
        self.repo = ProjectRepository(session)
        self.cache = cache
        self.health = health

    def build(self) -> Dashboard:
        cached = self.cache.get(CACHE_KEY)
        if cached is not None:
            cached.from_cache = True
            return cached

        projects, total = self.repo.list(limit=500)

        dashboard = Dashboard(
            totals=self._totals(projects, total),
            pending_changes=self._pending_changes(projects),
            active_services=self._active_services(projects),
            port_conflicts=self._port_conflicts(projects),
            recent_projects=self._recent(projects),
            from_cache=False,
        )
        self.cache.set(CACHE_KEY, dashboard)
        return dashboard

    def invalidate(self) -> None:
        self.cache.invalidate(CACHE_KEY)

    # --- blocos ---

    def _totals(self, projects: list[Project], total: int) -> dict[str, int]:
        by_status: dict[str, int] = defaultdict(int)
        for project in projects:
            by_status[project.status] += 1

        com_docker = sum(
            1
            for project in projects
            if any(tech.name in ("docker", "docker-compose") for tech in project.technologies)
        )

        return {
            "projects": total,
            "running": by_status.get(ProjectStatus.RUNNING.value, 0),
            "stopped": by_status.get(ProjectStatus.STOPPED.value, 0)
            + by_status.get(ProjectStatus.REGISTERED.value, 0),
            "missing": by_status.get(ProjectStatus.MISSING.value, 0),
            "with_docker": com_docker,
            "pinned": sum(1 for project in projects if project.is_pinned),
        }

    def _pending_changes(self, projects: list[Project]) -> list[PendingChange]:
        """Lê do cache de Git preenchido pelas consultas já feitas.

        Sem cache, o campo fica vazio em vez de disparar `git status` para cada
        projeto — o que é justamente o que travaria a tela.
        """
        pendentes: list[PendingChange] = []

        for project in projects:
            status = self.cache.get(f"git.status:{project.id}")
            if status is None or not getattr(status, "is_repo", False):
                continue
            if status.dirty_count > 0:
                pendentes.append(
                    PendingChange(
                        project_id=project.id,
                        name=project.name,
                        branch=status.current_branch,
                        dirty_count=status.dirty_count,
                    )
                )

        return sorted(pendentes, key=lambda item: item.dirty_count, reverse=True)[:10]

    def _active_services(self, projects: list[Project]) -> list[ActiveService]:
        ativos: list[ActiveService] = []

        for project in projects:
            for service in project.services:
                resultado = self.health.last_known(project.id, service.key)
                if resultado.state != HealthState.ONLINE:
                    continue
                ativos.append(
                    ActiveService(
                        project_id=project.id,
                        project_name=project.name,
                        label=service.label,
                        url=service.url,
                        port=service.port,
                        state=resultado.state.value,
                    )
                )

        return ativos[:20]

    def _port_conflicts(self, projects: list[Project]) -> list[PortConflict]:
        """Duas coisas disputando a mesma porta é a dor que aparece na hora errada."""
        por_porta: dict[int, set[str]] = defaultdict(set)

        for project in projects:
            for service in project.services:
                if service.port:
                    por_porta[service.port].add(project.name)

        return [
            PortConflict(port=porta, projects=sorted(nomes))
            for porta, nomes in sorted(por_porta.items())
            if len(nomes) > 1
        ]

    def _recent(self, projects: list[Project]) -> list[RecentProject]:
        com_acesso = [p for p in projects if p.last_accessed_at is not None]
        com_acesso.sort(key=lambda p: p.last_accessed_at, reverse=True)  # type: ignore[arg-type,return-value]

        return [
            RecentProject(
                id=project.id,
                name=project.name,
                status=project.status,
                last_accessed_at=project.last_accessed_at,
            )
            for project in com_acesso[:8]
        ]
