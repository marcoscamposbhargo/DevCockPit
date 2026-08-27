"""Contrato HTTP das rotas de Docker.

Usa um runner fake injetado no app, então nenhum Docker real é tocado.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import RootsConfig, Settings
from app.main import create_app
from app.runner.command_spec import CommandResult
from app.runner.fake import FakeCommandRunner
from tests.conftest import LOCAL_ORIGIN, WRITE_HEADERS
from tests.support import FakeAsyncRunner

pytestmark = pytest.mark.api

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "docker"

COMPOSE_YML = """
services:
  backend:
    image: python:3.12
    ports:
      - "8000:8000"
  db:
    image: postgres:16
    ports:
      - "5432:5432"
"""


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fake_runner() -> FakeCommandRunner:
    return FakeCommandRunner(
        {
            "docker.ps": CommandResult(0, fixture("compose_ps_array.json"), "", 40),
            "docker.logs": CommandResult(0, fixture("compose_logs.txt"), "", 30),
        }
    )


@pytest.fixture
def fake_job_runner() -> FakeAsyncRunner:
    return FakeAsyncRunner(lines=["Container backend Started"])


@pytest.fixture
def docker_client(
    settings: Settings,
    roots: RootsConfig,
    fake_runner: FakeCommandRunner,
    fake_job_runner: FakeAsyncRunner,
) -> TestClient:
    """Os **dois** runners são dublados: o síncrono e o de jobs.

    Dublar só o síncrono deixaria as ações Compose subindo containers de
    verdade — foi o que aconteceu antes desta correção.
    """
    app = create_app(
        settings=settings, roots=roots, create_tables=True, start_poller=False
    )
    app.state.command_runner = fake_runner
    app.state.job_manager.runner = fake_job_runner
    with TestClient(app, base_url=LOCAL_ORIGIN) as client:
        yield client


@pytest.fixture
def project(docker_client: TestClient, workspace: Path) -> str:
    path = workspace / "stack"
    path.mkdir()
    (path / "docker-compose.yml").write_text(COMPOSE_YML, encoding="utf-8")

    resposta = docker_client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def wait_for_final(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job não terminou")


# --- status ---------------------------------------------------------------


def test_status_lista_containers(docker_client: TestClient, project: str) -> None:
    corpo = docker_client.get(f"/api/projects/{project}/docker/status").json()

    assert corpo["available"] is True
    assert corpo["compose_file"] == "docker-compose.yml"
    assert corpo["running_count"] == 1
    assert [c["service"] for c in corpo["containers"]] == ["backend", "db"]
    assert corpo["containers"][0]["ports"][0]["host_port"] == 8000


def test_status_expoe_servicos_declarados(docker_client: TestClient, project: str) -> None:
    """A UI usa isto para oferecer ação por serviço sem inventar nome."""
    corpo = docker_client.get(f"/api/projects/{project}/docker/status").json()

    assert corpo["declared_services"] == ["backend", "db"]


def test_projeto_sem_compose_nao_quebra(
    docker_client: TestClient, workspace: Path
) -> None:
    path = workspace / "sem-docker"
    path.mkdir()
    (path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    pid = docker_client.post(
        "/api/projects", json={"path": str(path)}, headers=WRITE_HEADERS
    ).json()["id"]

    resposta = docker_client.get(f"/api/projects/{pid}/docker/status")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["compose_file"] is None
    assert "Compose" in corpo["detail"]


def test_daemon_fora_do_ar_devolve_200(
    docker_client: TestClient, project: str, fake_runner: FakeCommandRunner
) -> None:
    """NFR-060: o dashboard não pode cair porque o Docker Desktop está fechado."""
    fake_runner.responses["docker.ps"] = CommandResult(
        1, "", fixture("daemon_down_stderr.txt"), 300
    )

    resposta = docker_client.get(f"/api/projects/{project}/docker/status")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["available"] is False
    assert "Docker Desktop" in corpo["detail"]


# --- ações ----------------------------------------------------------------


@pytest.mark.parametrize("action", ["up", "down", "start", "stop", "restart"])
def test_acoes_devolvem_202(docker_client: TestClient, project: str, action: str) -> None:
    resposta = docker_client.post(
        f"/api/projects/{project}/docker/{action}", json={}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 202
    corpo = resposta.json()
    assert corpo["action"] == f"docker.{action}"
    wait_for_final(docker_client, corpo["job_id"])


def test_acao_produz_argv_esperado(
    docker_client: TestClient, project: str, fake_job_runner: FakeAsyncRunner
) -> None:
    job_id = docker_client.post(
        f"/api/projects/{project}/docker/up", json={}, headers=WRITE_HEADERS
    ).json()["job_id"]
    wait_for_final(docker_client, job_id)

    argv = fake_job_runner.argv_for("docker.up")
    assert argv[:2] == ["docker", "compose"]
    assert argv[-3:] == ["up", "-d", "--remove-orphans"]
    assert "-v" not in argv


def test_saida_do_comando_aparece_no_job(
    docker_client: TestClient, project: str
) -> None:
    job_id = docker_client.post(
        f"/api/projects/{project}/docker/up", json={}, headers=WRITE_HEADERS
    ).json()["job_id"]

    job = wait_for_final(docker_client, job_id)

    assert "Container backend Started" in job["output"]


def test_segunda_acao_no_mesmo_projeto_da_409(
    docker_client: TestClient,
    project: str,
    settings: Settings,
    roots: RootsConfig,
) -> None:
    """FR-057: dois `up` no mesmo projeto não coexistem."""
    app = docker_client.app
    app.state.job_manager.runner = FakeAsyncRunner(hang=True)

    primeira = docker_client.post(
        f"/api/projects/{project}/docker/up", json={}, headers=WRITE_HEADERS
    )
    segunda = docker_client.post(
        f"/api/projects/{project}/docker/up", json={}, headers=WRITE_HEADERS
    )

    assert primeira.status_code == 202
    assert segunda.status_code == 409
    assert segunda.json()["error"]["code"] == "OPERATION_IN_PROGRESS"

    docker_client.post(
        f"/api/jobs/{primeira.json()['job_id']}/cancel", headers=WRITE_HEADERS
    )


def test_acao_invalida_devolve_422(docker_client: TestClient, project: str) -> None:
    resposta = docker_client.post(
        f"/api/projects/{project}/docker/prune", json={}, headers=WRITE_HEADERS
    )

    assert resposta.status_code == 422


def test_servico_inexistente_devolve_422_sem_executar(
    docker_client: TestClient, project: str
) -> None:
    """Defesa D2: nome de serviço é validado contra o Compose do projeto."""
    resposta = docker_client.post(
        f"/api/projects/{project}/docker/restart",
        json={"services": ["nao-existe"]},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client_jobs(docker_client) == []


def test_servico_valido_e_aceito(docker_client: TestClient, project: str) -> None:
    resposta = docker_client.post(
        f"/api/projects/{project}/docker/restart",
        json={"services": ["backend"]},
        headers=WRITE_HEADERS,
    )

    assert resposta.status_code == 202
    wait_for_final(docker_client, resposta.json()["job_id"])


def test_acao_exige_guard_de_escrita(docker_client: TestClient, project: str) -> None:
    resposta = docker_client.post(f"/api/projects/{project}/docker/up", json={})

    assert resposta.status_code == 403


def test_nao_existe_rota_para_down_com_volumes(
    docker_client: TestClient, project: str
) -> None:
    for caminho in ("down-v", "prune", "rm", "kill"):
        resposta = docker_client.post(
            f"/api/projects/{project}/docker/{caminho}", json={}, headers=WRITE_HEADERS
        )
        assert resposta.status_code in (404, 422), caminho


def client_jobs(client: TestClient) -> list[dict]:
    return client.get("/api/jobs").json()["items"]


# --- logs -----------------------------------------------------------------


def test_logs_devolvem_linhas(docker_client: TestClient, project: str) -> None:
    corpo = docker_client.get(
        f"/api/projects/{project}/docker/logs", params={"tail": 50}
    ).json()

    assert corpo["tail"] == 50
    assert len(corpo["lines"]) == 3
    assert "Started server process" in corpo["lines"][0]


def test_logs_de_servico_inexistente_devolve_422(
    docker_client: TestClient, project: str
) -> None:
    resposta = docker_client.get(
        f"/api/projects/{project}/docker/logs", params={"service": "fantasma"}
    )

    assert resposta.status_code == 422


def test_logs_com_daemon_fora_do_ar(
    docker_client: TestClient, project: str, fake_runner: FakeCommandRunner
) -> None:
    fake_runner.responses["docker.logs"] = CommandResult(
        1, "", fixture("daemon_down_stderr.txt"), 200
    )

    resposta = docker_client.get(f"/api/projects/{project}/docker/logs")

    assert resposta.status_code == 503
    assert resposta.json()["error"]["code"] == "DOCKER_UNAVAILABLE"


def test_compose_em_subpasta_e_encontrado(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Quem separa infraestrutura do código guarda o Compose em `infra/`.

    A detecção passou a enxergar monorepo, mas a aba Docker tem busca própria e
    continuava só na raiz — respondendo "nenhum arquivo Compose encontrado"
    para um projeto que tem um. O caminho volta relativo porque
    `docker compose -f` roda a partir da raiz do projeto.
    """
    from app.detection.detectors.docker_stack import find_compose_relativo

    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    assert find_compose_relativo(tmp_path) == "infra/docker-compose.yml"


def test_a_raiz_vence_a_subpasta_no_compose(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.detection.detectors.docker_stack import find_compose_relativo

    (tmp_path / "infra").mkdir()
    (tmp_path / "infra" / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    assert find_compose_relativo(tmp_path) == "docker-compose.yml"
