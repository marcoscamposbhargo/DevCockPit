"""Registry de detecção (FR-022).

Adicionar suporte a uma stack nova é escrever um detector e registrá-lo aqui.
Nenhuma cadeia de `if` cresce com o tempo.
"""

from __future__ import annotations

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
            try:
                partial = detector.detect(project_dir)
            except OSError as exc:
                result.warnings.append(f"Detector {detector.name} falhou: {exc}")
                continue
            if partial is not None:
                result.merge(partial)

        # Fallback só entra quando nada mais reconheceu o projeto: um
        # `index.html` de template não deve rotular um Next.js como estático.
        if not result.technologies:
            for detector in self.fallbacks:
                partial = detector.detect(project_dir)
                if partial is not None:
                    result.merge(partial)

        return result


def looks_like_project(path: Path, markers: tuple[str, ...]) -> bool:
    """Decide se um diretório é candidato a projeto, para a varredura."""
    return any((path / marker).exists() for marker in markers)
