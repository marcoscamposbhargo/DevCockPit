"""Descoberta de projetos por varredura de diretório (FR-009 a FR-011).

Nota de sequenciamento: o roadmap prevê a varredura como job assíncrono, mas o
`JobManager` só chega na Fase 3a. Aqui ela é **síncrona e limitada** —
profundidade máxima, lista de ignorados e teto de candidatos —, o que satisfaz
NFR-011 ("nenhuma varredura síncrona e *ilimitada*"). Na Fase 3a vira job, e o
contrato HTTP muda de 200 para 202. Registrado como D-23.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import RootsConfig
from app.core.errors import PathNotAllowed
from app.core.paths import is_within, validate_project_dir
from app.detection.registry import DetectionRegistry, looks_like_project
from app.repositories.project_repository import ProjectRepository

DEFAULT_MARKERS = (
    ".git",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "docker-compose.yml",
    "compose.yml",
    "Dockerfile",
    "pom.xml",
    "build.gradle",
    "go.mod",
    "Cargo.toml",
)

MAX_CANDIDATES = 500


@dataclass
class Candidate:
    path: str
    suggested_name: str
    technologies: list[str]
    is_git_repo: bool
    already_registered: bool


@dataclass
class ScanResult:
    root: str
    scanned_dirs: int
    candidates: list[Candidate]
    truncated: bool
    skipped_dirs: list[str]


class DiscoveryService:
    def __init__(
        self,
        session: Session,
        roots: RootsConfig,
        registry: DetectionRegistry | None = None,
    ) -> None:
        self.repo = ProjectRepository(session)
        self.roots = roots
        self.registry = registry or DetectionRegistry()

    def scan(self, raw_root: str, max_depth: int | None = None) -> ScanResult:
        root = validate_project_dir(raw_root, self.roots.allowed_roots)
        depth_limit = max_depth if max_depth is not None else self.roots.scan_max_depth
        depth_limit = max(0, min(int(depth_limit), 6))

        ignore = set(self.roots.scan_ignore) or set()
        candidates: list[Candidate] = []
        skipped: list[str] = []
        scanned = 0
        truncated = False

        stack: list[tuple[Path, int]] = [(root, 0)]

        while stack:
            current, depth = stack.pop()
            scanned += 1

            try:
                entries = sorted(entry for entry in current.iterdir() if entry.is_dir())
            except (PermissionError, OSError):
                # Diretório sem permissão é registrado e ignorado, nunca aborta
                # a varredura inteira (US-023).
                skipped.append(current.as_posix())
                continue

            for entry in entries:
                if entry.name in ignore or entry.name.startswith("."):
                    continue

                if looks_like_project(entry, DEFAULT_MARKERS):
                    if len(candidates) >= MAX_CANDIDATES:
                        truncated = True
                        continue
                    candidates.append(self._describe(entry))
                    # Não desce em projeto encontrado: um monorepo vira um
                    # candidato, não trinta.
                    continue

                if depth + 1 <= depth_limit:
                    stack.append((entry, depth + 1))

        candidates.sort(key=lambda item: item.path.lower())
        return ScanResult(
            root=root.as_posix(),
            scanned_dirs=scanned,
            candidates=candidates,
            truncated=truncated,
            skipped_dirs=skipped[:20],
        )

    def _describe(self, path: Path) -> Candidate:
        detection = self.registry.run(path)
        stored = path.as_posix()
        return Candidate(
            path=stored,
            suggested_name=path.name,
            technologies=sorted({tech.name for tech in detection.technologies}),
            is_git_repo=(path / ".git").exists(),
            already_registered=self.repo.get_by_path(stored) is not None,
        )

    def assert_root_allowed(self, raw_root: str) -> Path:
        resolved = Path(raw_root).expanduser().resolve(strict=False)
        for root in self.roots.allowed_roots:
            if is_within(resolved, root):
                return resolved
        raise PathNotAllowed(f"O diretório {resolved} não está em nenhum root permitido.")
