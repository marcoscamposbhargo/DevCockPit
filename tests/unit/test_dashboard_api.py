"""Contrato HTTP de serviços, ações de sistema e dashboard."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.api


def porta_livre() -> int:
    with socket.socket() as temporario:
        temporario.bind(("127.0.0.1", 0))
        return temporario.getsockname()[1]


@pytest.fixture
def projeto(client: TestClient, workspace: Path) -> str:
    path = workspace / "app-web"
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    return client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    ).json()["id"]


# --- serviços -------------------------------------------------------------


def test_deteccao_ja_cria_servico(client: TestClient, projeto: str) -> None:
    itens = client.get(f"/api/projects/{projeto}/services").json()["items"]

    assert any(item["key"] == "backend" and item["port"] == 8000 for item in itens)
    assert all(item["state"] == "UNKNOWN" for item in itens), "nada verificado ainda"


def test_substituir_servicos(client: TestClient, projeto: str) -> None:
    resposta = client.put(
        f"/api/projects/{projeto}/services",
        json={
            "items": [
                {
                    "key": "frontend",
                    "label": "Frontend",
                    "port": 5173,
                    "url": "http://localhost:5173",
                    "health_kind": "HTTP",
                }
            ]
        },
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 200
    itens = resposta.json()["items"]
    assert [item["key"] for item in itens] == ["frontend"]


def test_url_externa_e_recusada(client: TestClient, projeto: str) -> None:
    """Um serviço não pode apontar para host arbitrário."""
    resposta = client.put(
        f"/api/projects/{projeto}/services",
        json={
            "items": [
                {"key": "api", "label": "API", "url": "http://evil.example", "health_kind": "HTTP"}
            ]
        },
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 422


def test_check_sob_demanda_atualiza_o_estado(client: TestClient, projeto: str) -> None:
    client.put(
        f"/api/projects/{projeto}/services",
        json={"items": [{"key": "db", "label": "DB", "port": porta_livre()}]},
        headers=WRITE_HEADERS,
    )

    itens = client.post(
        f"/api/projects/{projeto}/services/check", headers=WRITE_HEADERS
    ).json()["items"]

    assert itens[0]["state"] == "OFFLINE"
    assert itens[0]["checked_at"] is not None


def test_get_de_servicos_nao_verifica(client: TestClient, projeto: str) -> None:
    """A leitura serve cache; verificar aqui travaria o dashboard (NFR-011)."""
    client.put(
        f"/api/projects/{projeto}/services",
        json={"items": [{"key": "db", "label": "DB", "port": porta_livre()}]},
        headers=WRITE_HEADERS,
    )

    itens = client.get(f"/api/projects/{projeto}/services").json()["items"]

    assert itens[0]["state"] == "UNKNOWN"
    assert itens[0]["checked_at"] is None


# --- mapa de portas -------------------------------------------------------


def test_conflito_de_porta_entre_projetos(client: TestClient, workspace: Path) -> None:
    for nome in ("um", "dois"):
        path = workspace / nome
        path.mkdir()
        (path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        client.post("/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS)

    mapa = client.get("/api/services/ports").json()

    conflito = next(item for item in mapa["items"] if item["port"] == 8000)
    assert conflito["conflict"] is True
    assert set(conflito["projects"]) == {"um", "dois"}
    assert mapa["conflicts"] == 1


# --- ações de sistema -----------------------------------------------------


def test_abrir_browser_exige_chave_conhecida(client: TestClient, projeto: str) -> None:
    resposta = client.post(
        f"/api/projects/{projeto}/open/browser",
        json={"service_key": "nao-existe"},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 422
    assert "Disponíveis" in resposta.json()["error"]["message"]


def test_abrir_browser_nao_aceita_url_do_cliente(client: TestClient, projeto: str) -> None:
    """Decisão D-13: o payload tem `service_key`, e URL não é campo válido."""
    resposta = client.post(
        f"/api/projects/{projeto}/open/browser",
        json={"url": "http://evil.example"},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 422


def test_acoes_de_sistema_exigem_guard_de_escrita(client: TestClient, projeto: str) -> None:
    for acao in ("vscode", "folder", "terminal"):
        assert client.post(f"/api/projects/{projeto}/open/{acao}").status_code == 403


def test_projeto_sem_diretorio_nao_abre(client: TestClient, workspace: Path) -> None:
    path = workspace / "some"
    path.mkdir()
    pid = client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    ).json()["id"]
    path.rmdir()

    resposta = client.post(f"/api/projects/{pid}/open/folder", headers=WRITE_HEADERS)

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "PROJECT_DIR_MISSING"


# --- dashboard ------------------------------------------------------------


def test_dashboard_vazio(client: TestClient) -> None:
    corpo = client.get("/api/dashboard").json()

    assert corpo["totals"]["projects"] == 0
    assert corpo["from_cache"] is False
    assert corpo["generated_at"]


def test_dashboard_conta_projetos(client: TestClient, projeto: str) -> None:
    corpo = client.get("/api/dashboard").json()

    assert corpo["totals"]["projects"] == 1
    assert corpo["totals"]["stopped"] == 1


def test_dashboard_marca_from_cache_na_segunda_chamada(
    client: TestClient, projeto: str
) -> None:
    """A UI mostra a idade do dado em vez de fingir tempo real (D-18)."""
    assert client.get("/api/dashboard").json()["from_cache"] is False
    assert client.get("/api/dashboard").json()["from_cache"] is True


def test_dashboard_aponta_conflito_de_porta(client: TestClient, workspace: Path) -> None:
    for nome in ("a", "b"):
        path = workspace / nome
        path.mkdir()
        (path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        client.post("/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS)

    conflitos = client.get("/api/dashboard").json()["port_conflicts"]

    assert conflitos and conflitos[0]["port"] == 8000


def test_dashboard_lista_recentes(client: TestClient, projeto: str) -> None:
    client.get(f"/api/projects/{projeto}")  # marca acesso

    recentes = client.get("/api/dashboard").json()["recent_projects"]

    assert [item["id"] for item in recentes] == [projeto]


def test_dashboard_nao_dispara_verificacao(client: TestClient, workspace: Path) -> None:
    """Se o dashboard verificasse serviços, 30 projetos travariam a tela."""
    path = workspace / "lento"
    path.mkdir()
    (path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    client.post("/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS)

    corpo = client.get("/api/dashboard").json()

    # Nada foi verificado, então nenhum serviço aparece como ativo.
    assert corpo["active_services"] == []


def test_dashboard_com_docker_conta_projetos(client: TestClient, workspace: Path) -> None:
    path = workspace / "com-docker"
    path.mkdir()
    (path / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx\n", "utf-8")
    client.post("/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS)

    assert client.get("/api/dashboard").json()["totals"]["with_docker"] == 1
