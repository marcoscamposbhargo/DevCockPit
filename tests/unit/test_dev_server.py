"""Servidor de desenvolvimento: subir, parar, reconciliar e ler o log.

Os testes que sobem processo de verdade usam `python -c`, que existe em toda
máquina que roda esta suíte, e encerram o que sobem. Estão marcados como
`integration` porque tocam o sistema operacional.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from app.core.errors import ProjectDirMissing
from app.models.project import DevServer, Project
from app.runner.background import is_alive, start_background, stop_background, tail_log
from app.services.dev_server_service import (
    DevServerService,
    NoRunCommand,
)


@pytest.fixture
def projeto(session, workspace: Path) -> Project:  # type: ignore[no-untyped-def]
    diretorio = workspace / "app"
    diretorio.mkdir()
    project = Project(id="app", name="App", path=str(diretorio))
    session.add(project)
    session.flush()
    return project


@pytest.fixture
def servico(session, tmp_path: Path) -> DevServerService:  # type: ignore[no-untyped-def]
    return DevServerService(session=session, logs_dir=tmp_path / "logs")


# --- leitura do plano -----------------------------------------------------


def test_projeto_sem_pista_nao_pode_ser_ligado(servico, projeto) -> None:  # type: ignore[no-untyped-def]
    estado = servico.status(projeto)

    assert estado.running is False
    assert estado.can_start is False
    assert estado.command == ""


def test_status_mostra_o_comando_antes_do_clique(servico, projeto) -> None:  # type: ignore[no-untyped-def]
    """Ninguém deve descobrir o que o botão faz depois de apertá-lo."""
    (Path(projeto.path) / "package.json").write_text(
        '{"name":"x","scripts":{"dev":"vite"}}', encoding="utf-8"
    )

    estado = servico.status(projeto)

    assert estado.can_start is True
    assert estado.command == "npm run dev"
    assert estado.source == "node"
    assert "package.json" in estado.evidence


def test_ligar_sem_plano_explica_o_que_fazer(servico, projeto) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(NoRunCommand, match="devcockpit.yml"):
        servico.start(projeto)


def test_diretorio_sumido_nao_vira_plano(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    projeto.path = str(Path(projeto.path) / "nao-existe")

    assert servico.plan(projeto) is None
    with pytest.raises(ProjectDirMissing):
        servico.start(projeto)


def test_porta_declarada_entra_no_comando(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    """Um `uvicorn` sem `--port` sobe em 8000 e o painel verifica outra coisa."""
    from app.models.project import ProjectService as ProjectServiceModel

    (Path(projeto.path) / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    (Path(projeto.path) / "main.py").write_text("app = 1\n", encoding="utf-8")
    projeto.services.append(ProjectServiceModel(key="backend", label="Backend", port=9123))
    session.flush()

    assert "--port 9123" in servico.status(projeto).command


# --- reconciliação --------------------------------------------------------


def test_registro_de_processo_morto_e_descartado(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    """O processo morre por fora o tempo todo: Ctrl+C no console dele, erro de
    compilação, reinício da máquina. Um registro que sobrevive ao processo faz
    o painel oferecer "Parar" para algo que já não está lá."""
    session.add(
        DevServer(
            project_id=projeto.id,
            # PID que não existe: acima do teto usual de qualquer sistema.
            pid=4_000_000_000,
            command="fake",
            cwd=projeto.path,
            log_file="x.log",
            source="manifest",
        )
    )
    session.flush()

    estado = servico.status(projeto)

    assert estado.running is False
    assert (
        session.query(DevServer).filter(DevServer.project_id == projeto.id).count() == 0
    )


def test_parar_o_que_nao_esta_rodando_nao_e_erro(servico, projeto) -> None:  # type: ignore[no-untyped-def]
    """O resultado desejado já vale: o servidor está parado."""
    estado = servico.stop(projeto)

    assert estado.running is False


# --- log ------------------------------------------------------------------


def test_tail_le_so_o_fim_do_arquivo(tmp_path: Path) -> None:
    alvo = tmp_path / "grande.log"
    alvo.write_text("\n".join(f"linha {i}" for i in range(5000)), encoding="utf-8")

    linhas = tail_log(alvo, lines=10)

    assert len(linhas) == 10
    assert linhas[-1] == "linha 4999"


def test_tail_de_arquivo_inexistente_e_vazio(tmp_path: Path) -> None:
    assert tail_log(tmp_path / "nunca-existiu.log") == []


def test_log_e_lido_mesmo_com_o_servidor_parado(servico, projeto, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Depois de uma queda, o log é a única coisa que explica o que houve."""
    destino = tmp_path / "logs" / "servers" / f"{projeto.id}.log"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("Error: porta em uso\n", encoding="utf-8")

    assert servico.logs(projeto) == ["Error: porta em uso"]


# --- processo real --------------------------------------------------------


@pytest.mark.integration
def test_processo_sobe_escreve_no_log_e_morre_quando_mandado(tmp_path: Path) -> None:
    log = tmp_path / "servidor.log"
    iniciado = start_background(
        argv=[
            sys.executable,
            "-c",
            "import sys,time; print('subiu', flush=True); sys.stdout.flush(); time.sleep(60)",
        ],
        cwd=tmp_path,
        log_file=log,
    )

    try:
        # O processo escreve e segue vivo; o `sleep` cobre a partida do Python.
        limite = time.monotonic() + 15
        while time.monotonic() < limite and "subiu" not in "\n".join(tail_log(log)):
            time.sleep(0.2)

        assert "subiu" in "\n".join(tail_log(log))
        assert is_alive(iniciado.pid) is True
    finally:
        assert stop_background(iniciado.pid) is True

    limite = time.monotonic() + 10
    while time.monotonic() < limite and is_alive(iniciado.pid):
        time.sleep(0.2)
    assert is_alive(iniciado.pid) is False


@pytest.mark.integration
def test_parar_processo_que_ja_morreu_conta_como_sucesso() -> None:
    assert stop_background(4_000_000_000) is True


def test_pid_invalido_nunca_esta_vivo() -> None:
    assert is_alive(0) is False
    assert is_alive(-1) is False
