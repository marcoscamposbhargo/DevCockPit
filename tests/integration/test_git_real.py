"""Integração com `git` real, em repositório temporário criado pelo teste.

Nunca opera em repositório do usuário (anti-padrão listado em `docs/10`).
Rápido e determinístico, então roda por padrão.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 - o teste precisa preparar repositórios reais
from pathlib import Path

import pytest

from app.adapters.git.adapter import GitAdapter
from app.runner.command_runner import SubprocessCommandRunner

pytestmark = [
    pytest.mark.integration_git,
    pytest.mark.skipif(shutil.which("git") is None, reason="git não está no PATH"),
]


def git(cwd: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "teste@devcockpit.local")
    git(root, "config", "user.name", "Teste")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "feat: primeiro commit")
    return root


@pytest.fixture
def adapter() -> GitAdapter:
    return GitAdapter(SubprocessCommandRunner(), timeout_s=20)


def test_repo_limpo(adapter: GitAdapter, repo: Path) -> None:
    status = adapter.status(repo)

    assert status.is_repo is True
    assert status.current_branch == "main"
    assert status.dirty_count == 0


def test_repo_sujo(adapter: GitAdapter, repo: Path) -> None:
    (repo / "a.txt").write_text("mudou\n", encoding="utf-8")
    (repo / "novo.txt").write_text("novo\n", encoding="utf-8")

    status = adapter.status(repo)

    assert status.counts["modified"] == 1
    assert status.counts["untracked"] == 1


def test_arquivo_no_indice(adapter: GitAdapter, repo: Path) -> None:
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(repo, "add", "b.txt")

    status = adapter.status(repo)

    assert status.counts["staged"] == 1
    assert status.counts["added"] == 1


def test_detached_head(adapter: GitAdapter, repo: Path) -> None:
    git(repo, "checkout", "-q", "--detach", "HEAD")

    status = adapter.status(repo)

    assert status.detached is True
    assert status.current_branch is None


def test_caminho_com_espaco_e_acento(adapter: GitAdapter, repo: Path) -> None:
    pasta = repo / "pasta com acento é"
    pasta.mkdir()
    (pasta / "arquivo.txt").write_text("x", encoding="utf-8")

    status = adapter.status(repo)

    assert any("pasta com acento" in f.path for f in status.files)


def test_commits_e_branches(adapter: GitAdapter, repo: Path) -> None:
    git(repo, "branch", "feature/x")

    commits = adapter.log(repo, limit=5)
    branches = adapter.branches(repo)

    assert commits[0].subject == "feat: primeiro commit"
    assert commits[0].author == "Teste"
    assert set(branches) == {"main", "feature/x"}


def test_remote_configurado(adapter: GitAdapter, repo: Path) -> None:
    git(repo, "remote", "add", "origin", "https://github.com/usuario/repo.git")

    remotes = adapter.remotes(repo)

    assert remotes[0].name == "origin"
    assert "github.com" in remotes[0].url


def test_diretorio_sem_git_nao_e_repo(adapter: GitAdapter, tmp_path: Path) -> None:
    solto = tmp_path / "sem-git"
    solto.mkdir()

    status = adapter.status(solto)

    assert status.is_repo is False


def test_subdiretorio_nao_herda_o_repo_do_pai(adapter: GitAdapter, repo: Path) -> None:
    """A prova da correção: `git` responde a partir do subdiretório, nós não.

    Cenário real da máquina de desenvolvimento: existe um repositório em
    `C:/Users/User` e os projetos vivem abaixo dele. Sem esta regra, cada
    projeto exibiria a branch e os milhares de arquivos sujos do repositório
    pai — e o mesmo estado errado apareceria em todos.
    """
    sub = repo / "subprojeto"
    sub.mkdir()
    (sub / "requirements.txt").write_text("flask\n", encoding="utf-8")

    status = adapter.status(sub)

    assert status.is_repo is False
    assert status.inside_other_repo is True
    assert status.repo_root is not None
    assert status.repo_root.endswith("repo")
    assert status.current_branch is None
    assert status.dirty_count == 0


def test_repo_aninhado_e_reconhecido_como_proprio(adapter: GitAdapter, repo: Path) -> None:
    """Repositório próprio dentro de outro é dele mesmo, não do pai."""
    aninhado = repo / "independente"
    aninhado.mkdir()
    git(aninhado, "init", "-q", "-b", "dev")

    status = adapter.status(aninhado)

    assert status.is_repo is True
    assert status.inside_other_repo is False
    assert status.current_branch == "dev"
