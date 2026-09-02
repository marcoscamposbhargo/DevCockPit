"""Testes da rotação do arquivo de log.

Sem rotação o arquivo cresce sem fim: o log de desenvolvimento chegou a
57 MB porque o polling escreve algumas linhas por segundo.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.logging import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    PollingAccessFilter,
    configure_logging,
)

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


def _acesso(mensagem: str) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, mensagem, None, None)


@pytest.mark.parametrize(
    "rota",
    ["/api/system/metrics", "/api/health"],
)
def test_polling_bem_sucedido_nao_vira_linha(rota: str) -> None:
    registro = _acesso(f'127.0.0.1:5443 - "GET {rota} HTTP/1.1" 200')
    assert PollingAccessFilter().filter(registro) is False


def test_erro_na_rota_de_polling_continua_no_log() -> None:
    # É justamente quando a linha importa.
    registro = _acesso('127.0.0.1:5443 - "GET /api/system/metrics HTTP/1.1" 500')
    assert PollingAccessFilter().filter(registro) is True


@pytest.mark.parametrize(
    "mensagem",
    [
        '127.0.0.1:5443 - "GET /api/projects?limit=200 HTTP/1.1" 200',
        '127.0.0.1:5443 - "GET /api/dashboard HTTP/1.1" 200',
        '127.0.0.1:5443 - "POST /api/jobs HTTP/1.1" 200',
    ],
)
def test_navegacao_de_verdade_nao_e_filtrada(mensagem: str) -> None:
    assert PollingAccessFilter().filter(_acesso(mensagem)) is True


def test_configure_logging_instala_o_filtro_uma_vez_so(tmp_path: Path) -> None:
    # Reconfigurar não pode empilhar filtro sobre filtro.
    for _ in range(3):
        configure_logging(log_file=tmp_path / "app.log")
    acesso = logging.getLogger("uvicorn.access")
    assert len([f for f in acesso.filters if isinstance(f, PollingAccessFilter)]) == 1


def test_quiet_polling_desligado_nao_filtra_nada(tmp_path: Path) -> None:
    configure_logging(log_file=tmp_path / "app.log", quiet_polling=False)
    acesso = logging.getLogger("uvicorn.access")
    assert not [f for f in acesso.filters if isinstance(f, PollingAccessFilter)]
