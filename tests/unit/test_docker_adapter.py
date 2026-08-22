"""DockerAdapter: argv produzido e parse da saída do Compose.

Fixtures capturadas do Compose **v5.3.1** nesta máquina. A versão importa: o
formato de `ps --format json` varia, e este é justamente o risco registrado no
roadmap para a Fase 3b.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.docker.adapter import (
    COMPOSE_ACTIONS,
    DockerAdapter,
    classify_failure,
    parse_ps,
    parse_publishers,
)
from app.runner.command_spec import CommandResult
from app.runner.fake import FakeCommandRunner

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "docker"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok(stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="", duration_ms=40)


# --- argv produzido ------------------------------------------------------


def test_ps_pede_json_e_inclui_parados(tmp_path: Path) -> None:
    runner = FakeCommandRunner({"docker.ps": ok(fixture("compose_ps_running.jsonl"))})

    DockerAdapter(runner).status(tmp_path, "docker-compose.yml")

    argv = runner.argv_for("docker.ps")
    assert argv[:2] == ["docker", "compose"]
    assert "-f" in argv and "docker-compose.yml" in argv
    assert "--format" in argv and "json" in argv
    # `--all` é o que mostra container parado, que é informação relevante.
    assert "--all" in argv


def test_up_nao_usa_flag_de_volume(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    adapter = DockerAdapter(runner)

    spec = adapter.action_spec(tmp_path, "docker-compose.yml", "up", [], timeout_s=300)

    assert spec.argv[-3:] == ["up", "-d", "--remove-orphans"]
    assert "-v" not in spec.argv
    assert "--volumes" not in spec.argv


def test_nenhuma_acao_permitida_remove_volume_ou_faz_prune() -> None:
    """Defesa D6: perder volume é perder dado, e não há caminho para isso."""
    proibido = {"-v", "--volumes", "prune", "rm", "--force", "-f"}

    for action, args in COMPOSE_ACTIONS.items():
        assert not proibido & set(args), f"ação {action} expõe flag destrutiva: {args}"


def test_acao_desconhecida_e_recusada_no_adapter(tmp_path: Path) -> None:
    adapter = DockerAdapter(FakeCommandRunner())

    with pytest.raises(ValueError, match="não permitida"):
        adapter.action_spec(tmp_path, None, "rm", [], timeout_s=10)


def test_servicos_entram_ao_final_do_argv(tmp_path: Path) -> None:
    adapter = DockerAdapter(FakeCommandRunner())

    spec = adapter.action_spec(tmp_path, "compose.yml", "restart", ["backend"], timeout_s=60)

    assert spec.argv[-1] == "backend"
    assert spec.timeout_s == 60


def test_logs_limita_o_tail(tmp_path: Path) -> None:
    adapter = DockerAdapter(FakeCommandRunner())

    spec = adapter.logs_spec(tmp_path, None, "backend", tail=999_999)

    assert "--tail" in spec.argv
    assert spec.argv[spec.argv.index("--tail") + 1] == "2000"
    assert "--no-color" in spec.argv


def test_sem_compose_file_nao_passa_flag_f(tmp_path: Path) -> None:
    adapter = DockerAdapter(FakeCommandRunner())

    spec = adapter.ps_spec(tmp_path, None)

    assert "-f" not in spec.argv


# --- parse: saída real ---------------------------------------------------


def test_parse_json_por_linha_saida_real() -> None:
    containers = parse_ps(fixture("compose_ps_running.jsonl"))

    assert len(containers) == 1
    container = containers[0]
    assert container.name == "zap-crm-local"
    assert container.service == "zap-crm"
    assert container.state == "running"
    assert container.health == "unhealthy"
    assert container.image == "zapcrm-zap-crm"
    assert container.is_running is True


def test_parse_array_json() -> None:
    """Outras versões do Compose devolvem array; o parser aceita os dois."""
    containers = parse_ps(fixture("compose_ps_array.json"))

    assert [c.service for c in containers] == ["backend", "db"]
    assert containers[1].state == "exited"
    assert containers[1].exit_code == 1
    assert containers[1].is_running is False


def test_portas_publicadas_deduplicadas() -> None:
    """`Publishers` traz IPv4 e IPv6 para a mesma porta."""
    containers = parse_ps(fixture("compose_ps_running.jsonl"))

    ports = containers[0].ports
    assert len(ports) == 1
    assert ports[0].host_port == 5000
    assert ports[0].container_port == 5000
    assert str(ports[0]) == "5000->5000/tcp"


def test_container_sem_porta_publicada() -> None:
    containers = parse_ps(fixture("compose_ps_array.json"))

    assert containers[1].ports == []


def test_saida_vazia_devolve_lista_vazia() -> None:
    assert parse_ps("") == []
    assert parse_ps("   \n  ") == []


def test_linha_malformada_nao_zera_a_lista() -> None:
    """Uma versão que intercale ruído não pode fazer sumir os containers."""
    containers = parse_ps(fixture("compose_ps_malformed.jsonl"))

    assert [c.name for c in containers] == ["ok-1", "ok-2"]


def test_aviso_do_compose_e_ignorado() -> None:
    saida = (
        'time="2026-08-21T21:21:10-03:00" level=warning msg="version is obsolete"\n'
        + fixture("compose_ps_running.jsonl")
    )

    assert len(parse_ps(saida)) == 1


@pytest.mark.parametrize(
    ("publishers", "esperado"),
    [
        ([{"PublishedPort": 8000, "TargetPort": 8000, "Protocol": "tcp"}], [8000]),
        ([{"PublishedPort": 0, "TargetPort": 80}], []),
        ([{"TargetPort": 80}], []),
        ("nao-e-lista", []),
        (None, []),
    ],
)
def test_parse_publishers(publishers: object, esperado: list[int]) -> None:
    ports = parse_publishers({"Publishers": publishers})

    assert [port.host_port for port in ports] == esperado


# --- degradação ----------------------------------------------------------


def test_daemon_fora_do_ar_nao_e_erro(tmp_path: Path) -> None:
    """NFR-060: o dashboard continua respondendo com o Docker desligado."""
    runner = FakeCommandRunner(
        {"docker.ps": CommandResult(1, "", fixture("daemon_down_stderr.txt"), 300)}
    )

    status = DockerAdapter(runner).status(tmp_path, "docker-compose.yml")

    assert status.available is False
    assert "Docker Desktop" in status.detail
    assert status.containers == []


def test_sem_arquivo_compose(tmp_path: Path) -> None:
    runner = FakeCommandRunner(
        {"docker.ps": CommandResult(1, "", fixture("no_compose_stderr.txt"), 50)}
    )

    status = DockerAdapter(runner).status(tmp_path, None)

    assert status.available is True
    assert "Compose" in status.detail


@pytest.mark.parametrize(
    ("stderr", "esperado"),
    [
        ("error during connect: ...", "daemon_down"),
        ("Cannot connect to the Docker daemon", "daemon_down"),
        ("no configuration file provided: not found", "no_compose"),
        ("qualquer outra coisa", "unknown"),
    ],
)
def test_classificacao_de_falha(stderr: str, esperado: str) -> None:
    assert classify_failure(stderr) == esperado


def test_versao_do_compose(tmp_path: Path) -> None:
    """Detecção de versão: o formato de saída depende dela."""
    runner = FakeCommandRunner({"docker.version": ok("v5.3.1\n")})

    assert DockerAdapter(runner).compose_version(tmp_path) == "v5.3.1"


def test_versao_indisponivel_devolve_none(tmp_path: Path) -> None:
    runner = FakeCommandRunner({"docker.version": CommandResult(127, "", "not found", 5)})

    assert DockerAdapter(runner).compose_version(tmp_path) is None
