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


def test_trocar_a_porta_de_um_servico_existente_persiste(
    client: TestClient, projeto: str
) -> None:
    """Reenviar a lista com as mesmas chaves precisa sobreviver ao commit.

    O `clear()` + `append()` sem flush no meio faz o SQLAlchemy inserir antes
    de apagar: `UNIQUE(project_id, key)` estoura **depois** da resposta, o
    cliente vê 200 e o banco fica com o valor velho.
    """
    antes = client.get(f"/api/projects/{projeto}").json()["services"]
    trocado = [
        {**servico, "port": 9100} if servico["key"] == "backend" else servico
        for servico in antes
    ]

    resposta = client.put(
        f"/api/projects/{projeto}/services", json={"items": trocado}, headers=WRITE_HEADERS
    )
    assert resposta.status_code == 200

    depois = client.get(f"/api/projects/{projeto}").json()["services"]
    assert {s["key"]: s["port"] for s in depois}["backend"] == 9100


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


def test_mapa_de_portas_diz_quem_ocupa_cada_uma(client: TestClient, projeto: str) -> None:
    """Sem o id do projeto e a chave do serviço a tela não teria como editar."""
    mapa = client.get("/api/services/ports").json()

    binding = next(item for item in mapa["bindings"] if item["port"] == 8000)

    assert binding["project_id"] == projeto
    assert binding["service_key"] == "backend"
    assert binding["conflict"] is False


def test_dois_servicos_do_mesmo_projeto_na_mesma_porta_conflitam(
    client: TestClient, projeto: str
) -> None:
    """Contar por nome de projeto escondia este caso: um `set` de um nome só."""
    client.put(
        f"/api/projects/{projeto}/services",
        json={
            "items": [
                {"key": "api", "label": "API", "port": 8000},
                {"key": "admin", "label": "Admin", "port": 8000},
            ]
        },
        headers=WRITE_HEADERS,
    )

    mapa = client.get("/api/services/ports").json()

    porta = next(item for item in mapa["items"] if item["port"] == 8000)
    assert porta["conflict"] is True
    assert mapa["conflicts"] == 1
    assert all(item["conflict"] for item in mapa["bindings"] if item["port"] == 8000)


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


def test_dashboard_conta_rodando_pelo_health_observado(
    client: TestClient, projeto: str
) -> None:
    """O card "Rodando" vem do health, não da coluna `status`.

    `status` nunca chega a `RUNNING` sozinho — ele descreve o registro, não o
    processo. Contar por ele mostrava "0 rodando" na mesma tela que listava
    serviços online.
    """
    with socket.socket() as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        porta = servidor.getsockname()[1]

        client.put(
            f"/api/projects/{projeto}/services",
            json={
                "items": [
                    {"key": "db", "label": "DB", "port": porta}
                ]
            },
            headers=WRITE_HEADERS,
        )
        estado = client.post(
            f"/api/projects/{projeto}/services/check", headers=WRITE_HEADERS
        ).json()["items"][0]["state"]

    assert estado == "ONLINE"

    totals = client.get("/api/dashboard").json()["totals"]

    assert totals["running"] == 1
    assert totals["stopped"] == 0, "projeto com serviço online não pode contar como parado"
    assert totals["projects"] == 1


# --- resumo da lista de projetos ------------------------------------------


def test_lista_de_projetos_informa_quantos_servicos_cada_um_declara(
    client: TestClient, projeto: str
) -> None:
    """O card da lista cruza este total com o que o dashboard traz de cache.

    Sem ele a tela só saberia quantos serviços estão online, nunca de quantos —
    e "2 online" sem denominador não responde se falta algo de pé.
    """
    itens = client.get("/api/projects").json()["items"]
    resumo = next(item for item in itens if item["id"] == projeto)

    declarados = client.get(f"/api/projects/{projeto}/services").json()["items"]

    assert resumo["services_total"] == len(declarados)
    assert resumo["services_total"] > 0, "a detecção deste projeto já cria um serviço"


def test_projeto_sem_servico_declara_zero(client: TestClient, workspace: Path) -> None:
    """Zero é resposta, não ausência: o card mostra "sem serviço declarado"."""
    path = workspace / "pasta-vazia"
    path.mkdir()
    criado = client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    ).json()

    itens = client.get("/api/projects").json()["items"]
    resumo = next(item for item in itens if item["id"] == criado["id"])

    assert resumo["services_total"] == 0
