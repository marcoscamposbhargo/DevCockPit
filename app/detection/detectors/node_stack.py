"""Detectores de projeto Node.js, Vite e Next.js."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.detection.types import Category, DetectedTech, Detection, SuggestedService

NODE_FRAMEWORKS: dict[str, tuple[str, str, int | None]] = {
    # pacote: (nome exibido, categoria, porta convencional)
    "next": ("nextjs", Category.FRAMEWORK, 3000),
    "react": ("react", Category.FRAMEWORK, None),
    "vue": ("vue", Category.FRAMEWORK, None),
    "svelte": ("svelte", Category.FRAMEWORK, None),
    "@sveltejs/kit": ("sveltekit", Category.FRAMEWORK, 5173),
    "nuxt": ("nuxt", Category.FRAMEWORK, 3000),
    "astro": ("astro", Category.FRAMEWORK, 4321),
    "express": ("express", Category.FRAMEWORK, 3000),
    "fastify": ("fastify", Category.FRAMEWORK, 3000),
    "nestjs": ("nestjs", Category.FRAMEWORK, 3000),
    "@nestjs/core": ("nestjs", Category.FRAMEWORK, 3000),
    "vite": ("vite", Category.TOOLING, 5173),
    "typescript": ("typescript", Category.LANGUAGE, None),
    "tailwindcss": ("tailwind", Category.TOOLING, None),
    "electron": ("electron", Category.RUNTIME, None),
}

_VITE_PORT = re.compile(r"port\s*:\s*(\d{2,5})")


def _service_for(port: int, key: str, label: str) -> SuggestedService:
    return SuggestedService(
        key=key,
        label=label,
        port=port,
        url=f"http://localhost:{port}",
        health_kind="HTTP",
    )


class PackageJsonDetector:
    name = "node_package"

    def detect(self, project_dir: Path) -> Detection | None:
        target = project_dir / "package.json"
        if not target.is_file():
            return None

        detection = Detection(
            technologies=[DetectedTech("node", Category.RUNTIME, "package.json")]
        )

        try:
            data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            detection.warnings.append("package.json inválido; só o runtime foi detectado.")
            return detection

        packages = {
            *(data.get("dependencies") or {}),
            *(data.get("devDependencies") or {}),
        }

        for package in sorted(packages):
            entry = NODE_FRAMEWORKS.get(package.lower())
            if entry is None:
                continue
            label, category, port = entry
            detection.technologies.append(DetectedTech(label, category, "package.json"))
            if port and not any(s.key == "frontend" for s in detection.services):
                detection.services.append(_service_for(port, "frontend", "Frontend"))

        return detection


class ViteConfigDetector:
    name = "vite"

    def detect(self, project_dir: Path) -> Detection | None:
        matches = [
            candidate
            for suffix in ("js", "ts", "mjs", "mts")
            if (candidate := project_dir / f"vite.config.{suffix}").is_file()
        ]
        if not matches:
            return None

        config = matches[0]
        detection = Detection(
            technologies=[DetectedTech("vite", Category.TOOLING, config.name)]
        )

        # Extração best-effort: se o `port` estiver em variável ou vier de env,
        # a porta simplesmente não é sugerida. Nunca executamos o config.
        try:
            found = _VITE_PORT.search(config.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            found = None

        port = int(found.group(1)) if found else 5173
        if 1 <= port <= 65535:
            detection.services.append(_service_for(port, "frontend", "Frontend"))

        return detection


class NextConfigDetector:
    name = "nextjs"

    def detect(self, project_dir: Path) -> Detection | None:
        matches = [
            candidate
            for suffix in ("js", "ts", "mjs")
            if (candidate := project_dir / f"next.config.{suffix}").is_file()
        ]
        if not matches:
            return None

        return Detection(
            technologies=[DetectedTech("nextjs", Category.FRAMEWORK, matches[0].name)],
            services=[_service_for(3000, "frontend", "Frontend")],
        )
