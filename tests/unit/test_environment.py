"""Ordem de subida e assimetria da descida.

O modelo que estes testes fixam: o Docker sobe o ambiente, a aplicação sobe em
cima dele, e "Desligar" para só a aplicação. A assimetria é a parte que mais
parece bug para quem lê o código sem contexto, então cada teste diz por que ela
existe.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from app.jobs.job import Job
from app.models.project import Project
from app.models.project import ProjectService as ProjectServiceModel
from app.runner.command_spec import CommandResult
from app.services.dev_server_service import DevServerService
from app.services.environment_service import EnvironmentService, NothingToStart
from app.services.health_service import HealthResult, HealthState


class RunnerFalso:
    """Executa nada e devolve o que mandarem, registrando o argv recebido."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.chamadas: list[list[str]] = []

    async def run(self, spec, on_line=None, cancel_event=None):  # type: ignore[no-untyped-def]
        self.chamadas.append(spec.argv)
        if on_line is not None:
            on_line("stdout", "Container app-db-1  Started")
        return CommandResult(
            exit_code=0 if self.ok else 1,
            stdout="",
            stderr="" if self.ok else "boom",
            duration_ms=1,
        )


class HealthFalso:
    """Diz quem responde. `sempre_online` cobre o caminho feliz."""

    def __init__(self, online: set[str] | None = None, sempre_online: bool = False) -> None:
        self.online = online or set()
        self.sempre_online = sempre_online
        self.rodadas = 0

    async def check_many(self, targets):  # type: ignore[no-untyped-def]
        self.rodadas += 1
        return [
            HealthResult(
                project_id=alvo.project_id,
                key=alvo.key,
                state=(
                    HealthState.ONLINE
                    if self.sempre_online or alvo.key in self.online
                    else HealthState.OFFLINE
                ),
            )
            for alvo in targets
        ]


@pytest.fixture
def projeto(session, workspace: Path) -> Project:  # type: ignore[no-untyped-def]
    diretorio = workspace / "app"
    diretorio.mkdir()
    project = Project(id="app", name="App", path=str(diretorio))
    session.add(project)
    session.flush()
    return project


def com_compose(projeto: Project) -> None:
    (Path(projeto.path) / "docker-compose.yml").write_text(
        "services:\n  db:\n    image: postgres\n", encoding="utf-8"
    )


def com_run(projeto: Project, service: str | None = None) -> None:
    linhas = ['run:', '  cmd: ["node", "server.js"]']
    if service:
        linhas.append(f'  service: "{service}"')
    (Path(projeto.path) / "devcockpit.yml").write_text(
        "\n".join(linhas) + "\n", encoding="utf-8"
    )


def servico(session_factory, tmp_path, health=None, runner=None):  # type: ignore[no-untyped-def]
    from app.adapters.docker.adapter import DockerAdapter
    from app.runner.fake import FakeCommandRunner

    return EnvironmentService(
        session_factory=session_factory,
        adapter=DockerAdapter(runner=FakeCommandRunner()),
        health=health or HealthFalso(sempre_online=True),
        logs_dir=tmp_path / "logs",
        runner=runner or RunnerFalso(),
    )


# --- o plano --------------------------------------------------------------


def test_projeto_so_com_compose_nao_tem_aplicacao_separada(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """A stack inteira em container: o Compose **é** a aplicação."""
    com_compose(projeto)
    servers = DevServerService(session=session, logs_dir=tmp_path)

    plano = servico(session_factory, tmp_path).plan(projeto, servers)

    assert plano.has_docker is True
    assert plano.has_app is False


def test_run_declarado_torna_o_compose_ambiente(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    com_compose(projeto)
    com_run(projeto)
    servers = DevServerService(session=session, logs_dir=tmp_path)

    plano = servico(session_factory, tmp_path).plan(projeto, servers)

    assert plano.has_docker is True
    assert plano.has_app is True
    assert plano.app_command == "node server.js"


def test_a_porta_do_proprio_app_nao_entra_na_espera(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Esperar a porta do app antes de subir o app estouraria o teto sempre."""
    com_compose(projeto)
    com_run(projeto, service="backend")
    projeto.services.append(ProjectServiceModel(key="backend", label="Backend", port=8000))
    projeto.services.append(ProjectServiceModel(key="db", label="DB", port=5432))
    session.flush()
    servers = DevServerService(session=session, logs_dir=tmp_path)

    plano = servico(session_factory, tmp_path).plan(projeto, servers)

    assert plano.dependencies == ["db"]


def test_sem_run_service_o_primeiro_servico_com_porta_e_o_app(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Mesma escolha que decide a porta passada ao comando — as duas têm que
    concordar, senão a espera inclui a porta que o comando vai abrir."""
    com_compose(projeto)
    com_run(projeto)
    projeto.services.append(ProjectServiceModel(key="web", label="Web", port=3000))
    projeto.services.append(ProjectServiceModel(key="cache", label="Cache", port=6379))
    session.flush()
    servers = DevServerService(session=session, logs_dir=tmp_path)

    plano = servico(session_factory, tmp_path).plan(projeto, servers)

    assert plano.dependencies == ["cache"]


def test_servico_sem_porta_nao_entra_na_espera(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Não há o que perguntar a um serviço sem porta."""
    com_compose(projeto)
    com_run(projeto, service="app")
    projeto.services.append(ProjectServiceModel(key="app", label="App", port=3000))
    projeto.services.append(ProjectServiceModel(key="worker", label="Worker", port=None))
    session.flush()
    servers = DevServerService(session=session, logs_dir=tmp_path)

    plano = servico(session_factory, tmp_path).plan(projeto, servers)

    assert plano.dependencies == []


# --- a subida -------------------------------------------------------------


async def test_up_sobe_o_compose_antes_da_aplicacao(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """A ordem inversa quebra: aplicação antes do banco morre no primeiro
    `connect`, ou entra em laço de retentativa que ninguém quer ler."""
    com_compose(projeto)
    session.commit()

    runner = RunnerFalso()
    env = servico(session_factory, tmp_path, runner=runner)
    job = Job(id="j1", action="environment.up", key="k")

    await env.up(job, projeto.id)

    assert len(runner.chamadas) == 1
    argv = runner.chamadas[0]
    assert "compose" in argv and "up" in argv and "-d" in argv


async def test_up_sem_compose_e_sem_comando_recusa_com_instrucao(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    session.commit()
    env = servico(session_factory, tmp_path)
    job = Job(id="j1", action="environment.up", key="k")

    with pytest.raises(NothingToStart, match="devcockpit.yml"):
        await env.up(job, projeto.id)


async def test_compose_que_falha_interrompe_antes_de_subir_a_aplicacao(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Subir a aplicação em cima de um ambiente que não subiu só produz um erro
    mais confuso, mais tarde."""
    com_compose(projeto)
    com_run(projeto)
    session.commit()

    env = servico(session_factory, tmp_path, runner=RunnerFalso(ok=False))
    job = Job(id="j1", action="environment.up", key="k")

    with pytest.raises(Exception, match="Compose falhou"):
        await env.up(job, projeto.id)


async def test_a_saida_do_compose_vai_para_o_console_do_job(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    com_compose(projeto)
    session.commit()

    env = servico(session_factory, tmp_path)
    job = Job(id="j1", action="environment.up", key="k")

    await env.up(job, projeto.id)

    assert any("Started" in linha for linha in job.lines)
    assert any("Containers no ar" in linha for linha in job.lines)


async def test_espera_termina_quando_a_dependencia_responde(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Esperar tempo fixo é chute: um Postgres vazio abre em dois segundos, com
    trinta giga em vinte."""
    com_compose(projeto)
    com_run(projeto, service="web")
    projeto.services.append(ProjectServiceModel(key="web", label="Web", port=3000))
    projeto.services.append(ProjectServiceModel(key="db", label="DB", port=5432))
    session.commit()

    health = HealthFalso(online={"db"})
    env = servico(session_factory, tmp_path, health=health)
    job = Job(id="j1", action="environment.up", key="k")

    # Subir o app de verdade é barrado pela rede de proteção do conftest — e é
    # isso mesmo que se quer aqui. O que este teste afirma é o que veio antes:
    # a espera terminou numa rodada só, assim que a dependência respondeu.
    with pytest.raises(AssertionError, match="processo de longa duração"):
        await env.up(job, projeto.id)

    assert health.rodadas == 1
    assert any("Dependências prontas" in linha for linha in job.lines)


async def test_dependencia_que_nunca_responde_nao_trava_para_sempre(
    session, session_factory, projeto, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Travar o clique indefinidamente é pior que subir e deixar a aplicação
    reclamar, que é o que ela faria no terminal de qualquer jeito."""
    import app.services.environment_service as modulo

    monkeypatch.setattr(modulo, "DEPENDENCY_TIMEOUT_S", 0.2)
    monkeypatch.setattr(modulo, "DEPENDENCY_POLL_S", 0.05)

    com_compose(projeto)
    com_run(projeto, service="web")
    projeto.services.append(ProjectServiceModel(key="web", label="Web", port=3000))
    projeto.services.append(ProjectServiceModel(key="db", label="DB", port=5432))
    session.commit()

    env = servico(session_factory, tmp_path, health=HealthFalso(online=set()))
    job = Job(id="j1", action="environment.up", key="k")

    with pytest.raises(AssertionError, match="processo de longa duração"):
        await asyncio.wait_for(env.up(job, projeto.id), timeout=10)

    assert any("Subindo a aplicação assim mesmo" in linha for linha in job.lines)


# --- a descida ------------------------------------------------------------


class ServidorNoAr(DevServerService):
    """Aplicação de pé, sem processo de verdade.

    Subir um processo só para depois matá-lo tornaria este teste dependente do
    sistema operacional, e `stop` mataria o interpretador se o pid registrado
    fosse o do próprio pytest.
    """

    def __init__(self, session, logs_dir) -> None:  # type: ignore[no-untyped-def]
        super().__init__(session=session, logs_dir=logs_dir)
        self.parou = False

    def status(self, project):  # type: ignore[no-untyped-def]
        return replace(super().status(project), running=True)

    def stop(self, project):  # type: ignore[no-untyped-def]
        self.parou = True
        return super().status(project)


def test_desligar_para_so_a_aplicacao_por_padrao(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Banco e fila são caros de subir e não mudam entre uma execução e outra
    da aplicação. Derrubá-los a cada parada do backend trocaria um ciclo de dois
    segundos por um de trinta."""
    com_compose(projeto)
    com_run(projeto)
    servers = ServidorNoAr(session, tmp_path)

    alvo = servico(session_factory, tmp_path).down(projeto, servers, include_docker=False)

    assert alvo == "app"
    assert servers.parou is True


def test_desligar_com_a_aplicacao_ja_parada_derruba_o_compose(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """O caso do Dashdate: plano de `uvicorn` declarado, `uvicorn` parado, e o
    container atendendo na porta. Decidir pelo plano em vez do estado fazia o
    "Desligar" parar uma aplicação que já estava parada e responder sucesso —
    com o projeto seguindo no ar. Três cliques assim e a conclusão razoável é
    que o botão não funciona."""
    com_compose(projeto)
    com_run(projeto)
    servers = DevServerService(session=session, logs_dir=tmp_path)

    alvo = servico(session_factory, tmp_path).down(projeto, servers, include_docker=False)

    assert alvo == "docker"


def test_desligar_sem_nada_no_ar_e_sem_compose_diz_que_nao_havia_nada(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Não há o que parar. Dizer isso é melhor que responder "app" e não fazer
    nada — que era o comportamento antigo."""
    com_run(projeto)
    servers = DevServerService(session=session, logs_dir=tmp_path)

    alvo = servico(session_factory, tmp_path).down(projeto, servers, include_docker=False)

    assert alvo == "nothing"


def test_desligar_sem_aplicacao_separada_para_o_compose(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Senão "Desligar" não faria nada — a pior resposta possível a um clique."""
    com_compose(projeto)
    servers = DevServerService(session=session, logs_dir=tmp_path)

    alvo = servico(session_factory, tmp_path).down(projeto, servers, include_docker=False)

    assert alvo == "docker"


def test_desligar_completo_quando_pedido(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    com_compose(projeto)
    com_run(projeto)
    servers = DevServerService(session=session, logs_dir=tmp_path)

    alvo = servico(session_factory, tmp_path).down(projeto, servers, include_docker=True)

    assert alvo == "docker"


# --- falha de porta ocupada ----------------------------------------------


class RunnerQueFalhaPorPorta(RunnerFalso):
    """Reproduz a saída real do Docker quando a porta já está tomada."""

    def __init__(self, saida: str) -> None:
        super().__init__(ok=False)
        self.saida = saida

    async def run(self, spec, on_line=None, cancel_event=None):  # type: ignore[no-untyped-def]
        self.chamadas.append(spec.argv)
        return CommandResult(exit_code=1, stdout="", stderr=self.saida, duration_ms=1)


class DescobertaFalsa:
    def __init__(self, portas) -> None:  # type: ignore[no-untyped-def]
        self._portas = portas

    def last_known(self):  # type: ignore[no-untyped-def]
        from app.services.port_discovery_service import PortObservation

        return PortObservation(ports=self._portas)


@pytest.mark.parametrize(
    ("saida", "porta"),
    [
        (
            "Error response from daemon: failed to set up container networking: "
            "driver failed programming external connectivity on endpoint app-db-1 "
            "(5be7): Bind for 0.0.0.0:5432 failed: port is already allocated",
            5432,
        ),
        ("listen tcp 0.0.0.0:3000: bind: address already in use", 3000),
    ],
)
def test_extrai_a_porta_das_duas_formas_do_docker(saida: str, porta: int) -> None:
    """As duas formas trazem o número em posições diferentes da frase."""
    from app.services.environment_service import _porta_ocupada

    assert _porta_ocupada(saida) == porta


def test_falha_que_nao_e_de_porta_nao_inventa_culpado() -> None:
    from app.services.environment_service import _porta_ocupada

    assert _porta_ocupada("Error: pull access denied for foo/bar") is None


async def test_porta_ocupada_diz_quem_esta_com_ela(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """"Port is already allocated" é a falha mais comum e a mais inútil como o
    Docker a entrega: diz que a porta está ocupada e não diz por quem."""
    from app.services.port_discovery_service import ObservedPort

    com_compose(projeto)
    session.commit()

    env = servico(
        session_factory,
        tmp_path,
        runner=RunnerQueFalhaPorPorta(
            "Bind for 0.0.0.0:5432 failed: port is already allocated"
        ),
    )
    env.discovery = DescobertaFalsa(
        [
            ObservedPort(
                port=5432,
                pid=9,
                process_name="com.docker.backend.exe",
                project_name="Outro Projeto",
                matched_by="container",
            )
        ]
    )
    job = Job(id="j1", action="environment.up", key="k")

    with pytest.raises(Exception, match="Outro Projeto"):
        await env.up(job, projeto.id)

    assert any("5432" in linha and "ocupada" in linha for linha in job.lines)


async def test_sem_descoberta_a_mensagem_continua_correta(
    session, session_factory, projeto, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """A descoberta é opcional: sem ela o aviso perde o nome, não a verdade."""
    com_compose(projeto)
    session.commit()

    env = servico(
        session_factory,
        tmp_path,
        runner=RunnerQueFalhaPorPorta(
            "Bind for 0.0.0.0:5432 failed: port is already allocated"
        ),
    )
    job = Job(id="j1", action="environment.up", key="k")

    with pytest.raises(Exception, match="5432"):
        await env.up(job, projeto.id)
