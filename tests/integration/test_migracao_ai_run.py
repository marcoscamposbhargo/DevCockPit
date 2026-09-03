"""A migração 010 sobe e desce — em banco temporário, nunca no de produção.

O banco efetivo do painel instalado é `C:/Users/User/DevCockpit/data/devcockpit.db`,
com 19 projetos reais dentro, e `settings.resolve` reescreve caminho relativo:
rodar `alembic` sem apontar a URL para outro lugar aplica migração no banco do
dia a dia. Por isso o teste roda o Alembic em **subprocesso**, com
`DEVCOCKPIT_DATABASE_URL` absoluto em `tmp_path` — variável de ambiente vence o
`.env` no pydantic-settings, e o subprocesso não herda `get_settings` já
cacheado deste processo.

Aplicar a 010 no banco de produção é a T-14, porque exige reconstruir o
executável na mesma sessão (a constituição, em restrições técnicas).
"""

from __future__ import annotations

import subprocess  # noqa: S404 - o teste precisa rodar o Alembic de verdade
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

RAIZ = Path(__file__).resolve().parents[2]


def alembic(comando: str, banco: Path, env_base: dict[str, str]) -> None:
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *comando.split()],
        cwd=RAIZ,
        env={**env_base, "DEVCOCKPIT_DATABASE_URL": f"sqlite:///{banco.as_posix()}"},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, f"alembic {comando} falhou:\n{resultado.stderr}"


@pytest.fixture
def env_base() -> dict[str, str]:
    """Ambiente sem nenhum `DEVCOCKPIT_*` herdado da máquina de quem roda."""
    import os

    return {k: v for k, v in os.environ.items() if not k.startswith("DEVCOCKPIT_")}


def colunas(banco: Path, tabela: str) -> list[str]:
    import sqlite3

    with sqlite3.connect(banco) as conexao:
        return [linha[1] for linha in conexao.execute(f"pragma table_info({tabela})")]


def existe(banco: Path, nome: str) -> bool:
    import sqlite3

    with sqlite3.connect(banco) as conexao:
        consulta = "select 1 from sqlite_master where name = ?"
        return bool(list(conexao.execute(consulta, (nome,))))


def test_upgrade_cria_ai_run_e_downgrade_derruba(
    tmp_path: Path, env_base: dict[str, str]
) -> None:
    banco = tmp_path / "migracao.db"

    alembic("upgrade head", banco, env_base)

    assert existe(banco, "ai_run")
    assert existe(banco, "ix_ai_run_correlation")
    assert colunas(banco, "ai_run") == [
        "id",
        "correlation_id",
        "attempt",
        "provider",
        "model",
        "task_type",
        "decision",
        "tokens_in",
        "tokens_out",
        "latency_ms",
        "status",
        "estimated_cost",
        "price_date",
        "error",
        "created_at",
    ]

    alembic("downgrade 009_ai_especialista", banco, env_base)

    assert not existe(banco, "ai_run")
    # A reversão derruba a tabela e nada mais: o resto do schema fica de pé.
    assert existe(banco, "ai_message")
    assert existe(banco, "project")


def test_custo_e_data_de_preco_aceitam_nulo_no_banco(
    tmp_path: Path, env_base: dict[str, str]
) -> None:
    """`null` é "não medido" (**P-02**) — e precisa caber no schema, não só no modelo."""
    import sqlite3

    banco = tmp_path / "nulos.db"
    alembic("upgrade head", banco, env_base)

    with sqlite3.connect(banco) as conexao:
        conexao.execute(
            "insert into ai_run (correlation_id, attempt, provider, model, task_type, "
            "decision, tokens_in, tokens_out, latency_ms, status, estimated_cost, "
            "price_date, error, created_at) values "
            "('c-1', 1, 'ollama', 'qwen2.5-coder:7b', 'code_review', 'auto', 10, 5, 900, "
            "'ok', null, null, null, '2026-09-03 12:00:00')"
        )
        lido = list(conexao.execute("select estimated_cost, price_date from ai_run"))

    assert lido == [(None, None)]
