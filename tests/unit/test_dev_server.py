"""Servidor de desenvolvimento: subir, parar, reconciliar e ler o log.

Os testes que sobem processo de verdade usam `python -c`, que existe em toda
máquina que roda esta suíte, e encerram o que sobem. Estão marcados como
`integration` porque tocam o sistema operacional.
"""

from __future__ import annotations

import os
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


# --- porta do comando x porta do cadastro ---------------------------------


def _manifesto(projeto, porta: int, service: str = "backend") -> None:
    (Path(projeto.path) / "devcockpit.yml").write_text(
        "\n".join(
            [
                "run:",
                f'  cmd: ["python", "-m", "uvicorn", "main:app", "--port", "{porta}"]',
                f'  service: "{service}"',
            ]
        ),
        encoding="utf-8",
    )


def _servico(projeto, session, porta: int, key: str = "backend") -> None:
    from app.models.project import ProjectService as ProjectServiceModel

    projeto.services.append(ProjectServiceModel(key=key, label=key.title(), port=porta))
    session.flush()


def test_manifesto_em_outra_porta_e_denunciado(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    """O caso do SmartDash: subia em 8000 e o painel verificava a 3001.

    O sintoma não aponta para a causa — o servidor sobe, o log não acusa nada,
    e a tela insiste em "fora do ar". Sem aviso, procura-se defeito no projeto.
    """
    _manifesto(projeto, 8000)
    _servico(projeto, session, 3001)

    aviso = servico.status(projeto).port_warning

    assert aviso is not None
    assert "8000" in aviso and "3001" in aviso


def test_portas_iguais_nao_geram_aviso(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    _manifesto(projeto, 3001)
    _servico(projeto, session, 3001)

    assert servico.status(projeto).port_warning is None


def test_sem_service_no_manifesto_nao_ha_contra_o_que_comparar(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    """Adivinhar qual serviço é o app produziria aviso falso em todo projeto
    que declara banco além do backend."""
    (Path(projeto.path) / "devcockpit.yml").write_text(
        'run:\n  cmd: ["python", "-m", "uvicorn", "main:app", "--port", "8000"]\n',
        encoding="utf-8",
    )
    _servico(projeto, session, 3001)

    assert servico.status(projeto).port_warning is None


def test_comando_sem_porta_legivel_nao_gera_aviso(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    """`npm run dev` decide a porta dentro do script. Chutar ali é pior que calar."""
    (Path(projeto.path) / "devcockpit.yml").write_text(
        'run:\n  cmd: ["npm", "run", "dev"]\n  service: "backend"\n',
        encoding="utf-8",
    )
    _servico(projeto, session, 3001)

    assert servico.status(projeto).port_warning is None


def test_aviso_compara_com_o_servico_que_o_plano_fornece(servico, projeto, session) -> None:  # type: ignore[no-untyped-def]
    """A porta do banco não tem nada a ver com a porta do app."""
    _manifesto(projeto, 3001)
    _servico(projeto, session, 5432, key="db")
    _servico(projeto, session, 3001)

    assert servico.status(projeto).port_warning is None


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
    assert session.query(DevServer).filter(DevServer.project_id == projeto.id).count() == 0


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


# --- remoção do projeto ---------------------------------------------------


def test_remover_projeto_encerra_o_servidor_dele(  # type: ignore[no-untyped-def]
    session, workspace, tmp_path, monkeypatch
) -> None:
    """O PID só existe na linha de `dev_server`. Apagar o projeto sem parar o
    processo apagava justamente o PID: sobrava um servidor de pé que só o
    Gerenciador de Tarefas alcança, ocupando a porta."""
    from app.services.project_service import ProjectService

    diretorio = workspace / "com-servidor"
    diretorio.mkdir()
    project = Project(id="com-servidor", name="Com Servidor", path=str(diretorio))
    session.add(project)
    # Antes do registro que o referencia: a chave estrangeira exige o projeto
    # já gravado, e os dois no mesmo flush não garantem a ordem.
    session.flush()
    session.add(
        DevServer(
            project_id=project.id,
            pid=4242,
            command="node server.js",
            cwd=str(diretorio),
            log_file="x.log",
            source="manifest",
        )
    )
    session.flush()

    encerrados: list[int] = []
    monkeypatch.setattr(
        "app.services.project_service.stop_background",
        lambda pid: encerrados.append(pid) or True,
    )

    ProjectService(session=session, allowed_roots=[workspace]).delete(project.id)

    assert encerrados == [4242]
    assert session.get(Project, "com-servidor") is None


def test_servidor_teimoso_nao_impede_a_remocao(session, workspace, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Travar a remoção por causa de um processo que não obedece deixaria o
    usuário com um projeto que ele não consegue tirar da tela."""
    from app.services.project_service import ProjectService

    diretorio = workspace / "teimoso"
    diretorio.mkdir()
    project = Project(id="teimoso", name="Teimoso", path=str(diretorio))
    session.add(project)
    session.flush()
    session.add(
        DevServer(
            project_id=project.id,
            pid=4243,
            command="node server.js",
            cwd=str(diretorio),
            log_file="x.log",
            source="manifest",
        )
    )
    session.flush()

    monkeypatch.setattr("app.services.project_service.stop_background", lambda pid: False)

    ProjectService(session=session, allowed_roots=[workspace]).delete(project.id)

    assert session.get(Project, "teimoso") is None


def test_remover_projeto_sem_servidor_nao_tenta_encerrar_nada(  # type: ignore[no-untyped-def]
    session, workspace, monkeypatch
) -> None:
    from app.services.project_service import ProjectService

    diretorio = workspace / "simples"
    diretorio.mkdir()
    session.add(Project(id="simples", name="Simples", path=str(diretorio)))
    session.flush()

    def nao_deveria(pid):  # type: ignore[no-untyped-def]
        raise AssertionError(f"tentou encerrar o pid {pid} sem servidor registrado")

    monkeypatch.setattr("app.services.project_service.stop_background", nao_deveria)

    ProjectService(session=session, allowed_roots=[workspace]).delete("simples")

    assert session.get(Project, "simples") is None


# --- visão global ---------------------------------------------------------


def test_lista_global_traz_o_nome_do_projeto(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """A lista é lida de fora do projeto, então o id sozinho não serve: quem
    olha "o que deixo ligado antes de fechar o notebook" pensa em nome."""
    from app.models.project import DevServer as DevServerModel
    from tests.conftest import WRITE_HEADERS

    diretorio = workspace / "global"
    diretorio.mkdir(exist_ok=True)
    criado = client.post(
        "/api/projects",
        json={"path": str(diretorio), "name": "Projeto Global", "run_detection": False},
        headers=WRITE_HEADERS,
    ).json()

    sessao = client.app.state.session_factory()
    try:
        sessao.add(
            DevServerModel(
                project_id=criado["id"],
                # O PID precisa existir para não ser descartado na
                # reconciliação: o do próprio processo de teste serve.
                pid=os.getpid(),
                command="npm run dev",
                cwd=str(diretorio),
                log_file="x.log",
                source="node",
            )
        )
        sessao.commit()
    finally:
        sessao.close()

    itens = client.get("/api/servers").json()["items"]

    assert len(itens) == 1
    assert itens[0]["project_name"] == "Projeto Global"
    assert itens[0]["command"] == "npm run dev"


def test_lista_global_descarta_processo_morto(client, workspace) -> None:  # type: ignore[no-untyped-def]
    """Quem abre a tela depois de um Ctrl+C no console do servidor não pode ver
    um processo que já não existe."""
    from app.models.project import DevServer as DevServerModel
    from tests.conftest import WRITE_HEADERS

    diretorio = workspace / "morto"
    diretorio.mkdir(exist_ok=True)
    criado = client.post(
        "/api/projects",
        json={"path": str(diretorio), "name": "Morto", "run_detection": False},
        headers=WRITE_HEADERS,
    ).json()

    sessao = client.app.state.session_factory()
    try:
        sessao.add(
            DevServerModel(
                project_id=criado["id"],
                pid=4_000_000_000,
                command="npm run dev",
                cwd=str(diretorio),
                log_file="x.log",
                source="node",
            )
        )
        sessao.commit()
    finally:
        sessao.close()

    assert client.get("/api/servers").json()["items"] == []
