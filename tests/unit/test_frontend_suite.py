"""Roda a suíte de frontend dentro do `pytest`.

O painel tem ~5.500 linhas de JavaScript e, até esta sessão, nenhum teste — com
os defeitos de interface sendo a maioria dos achados. A suíte nova vive em
`tests/frontend/`, roda no runner do próprio Node e não traz dependência
nenhuma (ADR-005: o frontend não tem build nem `node_modules`).

Este arquivo existe para que `pytest -q` continue sendo o comando único. Sem
Node instalado o teste é **pulado**, não falha: quem só mexe no Python não
precisa de Node para rodar a suíte.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[2]
PADRAO = "tests/frontend/*.test.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node não está instalado")
def test_suite_de_frontend() -> None:
    resultado = subprocess.run(  # noqa: S603 - argv fixo, sem shell
        ["node", "--test", PADRAO],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if resultado.returncode != 0:
        # A saída do Node é o diagnóstico: repeti-la aqui evita "1 failed" sem
        # dizer qual teste, que obrigaria a rodar de novo à mão.
        pytest.fail(
            "A suíte de frontend falhou:\n\n"
            f"{resultado.stdout[-4000:]}\n{resultado.stderr[-2000:]}"
        )
