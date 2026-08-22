"""GitAdapter: argv produzido e parse da saída.

As fixtures foram capturadas de execução real do `git` 2.x no Windows, com o
comando exato que o adapter monta. Fixture inventada à mão é a origem clássica
do teste que passa e do código que falha (docs/10-testing-strategy.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.git.adapter import GitAdapter, parse_log, parse_remotes, parse_status
from app.adapters.git.models import provider_from_url
from app.runner.command_spec import CommandResult
from app.runner.fake import FakeCommandRunner

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "git"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok(stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="", duration_ms=5)


def at_root(project_dir: Path, **extra: CommandResult) -> FakeCommandRunner:
    """Runner que responde que o diretório É a raiz do repositório."""
    return FakeCommandRunner({"git.toplevel": ok(str(project_dir)), **extra})


# --- argv produzido ------------------------------------------------------


def test_status_usa_formato_estavel(tmp_path: Path) -> None:
    runner = at_root(tmp_path, **{"git.status": ok(fixture("status_clean.txt"))})

    GitAdapter(runner).status(tmp_path)

    argv = runner.argv_for("git.status")
    assert argv[0] == "git"
    assert "--porcelain=v2" in argv
    assert "--branch" in argv


def test_log_limita_e_usa_separador_proprio(tmp_path: Path) -> None:
    runner = FakeCommandRunner({"git.log": ok(fixture("log_two_commits.txt"))})

    GitAdapter(runner).log(tmp_path, limit=5)

    argv = runner.argv_for("git.log")
    assert "-n5" in argv
    assert any(part.startswith("--format=") and "\x1f" in part for part in argv)


def test_limite_de_log_e_saneado(tmp_path: Path) -> None:
    runner = FakeCommandRunner({"git.log": ok("")})

    GitAdapter(runner).log(tmp_path, limit=99999)

    assert "-n200" in runner.argv_for("git.log")


def test_desliga_prompt_do_terminal(tmp_path: Path) -> None:
    """Um `git` que pede senha travaria até o timeout."""
    runner = at_root(tmp_path, **{"git.status": ok(fixture("status_clean.txt"))})

    GitAdapter(runner).status(tmp_path)

    assert runner.calls[0].env_extra["GIT_TERMINAL_PROMPT"] == "0"


def test_adapter_nunca_monta_comando_de_escrita(tmp_path: Path) -> None:
    """FR-038: nenhuma operação altera o repositório."""
    runner = FakeCommandRunner()
    adapter = GitAdapter(runner)

    adapter.is_repo(tmp_path)
    adapter.status(tmp_path)
    adapter.log(tmp_path)
    adapter.branches(tmp_path)
    adapter.remotes(tmp_path)

    proibidos = {"commit", "reset", "clean", "checkout", "push", "merge", "rebase"}
    for call in runner.calls:
        assert not proibidos & set(call.argv), f"comando de escrita em {call.argv}"


# --- parse de status -----------------------------------------------------


def test_repo_limpo() -> None:
    status = parse_status(fixture("status_clean.txt"))

    assert status.is_repo
    assert status.current_branch == "main"
    assert status.detached is False
    assert status.dirty_count == 0
    assert status.files == []
    assert status.head_sha.startswith("f25ac69")


def test_repo_sujo_conta_cada_tipo() -> None:
    status = parse_status(fixture("status_dirty.txt"))

    assert status.counts["modified"] == 1
    assert status.counts["deleted"] == 1
    assert status.counts["added"] == 1
    assert status.counts["untracked"] == 1
    assert status.counts["staged"] == 1  # apenas d.txt está no índice
    assert {f.path for f in status.files} == {"a.txt", "b.txt", "c.txt", "d.txt"}


def test_detached_head() -> None:
    status = parse_status(fixture("status_detached.txt"))

    assert status.detached is True
    assert status.current_branch is None


def test_ahead_behind() -> None:
    status = parse_status(fixture("status_ahead_behind.txt"))

    assert status.ahead == 3
    assert status.behind == 2


def test_sem_upstream_nao_inventa_ahead_behind() -> None:
    status = parse_status(fixture("status_clean.txt"))

    assert status.ahead is None
    assert status.behind is None


def test_renomeado_e_caminho_com_espaco() -> None:
    status = parse_status(fixture("status_renamed_and_space.txt"))

    paths = {f.path for f in status.files}
    assert "docs/novo nome.md" in paths
    assert "pasta com espaco/arquivo.py" in paths
    assert status.counts["renamed"] == 1
    assert status.current_branch == "feature/nome-longo"


def test_limite_de_arquivos_marca_truncado() -> None:
    status = parse_status(fixture("status_dirty.txt"), file_limit=2)

    assert len(status.files) == 2
    assert status.files_truncated is True
    assert status.counts["modified"] == 1  # a contagem considera tudo


def test_saida_vazia_nao_quebra() -> None:
    status = parse_status("")

    assert status.is_repo
    assert status.dirty_count == 0


def test_status_com_exit_code_diferente_de_zero(tmp_path: Path) -> None:
    runner = at_root(
        tmp_path,
        **{"git.status": CommandResult(128, "", "fatal: not a git repository", 3)},
    )

    status = GitAdapter(runner).status(tmp_path)

    assert status.is_repo is False


# --- parse de log e remotes ----------------------------------------------


def test_log_com_virgula_e_pipe_no_assunto() -> None:
    commits = parse_log(fixture("log_two_commits.txt"))

    assert len(commits) == 2
    assert commits[0].sha == "f25ac69"
    assert commits[0].subject == "feat: primeiro commit"
    assert commits[1].subject == "fix: corrige, com virgula | e pipe"
    assert commits[0].date is not None


def test_log_vazio() -> None:
    assert parse_log("") == []


def test_remotes_deduplica_fetch_e_push() -> None:
    saida = (
        "origin\thttps://github.com/user/repo.git (fetch)\n"
        "origin\thttps://github.com/user/repo.git (push)\n"
        "upstream\thttps://github.com/outro/repo.git (fetch)\n"
    )

    remotes = parse_remotes(saida)

    assert [r.name for r in remotes] == ["origin", "upstream"]


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://github.com/user/repo.git", "github"),
        ("git@gitlab.com:user/repo.git", "gitlab"),
        ("https://bitbucket.org/user/repo", "bitbucket"),
        ("https://exemplo.dev/repo.git", "other"),
        (None, None),
    ],
)
def test_provider_inferido_da_url(url: str | None, esperado: str | None) -> None:
    assert provider_from_url(url) == esperado


# --- raiz do repositório (bug encontrado na Fase 2) -----------------------


def test_diretorio_dentro_de_repo_pai_nao_e_tratado_como_repo(tmp_path: Path) -> None:
    """O caso que motivou `locate_repo`.

    Numa máquina com repositório em `C:/Users/User`, `git` responde a partir de
    qualquer subdiretório. Sem esta checagem, trinta projetos exibiriam a
    branch e os arquivos sujos do repositório pai.
    """
    projeto = tmp_path / "meu-projeto"
    projeto.mkdir()
    repo_pai = tmp_path
    runner = FakeCommandRunner({"git.toplevel": ok(str(repo_pai))})

    status = GitAdapter(runner).status(projeto)

    assert status.is_repo is False
    assert status.inside_other_repo is True
    assert status.repo_root == repo_pai.resolve().as_posix()
    # e, principalmente: nenhum `git status` chegou a ser executado
    runner.assert_never_ran("git.status")


def test_diretorio_que_e_a_raiz_e_tratado_como_repo(tmp_path: Path) -> None:
    runner = at_root(tmp_path, **{"git.status": ok(fixture("status_clean.txt"))})

    status = GitAdapter(runner).status(tmp_path)

    assert status.is_repo is True
    assert status.inside_other_repo is False
    assert status.current_branch == "main"


def test_sem_repositorio_algum(tmp_path: Path) -> None:
    runner = FakeCommandRunner(
        {"git.toplevel": CommandResult(128, "", "fatal: not a git repository", 2)}
    )

    status = GitAdapter(runner).status(tmp_path)

    assert status.is_repo is False
    assert status.inside_other_repo is False
    assert status.repo_root is None
