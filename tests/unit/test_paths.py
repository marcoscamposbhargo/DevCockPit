"""Testes de `core/paths.py` — meta de cobertura 100% (é defesa de segurança)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.errors import PathNotAllowed, PathNotFound
from app.core.paths import (
    is_within,
    resolve_real,
    resolve_within_project,
    validate_project_dir,
)

pytestmark = pytest.mark.unit


def test_aceita_diretorio_dentro_do_root(workspace: Path) -> None:
    project = workspace / "meu-projeto"
    project.mkdir()

    result = validate_project_dir(project, [workspace])

    assert result == project.resolve()


def test_rejeita_path_relativo(workspace: Path) -> None:
    with pytest.raises(PathNotAllowed):
        validate_project_dir("projetos/algum", [workspace])


def test_rejeita_diretorio_inexistente(workspace: Path) -> None:
    with pytest.raises(PathNotFound):
        validate_project_dir(workspace / "nao-existe", [workspace])


def test_rejeita_arquivo(workspace: Path) -> None:
    arquivo = workspace / "readme.md"
    arquivo.write_text("x", encoding="utf-8")

    with pytest.raises(PathNotFound):
        validate_project_dir(arquivo, [workspace])


def test_rejeita_fora_do_root(tmp_path: Path, workspace: Path) -> None:
    fora = tmp_path / "outro-lugar"
    fora.mkdir()

    with pytest.raises(PathNotAllowed):
        validate_project_dir(fora, [workspace])


def test_rejeita_escape_com_dois_pontos(workspace: Path, tmp_path: Path) -> None:
    alvo = tmp_path / "secreto"
    alvo.mkdir()
    caminho = workspace / ".." / "secreto"

    with pytest.raises(PathNotAllowed):
        validate_project_dir(caminho, [workspace])


def test_rejeita_quando_nao_ha_root_configurado(workspace: Path) -> None:
    with pytest.raises(PathNotAllowed):
        validate_project_dir(workspace, [])


@pytest.mark.skipif(os.name == "nt", reason="symlink no Windows exige privilégio")
def test_rejeita_symlink_que_escapa_do_root(workspace: Path, tmp_path: Path) -> None:
    alvo = tmp_path / "fora"
    alvo.mkdir()
    link = workspace / "atalho"
    link.symlink_to(alvo, target_is_directory=True)

    with pytest.raises(PathNotAllowed):
        validate_project_dir(link, [workspace])


def test_root_com_prefixo_parecido_nao_da_falso_positivo(tmp_path: Path) -> None:
    """`Desktop` não pode abranger `Desktop-antigo` (bug clássico de startswith)."""
    root = tmp_path / "Desktop"
    root.mkdir()
    vizinho = tmp_path / "Desktop-antigo"
    vizinho.mkdir()

    assert is_within(vizinho, root) is False
    with pytest.raises(PathNotAllowed):
        validate_project_dir(vizinho, [root])


@pytest.mark.skipif(os.name != "nt", reason="comparação sem caixa é específica do Windows")
def test_windows_ignora_caixa(workspace: Path) -> None:
    project = workspace / "MeuProjeto"
    project.mkdir()

    result = validate_project_dir(str(project).upper(), [workspace])

    assert result.name.lower() == "meuprojeto"


def test_is_within_recusa_candidato_mais_curto_que_o_root(tmp_path: Path) -> None:
    root = tmp_path / "a" / "b" / "c"
    root.mkdir(parents=True)

    assert is_within(tmp_path / "a", root) is False


def test_resolve_real_canonicaliza_dois_pontos(tmp_path: Path) -> None:
    alvo = tmp_path / "alvo"
    alvo.mkdir()

    assert resolve_real(tmp_path / "alvo" / ".." / "alvo") == alvo.resolve()


def test_resolve_within_project_aceita_relativo(sample_project: Path) -> None:
    (sample_project / "docker-compose.yml").write_text("services: {}", encoding="utf-8")

    result = resolve_within_project(sample_project, "docker-compose.yml")

    assert result == (sample_project / "docker-compose.yml").resolve()


def test_resolve_within_project_rejeita_absoluto(sample_project: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_within_project(sample_project, sample_project / "docker-compose.yml")


def test_resolve_within_project_rejeita_escape(sample_project: Path) -> None:
    with pytest.raises(PathNotAllowed):
        resolve_within_project(sample_project, "../../etc/passwd")
