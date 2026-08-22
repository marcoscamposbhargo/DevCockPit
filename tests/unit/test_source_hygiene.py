"""Testes que varrem o próprio código-fonte.

São as verificações 8 e 9 de `docs/07-security-model.md`: se falharem, a
entrega é reprovada. Um comentário não salva ninguém — o teste é o que garante
que `subprocess` continue confinado.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT

pytestmark = pytest.mark.unit

APP_DIR = PROJECT_ROOT / "app"
RUNNER_DIR = APP_DIR / "runner"


def _python_files() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


def test_nenhum_shell_true_no_codigo() -> None:
    padrao = re.compile(r"shell\s*=\s*True")
    ofensores = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _python_files()
        if padrao.search(path.read_text(encoding="utf-8"))
    ]
    assert not ofensores, f"shell=True é proibido (ADR-003). Encontrado em: {ofensores}"


def test_subprocess_apenas_no_runner() -> None:
    padrao = re.compile(r"^\s*(import subprocess|from subprocess import)", re.MULTILINE)
    ofensores = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in _python_files()
        if padrao.search(path.read_text(encoding="utf-8")) and RUNNER_DIR not in path.parents
    ]
    assert not ofensores, (
        "subprocess só pode ser importado em app/runner/ (ADR-003). "
        f"Encontrado em: {ofensores}"
    )


def test_camada_http_nao_importa_adapters_nem_runner() -> None:
    """NFR-020: a camada HTTP não conhece o sistema operacional."""
    rotas = sorted((APP_DIR / "api" / "routes").rglob("*.py"))
    padrao = re.compile(r"^\s*from app\.(runner|adapters)", re.MULTILINE)
    ofensores = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in rotas
        if padrao.search(path.read_text(encoding="utf-8"))
    ]
    assert not ofensores, f"Rotas não devem importar runner nem adapters: {ofensores}"
