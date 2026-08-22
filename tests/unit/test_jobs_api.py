"""Contrato HTTP das rotas de job e da varredura assíncrona."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import WRITE_HEADERS

pytestmark = pytest.mark.api


def wait_for_final(client: TestClient, job_id: str, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} não terminou em {timeout}s")


def make_project(root: Path, name: str, **files: str) -> Path:
    project = root / name
    project.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (project / filename.replace("__", ".")).write_text(content, encoding="utf-8")
    return project


# --- varredura como job (D-23) -------------------------------------------


def test_scan_devolve_202_com_job_id(client: TestClient, workspace: Path) -> None:
    make_project(workspace, "api", requirements__txt="fastapi\n")

    resposta = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 202
    corpo = resposta.json()
    assert corpo["job_id"].startswith("j_")
    assert corpo["action"] == "discovery.scan"


def test_scan_conclui_e_candidatos_ficam_disponiveis(
    client: TestClient, workspace: Path
) -> None:
    make_project(workspace, "api", requirements__txt="fastapi\n")
    make_project(workspace, "web", package__json='{"dependencies":{"react":"19"}}')

    job_id = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    ).json()["job_id"]

    job = wait_for_final(client, job_id)
    assert job["status"] == "SUCCESS"
    assert "candidato" in job["message"]

    root = workspace.resolve().as_posix()
    candidatos = client.get("/api/discovery/candidates", params={"root": root}).json()

    nomes = {item["suggested_name"] for item in candidatos["items"]}
    assert {"api", "web"} <= nomes


def test_scan_com_root_proibido_falha_na_hora_e_nao_vira_job(
    client: TestClient, tmp_path: Path
) -> None:
    """Erro de allowlist tem que aparecer imediatamente, não escondido num job."""
    fora = tmp_path / "fora"
    fora.mkdir()

    resposta = client.post(
        "/api/discovery/scan", json={"root": str(fora)}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "PATH_NOT_ALLOWED"
    assert client.get("/api/jobs").json()["items"] == []


def test_duas_varreduras_simultaneas_dao_conflito(
    client: TestClient, workspace: Path
) -> None:
    for indice in range(40):
        make_project(workspace, f"p{indice}/sub/proj", requirements__txt="flask\n")

    primeira = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    )
    segunda = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    )

    assert primeira.status_code == 202
    # A primeira pode ter terminado antes da segunda chegar; o que não pode é
    # haver duas rodando.
    assert segunda.status_code in (202, 409)
    if segunda.status_code == 409:
        assert segunda.json()["error"]["code"] == "OPERATION_IN_PROGRESS"


# --- consulta de job ------------------------------------------------------


def test_job_inexistente_devolve_404(client: TestClient) -> None:
    resposta = client.get("/api/jobs/j_naoexiste")

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_listagem_de_jobs(client: TestClient, workspace: Path) -> None:
    make_project(workspace, "api", requirements__txt="fastapi\n")
    job_id = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    ).json()["job_id"]
    wait_for_final(client, job_id)

    items = client.get("/api/jobs").json()["items"]

    assert any(item["id"] == job_id for item in items)


def test_after_devolve_so_o_que_falta(client: TestClient, workspace: Path) -> None:
    """Fallback de polling: o cliente não rebaixa a saída inteira a cada tick."""
    make_project(workspace, "api", requirements__txt="fastapi\n")
    job_id = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    ).json()["job_id"]
    final = wait_for_final(client, job_id)

    assert final["line_count"] >= 2

    parcial = client.get(f"/api/jobs/{job_id}", params={"after": final["line_count"]}).json()
    assert parcial["output"] == ""
    assert parcial["line_count"] == final["line_count"]


def test_cancelar_job_ja_concluido_nao_quebra(client: TestClient, workspace: Path) -> None:
    make_project(workspace, "api", requirements__txt="fastapi\n")
    job_id = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    ).json()["job_id"]
    wait_for_final(client, job_id)

    resposta = client.post(f"/api/jobs/{job_id}/cancel", headers=WRITE_HEADERS)

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "SUCCESS"


def test_cancelar_exige_guard_de_escrita(client: TestClient) -> None:
    resposta = client.post("/api/jobs/j_qualquer/cancel")

    assert resposta.status_code == 403


# --- SSE ------------------------------------------------------------------


def test_stream_sse_emite_log_e_end(client: TestClient, workspace: Path) -> None:
    make_project(workspace, "api", requirements__txt="fastapi\n")
    job_id = client.post(
        "/api/discovery/scan", json={"root": str(workspace)}, headers=WRITE_HEADERS
    ).json()["job_id"]

    with client.stream("GET", f"/api/jobs/{job_id}/stream") as resposta:
        assert resposta.status_code == 200
        assert resposta.headers["content-type"].startswith("text/event-stream")

        eventos: list[str] = []
        payloads: list[dict] = []
        for linha in resposta.iter_lines():
            if linha.startswith("event: "):
                eventos.append(linha.removeprefix("event: "))
            elif linha.startswith("data: "):
                payloads.append(json.loads(linha.removeprefix("data: ")))
                # o `data` do evento `end` é a última coisa que chega
                if eventos and eventos[-1] == "end":
                    break

    assert "end" in eventos
    assert payloads[-1]["status"] == "SUCCESS"


def test_stream_de_job_inexistente_devolve_404(client: TestClient) -> None:
    assert client.get("/api/jobs/j_nada/stream").status_code == 404
