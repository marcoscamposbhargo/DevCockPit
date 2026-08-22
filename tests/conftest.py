"""Fixtures comuns.

Nenhum teste toca em `configs/roots.yml` real nem em projeto do usuário: os
roots apontam sempre para `tmp_path` (anti-padrão listado em `docs/10`).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import RootsConfig, Settings
from app.main import create_app
from app.models.base import Base, create_session_factory
from tests.support import FakeAsyncRunner

LOCAL_ORIGIN = "http://127.0.0.1:8765"
WRITE_HEADERS = {"X-DevCockpit-Client": "web", "Origin": LOCAL_ORIGIN}

INTEGRATION_MARKERS = {"integration", "integration_git", "integration_docker"}


@pytest.fixture(autouse=True)
def bloqueia_execucao_real_em_job(request, monkeypatch):  # type: ignore[no-untyped-def]
    """Rede de proteção: job não executa comando real fora de teste de integração.

    Um teste de API que enfileirava `docker compose up` chegou a **subir
    containers de verdade** nesta máquina. O runner síncrono estava dublado,
    mas jobs usam o assíncrono — e ninguém percebeu até o container aparecer no
    `docker ps`.

    Esquecer de dublar agora falha o teste com mensagem explícita, em vez de
    mexer no ambiente de quem roda a suíte.
    """
    if INTEGRATION_MARKERS & {mark.name for mark in request.node.iter_markers()}:
        return

    async def recusa(self, spec, on_line=None, cancel_event=None):  # type: ignore[no-untyped-def]
        raise AssertionError(
            f"Teste tentou executar comando real em job: {spec.argv}. "
            "Dublê `app.state.job_manager.runner` com `FakeAsyncRunner`, "
            "ou marque o teste como `integration`."
        )

    monkeypatch.setattr(
        "app.runner.async_runner.AsyncCommandRunner.run", recusa, raising=True
    )

    def recusa_processo(argv, cwd, log_file, env_extra=None):  # type: ignore[no-untyped-def]
        raise AssertionError(
            f"Teste tentou subir processo de longa duração: {argv}. "
            "Dublê `app.services.environment_service.EnvironmentService` ou o "
            "`start_background` usado, ou marque o teste como `integration`."
        )

    # O servidor de desenvolvimento não passa pelo `JobManager` — é um processo
    # de vida longa, e essa é a razão de ele existir fora dali. Sem esta segunda
    # rede, um teste que exercitasse a orquestração subiria `npm run dev` de
    # verdade na máquina de quem roda a suíte, e o processo **sobreviveria ao
    # pytest** de propósito: é o que o `CREATE_NEW_PROCESS_GROUP` garante.
    #
    # Aconteceu ao escrever `test_environment.py`: um `node server.js` nasceu
    # num diretório temporário do pytest. Foi assim que esta guarda apareceu.
    for alvo in (
        "app.runner.background.start_background",
        "app.services.dev_server_service.start_background",
    ):
        monkeypatch.setattr(alvo, recusa_processo, raising=True)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def roots(workspace: Path) -> RootsConfig:
    return RootsConfig(
        allowed_roots=[workspace.resolve()],
        scan_ignore=frozenset({"node_modules", ".venv"}),
        scan_max_depth=3,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        log_file=tmp_path / "test.log",
        log_format="plain",
        port=8765,
    )


@pytest.fixture
def session_factory(settings: Settings):  # type: ignore[no-untyped-def]
    factory = create_session_factory(settings.database_url)
    Base.metadata.create_all(factory.kw["bind"])
    return factory


@pytest.fixture
def session(session_factory) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(settings: Settings, roots: RootsConfig) -> Iterator[TestClient]:
    """App de teste com o runner de jobs dublado.

    Sem isso, um job enfileirado por um teste executaria comando de verdade —
    e já subiu containers na máquina uma vez. Ver `tests/support.py`.
    """
    # `start_poller=False`: tarefa de background em teste é fonte de
    # intermitência, e o que interessa aqui é o contrato HTTP. O poller tem
    # teste próprio.
    app = create_app(
        settings=settings, roots=roots, create_tables=True, start_poller=False
    )
    app.state.job_manager.runner = FakeAsyncRunner()
    with TestClient(app, base_url=LOCAL_ORIGIN) as test_client:
        yield test_client


@pytest.fixture
def sample_project(workspace: Path) -> Path:
    project = workspace / "dashboard-contabil"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return project
