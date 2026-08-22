"""Testes do CommandSpec, da allowlist e do CommandRunner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core.errors import ActionNotAllowed, ValidationError
from app.runner.allowlist import (
    FORBIDDEN_FRAGMENTS,
    assert_registry_is_safe,
    get_action,
    known_actions,
    safe_choice,
    safe_int,
    safe_token,
)
from app.runner.command_runner import SubprocessCommandRunner
from app.runner.command_spec import CommandSpec
from app.runner.fake import FakeCommandRunner

pytestmark = pytest.mark.unit


# --- CommandSpec ---------------------------------------------------------


def test_spec_exige_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout"):
        CommandSpec(argv=["git", "--version"], cwd=tmp_path, timeout_s=0, label="x")


def test_spec_exige_argv_nao_vazio(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="argv"):
        CommandSpec(argv=[], cwd=tmp_path, timeout_s=5, label="x")


def test_spec_exige_label(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="label"):
        CommandSpec(argv=["git"], cwd=tmp_path, timeout_s=5, label="")


# --- allowlist -----------------------------------------------------------


def test_acao_desconhecida_e_recusada() -> None:
    with pytest.raises(ActionNotAllowed):
        get_action("docker.rm.tudo")


def test_acao_conhecida_produz_argv_esperado() -> None:
    action = get_action("tool.version.git")
    assert action.build("git") == ["git", "--version"]


def test_registro_nao_contem_acao_destrutiva() -> None:
    assert_registry_is_safe()
    for label in known_actions():
        action = get_action(label)
        try:
            argv = [part.lower() for part in action.build()]
        except TypeError:
            continue
        for fragment in FORBIDDEN_FRAGMENTS:
            assert not all(part in argv for part in fragment), f"{label} produz {argv}"


def test_safe_int_respeita_faixa() -> None:
    assert safe_int(20, minimum=1, maximum=200, name="limit") == "20"
    with pytest.raises(ValidationError):
        safe_int(500, minimum=1, maximum=200, name="limit")
    with pytest.raises(ValidationError):
        safe_int("abc", minimum=1, maximum=200, name="limit")


def test_safe_choice_recusa_valor_fora_do_conjunto() -> None:
    assert safe_choice("backend", allowed=["backend", "frontend"], name="service") == "backend"
    with pytest.raises(ValidationError):
        safe_choice("outro", allowed=["backend"], name="service")


def test_safe_token_recusa_valor_que_parece_flag() -> None:
    assert safe_token("backend-1", name="service") == "backend-1"
    with pytest.raises(ValidationError):
        safe_token("--force", name="service")
    with pytest.raises(ValidationError):
        safe_token("back end", name="service")


# --- FakeCommandRunner ---------------------------------------------------


def test_fake_registra_chamadas(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    spec = CommandSpec(
        argv=["git", "--version"], cwd=tmp_path, timeout_s=5, label="tool.version.git"
    )

    runner.run(spec)

    assert runner.labels == ["tool.version.git"]
    assert runner.argv_for("tool.version.git") == ["git", "--version"]
    runner.assert_never_ran("docker.up")


# --- SubprocessCommandRunner ---------------------------------------------


def test_executa_comando_real_simples(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    spec = CommandSpec(
        argv=[sys.executable, "-c", "print('ola')"],
        cwd=tmp_path,
        timeout_s=15,
        label="test.echo",
    )

    result = runner.run(spec)

    assert result.ok
    assert "ola" in result.stdout
    assert result.duration_ms >= 0


def test_metacaractere_de_shell_chega_intacto_sem_efeito(tmp_path: Path) -> None:
    """Verificação 10 de docs/07: `;` e `&&` são texto, não comando."""
    payload = "meu projeto & echo INVADIDO; rm -rf /"
    runner = SubprocessCommandRunner()
    spec = CommandSpec(
        argv=[sys.executable, "-c", "import sys; print(sys.argv[1])", payload],
        cwd=tmp_path,
        timeout_s=15,
        label="test.injection",
    )

    result = runner.run(spec)

    assert result.ok
    assert payload in result.stdout
    assert "INVADIDO" not in result.stdout.replace(payload, "")


def test_timeout_marca_resultado(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    spec = CommandSpec(
        argv=[sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        timeout_s=1,
        label="test.sleep",
    )

    result = runner.run(spec)

    assert result.timed_out
    assert not result.ok


def test_programa_inexistente_devolve_erro_claro(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    spec = CommandSpec(
        argv=["programa-que-nao-existe-devcockpit"],
        cwd=tmp_path,
        timeout_s=5,
        label="test.missing",
    )

    result = runner.run(spec)

    assert result.exit_code == 127
    assert "não encontrado" in result.stderr
