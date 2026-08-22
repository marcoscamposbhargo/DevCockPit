"""Os testes de segurança de `docs/07-security-model.md`.

Falha aqui reprova a entrega. Não vira issue.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import LOCAL_ORIGIN, WRITE_HEADERS

pytestmark = pytest.mark.api


# --- 1 e 14: guard de origem (defesa D5) ---------------------------------


def test_1_post_sem_cabecalho_de_cliente_e_recusado(
    client: TestClient, sample_project: Path
) -> None:
    resposta = client.post(
        "/api/projects",
        json={"path": str(sample_project)},
        headers={"Origin": LOCAL_ORIGIN},
    )

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "ACTION_NOT_ALLOWED"


def test_14_post_sem_origin_e_recusado(client: TestClient, sample_project: Path) -> None:
    resposta = client.post(
        "/api/projects",
        json={"path": str(sample_project)},
        headers={"X-DevCockpit-Client": "web"},
    )

    assert resposta.status_code == 403


def test_2_origin_externa_e_recusada(client: TestClient, sample_project: Path) -> None:
    resposta = client.post(
        "/api/projects",
        json={"path": str(sample_project)},
        headers={"X-DevCockpit-Client": "web", "Origin": "https://evil.example"},
    )

    assert resposta.status_code == 403


def test_get_nao_exige_cabecalho_de_cliente(client: TestClient) -> None:
    assert client.get("/api/projects").status_code == 200


# --- 13: guard de Host (defesa D10, contra DNS rebinding) ----------------


def test_13_host_externo_e_recusado_mesmo_em_get(client: TestClient) -> None:
    resposta = client.get("/api/projects", headers={"Host": "evil.example"})

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "ACTION_NOT_ALLOWED"


def test_13_host_externo_e_recusado_em_escrita(
    client: TestClient, sample_project: Path
) -> None:
    resposta = client.post(
        "/api/projects",
        json={"path": str(sample_project)},
        headers={**WRITE_HEADERS, "Host": "evil.example"},
    )

    assert resposta.status_code == 403


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:8765", "localhost"])
def test_host_local_e_aceito(client: TestClient, host: str) -> None:
    assert client.get("/api/projects", headers={"Host": host}).status_code == 200


# --- 3: startup recusa host não-loopback ---------------------------------
# Coberto em tests/unit/test_config_and_cache.py::test_recusa_host_nao_loopback


# --- 4, 5, 6: validação de path (defesa D4) ------------------------------
# Coberto em tests/unit/test_paths.py; aqui valida-se o contrato HTTP.


def test_4_path_fora_do_root_devolve_403(client: TestClient, tmp_path: Path) -> None:
    fora = tmp_path / "fora-do-root"
    fora.mkdir()

    resposta = client.post("/api/projects", json={"path": str(fora)}, headers=WRITE_HEADERS)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "PATH_NOT_ALLOWED"


def test_5_path_com_escape_devolve_403(client: TestClient, workspace: Path) -> None:
    resposta = client.post(
        "/api/projects",
        json={"path": str(workspace / ".." / ".." / "windows")},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code in (400, 403)


# --- 11: ação desconhecida ------------------------------------------------


@pytest.mark.parametrize(
    "acao", ["rm-tudo", "prune", "kill", "down-v", "exec", "cp"]
)
def test_11_acao_desconhecida_nao_executa_nada(client: TestClient, acao: str) -> None:
    """Verbo fora do conjunto fechado é recusado antes de virar comando.

    422 (não casa o padrão da rota) ou 404 (rota inexistente) — o que importa é
    que nada roda e nenhum job é criado.
    """
    resposta = client.post(
        f"/api/projects/qualquer/docker/{acao}", json={}, headers=WRITE_HEADERS
    )

    assert resposta.status_code in (404, 422), acao
    assert client.get("/api/jobs").json()["items"] == []


# --- 10: metacaractere de shell no nome ----------------------------------


def test_10_nome_com_metacaractere_e_tratado_como_texto(
    client: TestClient, workspace: Path
) -> None:
    projeto = workspace / "projeto-x"
    projeto.mkdir()

    resposta = client.post(
        "/api/projects",
        json={"path": str(projeto), "name": "proj & echo INVADIDO; rm -rf /"},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 201
    assert resposta.json()["name"] == "proj & echo INVADIDO; rm -rf /"


# --- 12: redação na auditoria --------------------------------------------
# Coberto em tests/unit/test_config_and_cache.py (redact/redact_argv) e no
# ActivityService, que aplica redact_argv antes de persistir.


def test_erro_de_dominio_traz_correlation_id(client: TestClient, tmp_path: Path) -> None:
    resposta = client.post(
        "/api/projects", json={"path": str(tmp_path / "nada")}, headers=WRITE_HEADERS
    )

    corpo = resposta.json()["error"]
    assert corpo["correlation_id"]
    assert resposta.headers.get("X-Correlation-Id")
