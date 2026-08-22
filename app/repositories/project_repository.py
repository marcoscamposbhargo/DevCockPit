"""Acesso a dados de projeto. Nenhuma query SQL fora desta camada (ADR-002)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectStatus, ProjectTechnology, utcnow


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- leitura ---

    def get(self, project_id: str) -> Project | None:
        return self.session.get(Project, project_id)

    def get_by_path(self, path: str) -> Project | None:
        stmt = select(Project).where(Project.path == path)
        return self.session.execute(stmt).scalar_one_or_none()

    def id_exists(self, project_id: str) -> bool:
        return self.session.get(Project, project_id) is not None

    def list(
        self,
        *,
        status: str | None = None,
        tech: str | None = None,
        pinned: bool | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        stmt = select(Project)

        if status is not None:
            stmt = stmt.where(Project.status == status)
        if pinned is not None:
            stmt = stmt.where(Project.is_pinned.is_(pinned))
        if tech is not None:
            stmt = stmt.where(
                Project.id.in_(
                    select(ProjectTechnology.project_id).where(ProjectTechnology.name == tech)
                )
            )
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(
                func.lower(Project.name).like(pattern) | func.lower(Project.path).like(pattern)
            )

        total = self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()

        stmt = stmt.order_by(
            Project.is_pinned.desc(),
            Project.last_accessed_at.desc().nulls_last(),
            Project.name.asc(),
        ).limit(limit).offset(offset)

        return list(self.session.execute(stmt).scalars()), int(total)

    def count_by_status(self) -> dict[str, int]:
        stmt = select(Project.status, func.count()).group_by(Project.status)
        return {row[0]: int(row[1]) for row in self.session.execute(stmt)}

    # --- escrita ---

    def add(self, project: Project) -> Project:
        self.session.add(project)
        self.session.flush()
        return project

    def delete(self, project: Project) -> None:
        self.session.delete(project)

    def touch_access(self, project: Project, when: datetime | None = None) -> None:
        project.last_accessed_at = when or utcnow()

    def set_status(self, project: Project, status: ProjectStatus) -> None:
        project.status = status.value
