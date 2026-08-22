"""Descoberta, detecção aplicada ao projeto e contrato das rotas Git."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.api


def scan_now(client: TestClient, root: Path, max_depth: int | None = None) -> dict:
    """Dispara a varredura, espera o job e devolve os candidatos.

    Desde a Fase 3a a varredura é assíncrona (D-23): o `POST` devolve 202 com
    `job_id` e o resultado é buscado depois.
    """
    payload: dict = {"root": str(root)}
    if max_depth is not None:
        payload["max_depth"] = max_depth

    resposta = client.post("/api/discovery/scan", json=payload, headers=WRITE_HEADERS)
    assert resposta.status_code == 202, resposta.text
    job_id = resposta.json()["job_id"]

    deadline = time.time() + 20
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"}:
            assert job["status"] == "SUCCESS", job
            break
        time.sleep(0.05)
    else:
        raise AssertionError("a varredura não terminou a tempo")

    return client.get(
        "/api/discovery/candidates", params={"root": root.resolve().as_posix()}
    ).json()


def make_project(root: Path, name: str, **files: str) -> Path:
    project = root / name
    project.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (project / filename.replace("__", ".")).write_text(content, encoding="utf-8")
    return project


# --- detecção no cadastro -------------------------------------------------


def test_cadastro_ja_traz_stack_detectada(client: TestClient, workspace: Path) -> None:
    project = make_project(workspace, "api", requirements__txt="fastapi\npsycopg2\n")

    corpo = client.post(
        "/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS
    ).json()

    tecnologias = {tech["name"] for tech in corpo["technologies"]}
    assert {"python", "fastapi", "postgresql"} <= tecnologias
    assert all(tech["source"] == "DETECTED" for tech in corpo["technologies"])
    assert any(service["port"] == 8000 for service in corpo["services"])


def test_cadastro_sem_deteccao_quando_pedido(client: TestClient, workspace: Path) -> None:
    project = make_project(workspace, "api2", requirements__txt="fastapi\n")

    corpo = client.post(
        "/api/projects",
        json={"path": str(project), "run_detection": False},
        headers=WRITE_HEADERS,
    ).json()

    assert corpo["technologies"] == []


def test_redeteccao_encontra_stack_nova(client: TestClient, workspace: Path) -> None:
    project = make_project(workspace, "cresce", requirements__txt="flask\n")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)

    (project / "docker-compose.yml").write_text("services:\n  db:\n    image: postgres\n", "utf-8")
    diff = client.post("/api/projects/cresce/detect", headers=WRITE_HEADERS).json()

    assert "docker" in diff["added"]
    assert diff["compose_file"] == "docker-compose.yml"


def test_redeteccao_remove_stack_que_sumiu(client: TestClient, workspace: Path) -> None:
    project = make_project(workspace, "encolhe", requirements__txt="flask\n", Dockerfile="FROM x")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)

    (project / "Dockerfile").unlink()
    diff = client.post("/api/projects/encolhe/detect", headers=WRITE_HEADERS).json()

    assert "docker" in diff["removed"]


def test_deteccao_travada_e_ignorada(client: TestClient, workspace: Path) -> None:
    """FR-024: o usuário sempre tem a última palavra sobre a própria máquina."""
    project = make_project(workspace, "travado", requirements__txt="flask\n")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)
    client.patch(
        "/api/projects/travado", json={"detection_locked": True}, headers=WRITE_HEADERS
    )

    (project / "package.json").write_text('{"dependencies":{"react":"19"}}', encoding="utf-8")
    diff = client.post("/api/projects/travado/detect", headers=WRITE_HEADERS).json()

    assert diff["skipped"] is True
    assert diff["added"] == []


# --- descoberta -----------------------------------------------------------


def test_varredura_encontra_projetos_e_ignora_dependencias(
    client: TestClient, workspace: Path
) -> None:
    make_project(workspace, "projetos/api", requirements__txt="fastapi\n")
    make_project(workspace, "projetos/web", package__json=json.dumps({"dependencies": {}}))
    make_project(workspace, "projetos/web/node_modules/lib", package__json="{}")
    (workspace / "projetos" / "sem-nada").mkdir(parents=True)

    caminhos = {item["path"] for item in scan_now(client, workspace)["items"]}
    assert any(p.endswith("/api") for p in caminhos)
    assert any(p.endswith("/web") for p in caminhos)
    assert not any("node_modules" in p for p in caminhos)
    assert not any(p.endswith("sem-nada") for p in caminhos)


def test_varredura_nao_desce_dentro_de_projeto_encontrado(
    client: TestClient, workspace: Path
) -> None:
    """Um monorepo vira um candidato, não trinta."""
    make_project(workspace, "mono", package__json="{}")
    make_project(workspace, "mono/pacotes/a", package__json="{}")

    itens = scan_now(client, workspace)["items"]

    assert len([i for i in itens if "mono" in i["path"]]) == 1


def test_varredura_marca_ja_cadastrado(client: TestClient, workspace: Path) -> None:
    project = make_project(workspace, "conhecido", requirements__txt="flask\n")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)

    itens = scan_now(client, workspace)["items"]

    encontrado = next(i for i in itens if i["path"].endswith("conhecido"))
    assert encontrado["already_registered"] is True
    assert "flask" in encontrado["technologies"]


def test_varredura_respeita_profundidade(client: TestClient, workspace: Path) -> None:
    make_project(workspace, "a/b/c/d/fundo", requirements__txt="flask\n")

    raso = scan_now(client, workspace, max_depth=1)

    assert raso["items"] == []


def test_varredura_fora_do_root_e_recusada(client: TestClient, tmp_path: Path) -> None:
    fora = tmp_path / "outro"
    fora.mkdir()

    resposta = client.post(
        "/api/discovery/scan", json={"root": str(fora)}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "PATH_NOT_ALLOWED"


def test_importacao_em_lote_com_falha_parcial(client: TestClient, workspace: Path) -> None:
    bom = make_project(workspace, "bom", requirements__txt="flask\n")
    make_project(workspace, "repetido", requirements__txt="flask\n")
    repetido = workspace / "repetido"
    client.post("/api/projects", json={"path": str(repetido)}, headers=WRITE_HEADERS)

    resposta = client.post(
        "/api/discovery/import",
        json={"paths": [str(bom), str(repetido), str(workspace / "fantasma")]},
        headers=WRITE_HEADERS,
    ).json()

    assert resposta["imported"] == 1
    assert resposta["failed"] == 2
    codigos = {item["error_code"] for item in resposta["items"] if not item["ok"]}
    assert codigos == {"PROJECT_ALREADY_EXISTS", "PATH_NOT_FOUND"}


# --- rotas Git ------------------------------------------------------------


def test_status_de_diretorio_sem_git_nao_e_erro(client: TestClient, workspace: Path) -> None:
    """FR-030: ausência de repositório é informação, não falha."""
    project = make_project(workspace, "sem-git", requirements__txt="flask\n")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)

    resposta = client.get("/api/projects/sem-git/git/status")

    assert resposta.status_code == 200
    assert resposta.json()["is_repo"] is False


def test_status_de_projeto_com_diretorio_removido(client: TestClient, workspace: Path) -> None:
    project = make_project(workspace, "sumiu", requirements__txt="flask\n")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)
    (project / "requirements.txt").unlink()
    project.rmdir()

    resposta = client.get("/api/projects/sumiu/git/status")

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "PROJECT_DIR_MISSING"


def test_nao_existe_rota_de_escrita_git(client: TestClient, workspace: Path) -> None:
    """FR-038 verificado pelo contrato HTTP."""
    project = make_project(workspace, "leitura", requirements__txt="flask\n")
    client.post("/api/projects", json={"path": str(project)}, headers=WRITE_HEADERS)

    for caminho in ("commit", "reset", "push", "checkout", "clean"):
        resposta = client.post(
            f"/api/projects/leitura/git/{caminho}", json={}, headers=WRITE_HEADERS
        )
        assert resposta.status_code == 404, caminho
