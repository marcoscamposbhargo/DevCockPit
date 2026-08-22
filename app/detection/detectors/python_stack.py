"""Detectores de projeto Python."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from app.detection.types import Category, DetectedTech, Detection, SuggestedService

# framework -> (nome exibido, porta convencional)
PY_FRAMEWORKS: dict[str, tuple[str, int | None]] = {
    "fastapi": ("fastapi", 8000),
    "django": ("django", 8000),
    "flask": ("flask", 5000),
    "starlette": ("starlette", 8000),
    "uvicorn": ("uvicorn", None),
    "gunicorn": ("gunicorn", None),
    "streamlit": ("streamlit", 8501),
    "celery": ("celery", None),
}

PY_DATABASES = {
    "psycopg": "postgresql",
    "psycopg2": "postgresql",
    "asyncpg": "postgresql",
    "pymysql": "mysql",
    "duckdb": "duckdb",
    "redis": "redis",
    "pymongo": "mongodb",
}

_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9._-]+)")


def _classify(packages: set[str], evidence: str) -> Detection:
    detection = Detection(
        technologies=[DetectedTech("python", Category.LANGUAGE, evidence)]
    )

    for package in sorted(packages):
        key = package.lower()

        if key in PY_FRAMEWORKS:
            label, port = PY_FRAMEWORKS[key]
            detection.technologies.append(DetectedTech(label, Category.FRAMEWORK, evidence))
            if port and not any(s.key == "backend" for s in detection.services):
                detection.services.append(
                    SuggestedService(
                        key="backend",
                        label="Backend",
                        port=port,
                        url=f"http://localhost:{port}",
                        health_kind="HTTP",
                    )
                )

        if key in PY_DATABASES:
            detection.technologies.append(
                DetectedTech(PY_DATABASES[key], Category.DATABASE, evidence)
            )

    return detection


class RequirementsDetector:
    name = "python_requirements"

    def detect(self, project_dir: Path) -> Detection | None:
        target = project_dir / "requirements.txt"
        if not target.is_file():
            return None

        packages: set[str] = set()
        try:
            for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith(("#", "-")):
                    continue
                match = _REQUIREMENT.match(line)
                if match:
                    packages.add(match.group(1))
        except OSError:
            return Detection(
                technologies=[DetectedTech("python", Category.LANGUAGE, "requirements.txt")],
                warnings=["Não foi possível ler requirements.txt."],
            )

        return _classify(packages, "requirements.txt")


class PyprojectDetector:
    name = "python_pyproject"

    def detect(self, project_dir: Path) -> Detection | None:
        target = project_dir / "pyproject.toml"
        if not target.is_file():
            return None

        try:
            data = tomllib.loads(target.read_text(encoding="utf-8", errors="replace"))
        except (tomllib.TOMLDecodeError, OSError):
            return Detection(
                technologies=[DetectedTech("python", Category.LANGUAGE, "pyproject.toml")],
                warnings=["pyproject.toml inválido; só a linguagem foi detectada."],
            )

        packages: set[str] = set()
        project = data.get("project") or {}

        for entry in project.get("dependencies") or []:
            match = _REQUIREMENT.match(str(entry))
            if match:
                packages.add(match.group(1))

        for group in (project.get("optional-dependencies") or {}).values():
            for entry in group:
                match = _REQUIREMENT.match(str(entry))
                if match:
                    packages.add(match.group(1))

        poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        packages.update(str(key) for key in poetry if str(key).lower() != "python")

        return _classify(packages, "pyproject.toml")
