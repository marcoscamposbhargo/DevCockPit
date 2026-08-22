"""Regressões encontradas na varredura de 22/08/2026.

Cada teste aqui nasceu de um defeito que a suíte não pegava. O comentário de
cada bloco diz o que estava errado antes, porque é isso que impede o defeito de
voltar disfarçado de refatoração inocente.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.system.adapter import build_os_adapter
from app.jobs.job import Job
from app.runner.allowlist import (
    _REGISTRY,
    ActionDefinition,
    assert_registry_is_safe,
)
from app.schemas.project import ServiceIn, validate_local_http_url

# --- validação de URL local ----------------------------------------------
# O parser antigo cortava a string no primeiro `:` para achar o host. Em
# `http://localhost:3000@evil.com/`, `localhost:3000` é *userinfo* e o host real
# é `evil.com` — a URL passava, virava `health_url` de um serviço e o poller
# passava a bater num host externo a cada ciclo.

URLS_EXTERNAS = [
    "http://localhost:3000@evil.com/",
    "http://127.0.0.1:80@attacker.test/probe",
    "https://localhost@example.com",
    "http://evil.com",
    "http://localhost.evil.com:3000",
]


@pytest.mark.parametrize("url", URLS_EXTERNAS)
def test_url_que_aponta_para_fora_e_recusada(url: str) -> None:
    with pytest.raises(ValueError, match="localhost"):
        validate_local_http_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:3000",
        "http://127.0.0.1:8000/health",
        "https://localhost",
        "http://[::1]:8080/ready",
    ],
)
def test_url_local_continua_aceita(url: str) -> None:
    """Inclui a forma IPv6 com porta, que o parser antigo rejeitava."""
    assert validate_local_http_url(url) == url


def test_servico_nao_aceita_health_url_externa() -> None:
    with pytest.raises(ValueError, match="localhost"):
        ServiceIn(key="api", label="API", health_url="http://localhost:1@evil.com/")


# --- índice absoluto da saída de job -------------------------------------
# `revision` conta tudo que já saiu e nunca retrocede; `lines` encolhe a cada
# truncamento. O código fatiava `lines[after:]` com um índice absoluto: depois
# do primeiro corte o SSE passava a entregar listas vazias para sempre e o
# console do `compose up` congelava no meio.


def _job_truncado(total: int = 400, limite: int = 300) -> Job:
    job = Job(id="j1", action="a", key="k")
    for i in range(total):
        job.append(f"linha {i:04d}", limit=limite)
    return job


def test_lines_since_continua_entregando_depois_do_truncamento() -> None:
    job = _job_truncado()
    assert job.output_truncated is True
    assert job.dropped > 0

    cursor = job.revision
    job.append("depois do corte", limit=300)

    novas = job.lines_since(cursor)
    assert novas == ["depois do corte"]


def test_lines_since_com_cursor_anterior_ao_descarte_nao_estoura() -> None:
    """Cliente que ficou para trás recebe o que sobrou, não uma lista vazia."""
    job = _job_truncado()

    assert job.lines_since(0) == job.lines
    assert job.lines_since(job.revision) == []


def test_cursor_e_o_tamanho_da_lista_nao_se_confundem() -> None:
    job = _job_truncado()
    # Exatamente a confusão que causava o defeito: os dois números divergem, e
    # é o primeiro que o cliente devolve em `after`.
    assert job.revision > len(job.lines)
    assert job.revision == job.dropped + len(job.lines)


# --- allowlist: flags proibidas ------------------------------------------
# `FORBIDDEN_FLAGS` estava declarado e nunca conferido. A barreira que impedia
# `down -v` de entrar no registro era só documentação.


def test_registro_reprova_acao_com_flag_proibida() -> None:
    rotulo = "teste.acao.destrutiva"
    _REGISTRY[rotulo] = ActionDefinition(
        label=rotulo,
        build=lambda: ["docker", "compose", "down", "-v"],
        timeout_key="timeout_docker_read",
        description="Só existe dentro deste teste.",
    )
    try:
        with pytest.raises(RuntimeError, match="flag proibida"):
            assert_registry_is_safe()
    finally:
        del _REGISTRY[rotulo]


def test_registro_real_passa_na_verificacao() -> None:
    assert_registry_is_safe()


# --- abertura de janela: dispara e segue ---------------------------------
# Terminal, editor e explorador eram executados com `capture_output` e timeout.
# `powershell -NoExit` e `alacritty` só terminam quando o usuário fecha a
# janela: o timeout de 10 s matava o terminal recém-aberto, e o pipe de captura
# impedia que ele ganhasse console próprio.

PLATAFORMAS = ["windows", "macos", "linux"]


@pytest.mark.parametrize("plataforma", PLATAFORMAS)
def test_abrir_terminal_e_desacoplado(plataforma: str, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    adapter = build_os_adapter(platform=plataforma)
    monkeypatch.setattr(adapter, "tool_available", lambda tool: True)

    assert adapter.open_terminal(tmp_path).detached is True


@pytest.mark.parametrize("plataforma", PLATAFORMAS)
def test_abrir_editor_e_pasta_tambem_sao_desacoplados(
    plataforma: str, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    adapter = build_os_adapter(platform=plataforma)
    monkeypatch.setattr(adapter, "tool_available", lambda tool: True)
    monkeypatch.setattr("shutil.which", lambda tool: f"C:/fake/{tool}")

    assert adapter.open_folder(tmp_path).detached is True
    assert adapter.open_in_editor(tmp_path).detached is True


def test_powershell_de_reserva_nao_espera_a_janela_fechar(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """O caso concreto: Windows 10 antigo, sem `wt.exe`."""
    adapter = build_os_adapter(platform="windows")
    monkeypatch.setattr(adapter, "tool_available", lambda tool: False)

    spec = adapter.open_terminal(tmp_path)

    assert spec.argv[0] == "powershell.exe"
    assert "-NoExit" in spec.argv
    assert spec.detached is True
