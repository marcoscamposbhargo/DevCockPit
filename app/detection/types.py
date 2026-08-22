"""Tipos compartilhados pelos detectores.

Um detector responde a uma pergunta simples: "este diretório carrega a marca
X?". Ele não conhece banco, HTTP nem `subprocess` — só lê arquivo de manifesto
conhecido (defesa D9: superfície mínima de leitura).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class Category:
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    RUNTIME = "runtime"
    DATABASE = "database"
    TOOLING = "tooling"


@dataclass(frozen=True)
class DetectedTech:
    name: str
    category: str
    evidence: str

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass(frozen=True)
class SuggestedService:
    key: str
    label: str
    port: int | None = None
    url: str | None = None
    health_kind: str = "TCP"


@dataclass
class Detection:
    technologies: list[DetectedTech] = field(default_factory=list)
    services: list[SuggestedService] = field(default_factory=list)
    compose_file: str | None = None
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: Detection) -> None:
        known = {tech.name for tech in self.technologies}
        self.technologies.extend(t for t in other.technologies if t.name not in known)

        keys = {service.key for service in self.services}
        self.services.extend(s for s in other.services if s.key not in keys)

        self.compose_file = self.compose_file or other.compose_file
        self.warnings.extend(other.warnings)


class Detector(Protocol):
    name: str

    def detect(self, project_dir: Path) -> Detection | None: ...
