"""Registry de detecção (FR-022).

Adicionar suporte a uma stack nova é escrever um detector e registrá-lo aqui.
Nenhuma cadeia de `if` cresce com o tempo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.monorepo import SUBPROJETOS
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
from app.detection.types import DetectedTech, Detection, Detector

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


def _dentro_de(deteccao: Detection, relativo: str) -> Detection:
    """Reescreve uma detecção de subpasta para falar em nome do projeto inteiro.

    Sem isso, a evidência diria "pyproject.toml" para um arquivo que está em
    `backend/`, e o `compose_file` viraria um caminho que não existe a partir
    da raiz — que é justamente o erro que o painel cometia ao não achar o
    Compose de quem o guarda em `infra/`.
    """
    return Detection(
        technologies=[
            DetectedTech(
                name=t.name,
                category=t.category,
                evidence=f"{relativo}/{t.evidence}",
            )
            for t in deteccao.technologies
        ],
        services=deteccao.services,
        compose_file=(
            f"{relativo}/{deteccao.compose_file}" if deteccao.compose_file else None
        ),
        warnings=deteccao.warnings,
    )


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

        self._rodar(self.detectors, project_dir, result)

        # Monorepo: a raiz de um repositório com `backend/` e `frontend/` não
        # tem marcador nenhum, e o projeto aparecia sem stack e sem ambiente.
        # A raiz vem primeiro de propósito — o que ela declara é a palavra do
        # projeto sobre si mesmo, e `merge` mantém quem chegou antes.
        for relativo in SUBPROJETOS:
            sub = project_dir / relativo
            if sub.is_dir():
                self._rodar(self.detectors, sub, result, dentro=relativo)

        # Fallback só entra quando nada mais reconheceu o projeto: um
        # `index.html` de template não deve rotular um Next.js como estático.
        if not result.technologies:
            self._rodar(self.fallbacks, project_dir, result)

        return result

    def _rodar(
        self,
        detectores: tuple[Detector, ...],
        diretorio: Path,
        result: Detection,
        *,
        dentro: str = "",
    ) -> None:
        """Roda um conjunto de detectores num diretório e junta o que achou.

        `dentro` é o caminho relativo à raiz do projeto. Ele entra na evidência
        e no `compose_file` porque um nome de arquivo solto mentiria: quem lê
        "docker-compose.yml" procura na raiz, e o arquivo está em `infra/`.
        """
        for detector in detectores:
            partial = self._safe_detect(detector, diretorio, result)
            if partial is None:
                continue
            if dentro:
                partial = _dentro_de(partial, dentro)
            result.merge(partial)

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
                f"O detector {detector.name} não conseguiu ler este projeto: {str(exc)[:120]}"
            )
            return None


def looks_like_project(path: Path, markers: tuple[str, ...]) -> bool:
    """Decide se um diretório é candidato a projeto, para a varredura."""
    return any((path / marker).exists() for marker in markers)
