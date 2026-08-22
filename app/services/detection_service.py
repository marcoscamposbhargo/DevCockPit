"""Aplica a detecção ao projeto cadastrado (FR-020, FR-024, FR-025).

Regra que define o comportamento: **edição manual do usuário vence sempre**.
Uma nova detecção substitui apenas linhas `DETECTED`; o que o usuário marcou
como `MANUAL` nunca é desfeito.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.detection.registry import DetectionRegistry
from app.models.project import (
    ActivityStatus,
    Project,
    ProjectTechnology,
    TechnologySource,
)
from app.models.project import (
    ProjectService as ProjectServiceModel,
)
from app.services.activity_service import ActivityService


@dataclass
class DetectionDiff:
    added: list[str]
    removed: list[str]
    kept_manual: list[str]
    services_added: list[str]
    compose_file: str | None
    warnings: list[str]
    skipped: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.services_added)


class DetectionService:
    def __init__(
        self,
        session: Session,
        registry: DetectionRegistry | None = None,
        activity: ActivityService | None = None,
    ) -> None:
        self.session = session
        self.registry = registry or DetectionRegistry()
        self.activity = activity or ActivityService(session)

    def run_for(self, project: Project, *, record: bool = True) -> DetectionDiff:
        if project.detection_locked:
            diff = DetectionDiff([], [], [], [], None, [], skipped=True)
            if record:
                self.activity.record(
                    action="project.detect",
                    status=ActivityStatus.SUCCESS,
                    project_id=project.id,
                    message="Detecção ignorada: o projeto está com a stack travada.",
                )
            return diff

        detection = self.registry.run(Path(project.path))

        manual = {
            tech.name: tech
            for tech in project.technologies
            if tech.source == TechnologySource.MANUAL.value
        }
        previous_detected = {
            tech.name: tech
            for tech in project.technologies
            if tech.source == TechnologySource.DETECTED.value
        }
        found = {tech.name: tech for tech in detection.technologies}

        for name, tech in previous_detected.items():
            if name not in found:
                project.technologies.remove(tech)
                self.session.delete(tech)

        added: list[str] = []
        for name, tech in found.items():
            if name in manual or name in previous_detected:
                continue
            project.technologies.append(
                ProjectTechnology(
                    name=name,
                    category=tech.category,
                    source=TechnologySource.DETECTED.value,
                    evidence=tech.evidence,
                )
            )
            added.append(name)

        services_added = self._apply_services(project, detection.services)

        diff = DetectionDiff(
            added=sorted(added),
            removed=sorted(name for name in previous_detected if name not in found),
            kept_manual=sorted(manual),
            services_added=sorted(services_added),
            compose_file=detection.compose_file,
            warnings=detection.warnings,
        )

        if record:
            self.activity.record(
                action="project.detect",
                status=ActivityStatus.SUCCESS,
                project_id=project.id,
                message=_summary(diff),
            )
        return diff

    def _apply_services(self, project: Project, suggestions: list) -> list[str]:
        """Só adiciona serviço que ainda não existe. Nunca sobrescreve o do usuário."""
        existing = {service.key for service in project.services}
        added: list[str] = []

        for suggestion in suggestions:
            if suggestion.key in existing:
                continue
            project.services.append(
                ProjectServiceModel(
                    key=suggestion.key,
                    label=suggestion.label,
                    port=suggestion.port,
                    url=suggestion.url,
                    health_url=suggestion.url if suggestion.health_kind == "HTTP" else None,
                    health_kind=suggestion.health_kind,
                )
            )
            existing.add(suggestion.key)
            added.append(suggestion.key)

        return added


def _summary(diff: DetectionDiff) -> str:
    if not diff.changed:
        return "Detecção executada; nada mudou."
    parts = []
    if diff.added:
        parts.append(f"+{len(diff.added)} tecnologia(s): {', '.join(diff.added)}")
    if diff.removed:
        parts.append(f"-{len(diff.removed)}: {', '.join(diff.removed)}")
    if diff.services_added:
        parts.append(f"+{len(diff.services_added)} serviço(s)")
    return "; ".join(parts)
