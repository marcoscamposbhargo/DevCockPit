"""Testes da rotação do arquivo de log.

Sem rotação o arquivo cresce sem fim: o log de desenvolvimento chegou a
57 MB porque o polling escreve algumas linhas por segundo.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.logging import LOG_BACKUP_COUNT, LOG_MAX_BYTES, configure_logging

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _restaura_logging():
    yield
    for handler in logging.getLogger().handlers[:]:
        handler.close()
    logging.getLogger().handlers.clear()


def _escreve(logger: logging.Logger, linhas: int) -> None:
    for i in range(linhas):
        logger.info("linha %d com texto suficiente para encher o arquivo", i)


def test_arquivo_nao_passa_do_teto(tmp_path: Path) -> None:
    alvo = tmp_path / "app.log"
    configure_logging(log_file=alvo, max_bytes=2000, backup_count=2)

    _escreve(logging.getLogger("teste.rotacao"), 200)

    for arquivo in tmp_path.iterdir():
        assert arquivo.stat().st_size <= 2000, f"{arquivo.name} passou do teto"


def test_guarda_apenas_os_backups_configurados(tmp_path: Path) -> None:
    alvo = tmp_path / "app.log"
    configure_logging(log_file=alvo, max_bytes=2000, backup_count=2)

    _escreve(logging.getLogger("teste.rotacao"), 500)

    # O arquivo corrente mais `backup_count` antigos — nada além disso.
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "app.log",
        "app.log.1",
        "app.log.2",
    ]


def test_padrao_limita_o_log_a_algo_administravel() -> None:
    # 10 MB x 5 backups: o log inteiro cabe em ~60 MB.
    assert LOG_MAX_BYTES * (LOG_BACKUP_COUNT + 1) <= 100 * 1024 * 1024
