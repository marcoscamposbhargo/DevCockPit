"""Contrato HTTP das rotas de projeto e do log de atividade."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.api


def _create(client: TestClient, path: Path, **extra: object) -> dict:
    resposta = client.post(
        "/api/projects", json={"path": str(path), **extra}, headers=WRITE_HEADERS
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_cadastra_projeto_com_nome_da_pasta(client: TestClient, sample_project: Path) -> None:
    corpo = _create(client, sample_project)

    assert corpo["name"] == "dashboard-contabil"
    assert corpo["id"] == "dashboard-contabil"
    assert corpo["status"] == "REGISTERED"
    assert corpo["path"].endswith("dashboard-contabil")


def test_cadastra_com_nome_proprio_gera_slug(client: TestClient, sample_project: Path) -> None:
    corpo = _create(client, sample_project, name="Dashboard Contábil")

    assert corpo["name"] == "Dashboard Contábil"
    assert corpo["id"] == "dashboard-contabil"


def test_path_duplicado_devolve_409(client: TestClient, sample_project: Path) -> None:
    _create(client, sample_project)

    resposta = client.post(
        "/api/projects", json={"path": str(sample_project)}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "PROJECT_ALREADY_EXISTS"


def test_nomes_iguais_geram_ids_distintos(client: TestClient, workspace: Path) -> None:
    primeiro = workspace / "um" / "api"
    segundo = workspace / "dois" / "api"
    primeiro.mkdir(parents=True)
    segundo.mkdir(parents=True)

    a = _create(client, primeiro)
    b = _create(client, segundo)

    assert a["id"] == "api"
    assert b["id"] == "api-2"


def test_diretorio_inexistente_devolve_400(client: TestClient, workspace: Path) -> None:
    resposta = client.post(
        "/api/projects", json={"path": str(workspace / "fantasma")}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "PATH_NOT_FOUND"


def test_lista_com_total_e_filtro_de_busca(client: TestClient, workspace: Path) -> None:
    for nome in ("alpha", "beta", "gamma"):
        pasta = workspace / nome
        pasta.mkdir()
        _create(client, pasta)

    todos = client.get("/api/projects").json()
    assert todos["total"] == 3

    filtrado = client.get("/api/projects", params={"q": "bet"}).json()
    assert filtrado["total"] == 1
    assert filtrado["items"][0]["name"] == "beta"


def test_detalhe_atualiza_ultimo_acesso(client: TestClient, sample_project: Path) -> None:
    criado = _create(client, sample_project)
    assert criado["last_accessed_at"] is None

    detalhe = client.get(f"/api/projects/{criado['id']}").json()

    assert detalhe["last_accessed_at"] is not None


def test_projeto_inexistente_devolve_404(client: TestClient) -> None:
    resposta = client.get("/api/projects/nao-existe")

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_patch_altera_campos_editaveis(client: TestClient, sample_project: Path) -> None:
    criado = _create(client, sample_project)

    resposta = client.patch(
        f"/api/projects/{criado['id']}",
        json={"name": "Novo Nome", "is_pinned": True},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["name"] == "Novo Nome"
    assert corpo["is_pinned"] is True


def test_patch_ignora_path(client: TestClient, sample_project: Path, workspace: Path) -> None:
    """Decisão D-06: `path` não é editável."""
    criado = _create(client, sample_project)
    outro = workspace / "outro"
    outro.mkdir()

    resposta = client.patch(
        f"/api/projects/{criado['id']}", json={"path": str(outro)}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 200
    assert resposta.json()["path"] == criado["path"]


def test_delete_remove_registro_mas_nao_toca_no_disco(
    client: TestClient, sample_project: Path
) -> None:
    criado = _create(client, sample_project)

    resposta = client.delete(f"/api/projects/{criado['id']}", headers=WRITE_HEADERS)

    assert resposta.status_code == 204
    assert sample_project.exists()
    assert (sample_project / "pyproject.toml").exists()
    assert client.get(f"/api/projects/{criado['id']}").status_code == 404


def test_projeto_com_diretorio_removido_vira_missing(
    client: TestClient, workspace: Path
) -> None:
    """NFR-062: sumiu o diretório, o sistema tem um estado honesto para exibir."""
    pasta = workspace / "some-e-volta"
    pasta.mkdir()
    criado = _create(client, pasta)

    pasta.rmdir()

    detalhe = client.get(f"/api/projects/{criado['id']}").json()
    assert detalhe["status"] == "MISSING"


def test_atividade_registra_cadastro_e_remocao(
    client: TestClient, sample_project: Path
) -> None:
    criado = _create(client, sample_project)
    client.delete(f"/api/projects/{criado['id']}", headers=WRITE_HEADERS)

    atividade = client.get("/api/activity", params={"project_id": criado["id"]}).json()
    acoes = [item["action"] for item in atividade["items"]]

    assert "project.create" in acoes
    assert "project.delete" in acoes
    assert all(item["correlation_id"] for item in atividade["items"])


def test_health_informa_ferramentas_e_roots(client: TestClient, workspace: Path) -> None:
    corpo = client.get("/api/health").json()

    assert corpo["status"] == "ok"
    assert set(corpo["tools"]) == {"git", "docker", "code"}
    assert corpo["allowed_roots"] == [workspace.resolve().as_posix()]


# --- frontend servido -----------------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    ["/", "/css/tokens.css", "/js/main.js"],
    ids=["index", "css", "js"],
)
def test_frontend_manda_o_browser_revalidar(client: TestClient, caminho: str) -> None:
    """Sem `Cache-Control` o navegador guarda CSS e JS por um tempo que ele
    mesmo estima e não pergunta se mudou.

    Num painel local, cujos arquivos mudam no disco embaixo da aba aberta, isso
    aparece como "a alteração não surtiu efeito" — com o servidor entregando o
    arquivo novo o tempo todo. Aconteceu de verdade, e sem `no-cache` volta a
    acontecer sem deixar rastro em log nenhum.
    """
    resposta = client.get(caminho)

    assert resposta.status_code == 200
    assert resposta.headers.get("cache-control") == "no-cache"


def test_revalidacao_do_frontend_nao_baixa_o_arquivo_de_novo(client: TestClient) -> None:
    """`no-cache` é "confirme antes de usar", não "baixe sempre"."""
    primeira = client.get("/css/tokens.css")
    etag = primeira.headers["etag"]

    segunda = client.get("/css/tokens.css", headers={"If-None-Match": etag})

    assert segunda.status_code == 304
    assert not segunda.content
