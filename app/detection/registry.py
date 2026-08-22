"""Registry de detecção (FR-022).

Adicionar suporte a uma stack nova é escrever um detector e registrá-lo aqui.
Nenhuma cadeia de `if` cresce com o tempo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.detection.detectors.docker_stack import ComposeDetector, DockerfileDetector
from app.detection.detectors.node_stack import (
    NextConfigDetector,
    PackageJsonDetector,
    ViteConfigDetector,
)
from app.detection.detectors.other_stacks import (
    GoDetector,
    GradleDetector,
    MavenDetector,
    RustDetector,
    StaticHtmlDetector,
)
from app.detection.detectors.python_stack import PyprojectDetector, RequirementsDetector
from app.detection.types import Detection, Detector

logger = logging.getLogger(__name__)

# A ordem importa: quem detecta primeiro define o rótulo do serviço quando há
# empate de chave. Compose vem cedo porque é a fonte mais confiável de portas.
DEFAULT_DETECTORS: tuple[Detector, ...] = (
    ComposeDetector(),
    DockerfileDetector(),
    PyprojectDetector(),
    RequirementsDetector(),
    PackageJsonDetector(),
    NextConfigDetector(),
    ViteConfigDetector(),
    MavenDetector(),
    GradleDetector(),
    GoDetector(),
    RustDetector(),
)

FALLBACK_DETECTORS: tuple[Detector, ...] = (StaticHtmlDetector(),)


class DetectionRegistry:
    def __init__(
        self,
        detectors: tuple[Detector, ...] = DEFAULT_DETECTORS,
        fallbacks: tuple[Detector, ...] = FALLBACK_DETECTORS,
    ) -> None:
        self.detectors = detectors
        self.fallbacks = fallbacks

    @property
    def names(self) -> list[str]:
        return [detector.name for detector in (*self.detectors, *self.fallbacks)]

    def run(self, project_dir: Path) -> Detection:
        result = Detection()

        if not project_dir.is_dir():
            result.warnings.append("Diretório não encontrado; detecção não executada.")
            return result

        for detector in self.detectors:
            partial = self._safe_detect(detector, project_dir, result)
            if partial is not None:
                result.merge(partial)

        # Fallback só entra quando nada mais reconheceu o projeto: um
        # `index.html` de template não deve rotular um Next.js como estático.
        if not result.technologies:
            for detector in self.fallbacks:
                partial = self._safe_detect(detector, project_dir, result)
                if partial is not None:
                    result.merge(partial)

        return result

    @staticmethod
    def _safe_detect(detector: Detector, project_dir: Path, result: Detection) -> Detection | None:
        """Um detector que quebra não pode derrubar a detecção inteira.

        Antes só `OSError` era contido. Mas detector lê arquivo de projeto
        alheio, e arquivo de projeto alheio vem torto de dez jeitos diferentes:
        JSON com vírgula sobrando, YAML com tabulação, TOML inválido, byte que
        não é UTF-8. Cada um levanta uma exceção de tipo próprio, nenhuma delas
        `OSError` — e a que escapasse derrubava o cadastro do projeto junto,
        que é a pior forma possível de reagir a um `package.json` mal formado.

        A varredura do fallback não tinha proteção nenhuma.

        O que quebra vira aviso na tela; os outros detectores seguem.
        """
        try:
            return detector.detect(project_dir)
        except Exception as exc:  # noqa: BLE001 - detector não derruba cadastro
            logger.warning(
                "detector falhou",
                extra={
                    "extra_fields": {
                        "detector": detector.name,
                        "project_dir": str(project_dir),
                        "error": str(exc),
                    }
                },
            )
            result.warnings.append(
                f"O detector {detector.name} não conseguiu ler este projeto: "
                f"{str(exc)[:120]}"
            )
            return None


def looks_like_project(path: Path, markers: tuple[str, ...]) -> bool:
    """Decide se um diretório é candidato a projeto, para a varredura."""
    return any((path / marker).exists() for marker in markers)
