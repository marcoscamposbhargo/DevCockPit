"""Settings (bind loopback), redação de log e TTLCache."""

from __future__ import annotations

import pytest

from app.core.cache import NullCache, TTLCache
from app.core.config import Settings
from app.core.logging import redact, redact_argv

pytestmark = pytest.mark.unit


# --- bind loopback (NFR-001) ---------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_aceita_host_loopback(host: str) -> None:
    assert Settings(host=host).host == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "10.0.0.1"])
def test_recusa_host_nao_loopback(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(host=host)


def test_recusa_host_invalido() -> None:
    with pytest.raises(ValueError, match="inválido"):
        Settings(host="nao-e-um-host")


def test_self_origins_cobre_as_formas_locais() -> None:
    origins = Settings(port=8765).self_origins
    assert "http://127.0.0.1:8765" in origins
    assert "http://localhost:8765" in origins


# --- redação (NFR-103) ---------------------------------------------------


def test_redige_valor_sensivel() -> None:
    assert redact("GITHUB_TOKEN=abc123") == "GITHUB_TOKEN=***"
    assert redact("--password=segredo") == "--password=***"


def test_nao_redige_valor_comum() -> None:
    assert redact("--porcelain=v2") == "--porcelain=v2"


def test_redact_argv_preserva_estrutura() -> None:
    argv = ["git", "-c", "http.extraHeader=Authorization=Bearer xyz", "status"]
    redigido = redact_argv(argv)
    assert redigido[0] == "git"
    assert "xyz" not in " ".join(redigido)


# --- cache ---------------------------------------------------------------


def test_cache_devolve_valor_dentro_do_ttl() -> None:
    tempo = {"agora": 100.0}
    cache = TTLCache(ttl_seconds=5, clock=lambda: tempo["agora"])
    cache.set("git.status:x", {"branch": "main"})

    tempo["agora"] = 103.0
    assert cache.get("git.status:x") == {"branch": "main"}


def test_cache_expira_apos_ttl() -> None:
    tempo = {"agora": 100.0}
    cache = TTLCache(ttl_seconds=5, clock=lambda: tempo["agora"])
    cache.set("k", 1)

    tempo["agora"] = 106.0
    assert cache.get("k") is None


def test_cache_invalida_por_prefixo() -> None:
    cache = TTLCache(ttl_seconds=60)
    cache.set("git.status:a", 1)
    cache.set("git.status:b", 2)
    cache.set("docker.ps:a", 3)

    cache.invalidate_prefix("git.status:")

    assert cache.get("git.status:a") is None
    assert cache.get("docker.ps:a") == 3


def test_null_cache_nao_guarda_nada() -> None:
    cache = NullCache()
    cache.set("k", 1)
    assert cache.get("k") is None
