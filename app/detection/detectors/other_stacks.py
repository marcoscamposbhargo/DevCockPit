"""Detectores das demais stacks do MVP (FR-021)."""

from __future__ import annotations

from pathlib import Path

from app.detection.types import Category, DetectedTech, Detection


class _MarkerDetector:
    """Detector por presença de arquivo, sem leitura de conteúdo."""

    name = "marker"
    marker = ""
    technologies: tuple[tuple[str, str], ...] = ()

    def detect(self, project_dir: Path) -> Detection | None:
        if not (project_dir / self.marker).is_file():
            return None
        return Detection(
            technologies=[
                DetectedTech(name, category, self.marker) for name, category in self.technologies
            ]
        )


class MavenDetector(_MarkerDetector):
    name = "java_maven"
    marker = "pom.xml"
    technologies = (("java", Category.LANGUAGE), ("maven", Category.TOOLING))


class GradleDetector:
    name = "java_gradle"

    def detect(self, project_dir: Path) -> Detection | None:
        for marker in ("build.gradle", "build.gradle.kts"):
            if (project_dir / marker).is_file():
                return Detection(
                    technologies=[
                        DetectedTech("java", Category.LANGUAGE, marker),
                        DetectedTech("gradle", Category.TOOLING, marker),
                    ]
                )
        return None


class GoDetector(_MarkerDetector):
    name = "go_mod"
    marker = "go.mod"
    technologies = (("go", Category.LANGUAGE),)


class RustDetector(_MarkerDetector):
    name = "rust_cargo"
    marker = "Cargo.toml"
    technologies = (("rust", Category.LANGUAGE),)


class StaticHtmlDetector:
    """Último recurso: só marca HTML estático quando nada mais foi detectado.

    O registry passa `already_detected` para evitar rotular um projeto Next.js
    como "site estático" por causa de um `index.html` de template.
    """

    name = "static_html"

    def detect(self, project_dir: Path) -> Detection | None:
        if not (project_dir / "index.html").is_file():
            return None
        return Detection(technologies=[DetectedTech("html", Category.LANGUAGE, "index.html")])
