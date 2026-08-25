"""Empacotamento: o que o executável faz antes de o servidor existir.

Nada aqui sobe servidor. O que se protege é a preparação — pasta de dados,
configuração semeada, porta escolhida — porque é onde uma falha vira uma janela
que fecha sozinha, sem log e sem ninguém para ler o traceback.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml

from app import launcher

pytestmark = pytest.mark.unit


@pytest.fixture
def ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    for chave in (
        "DEVCOCKPIT_DATABASE_URL",
        "DEVCOCKPIT_LOG_FILE",
        "DEVCOCKPIT_ROOTS_FILE",
        "DEVCOCKPIT_DEFAULTS_FILE",
        "DEVCOCKPIT_PORT",
    ):
        monkeypatch.delenv(chave, raising=False)


def test_prepara_pastas_e_aponta_settings(tmp_path: Path, ambiente_limpo: None) -> None:
    launcher.preparar_ambiente(tmp_path)

    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "configs").is_dir()

    import os

    assert os.environ["DEVCOCKPIT_DATABASE_URL"].endswith("devcockpit.db")
    assert Path(os.environ["DEVCOCKPIT_ROOTS_FILE"]).parent == tmp_path / "configs"


def test_valor_definido_pelo_usuario_ganha(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quem já configurou por variável de ambiente não é sobrescrito."""
    monkeypatch.setenv("DEVCOCKPIT_DATABASE_URL", "sqlite:///C:/outro/lugar.db")

    launcher.preparar_ambiente(tmp_path)

    import os

    assert os.environ["DEVCOCKPIT_DATABASE_URL"] == "sqlite:///C:/outro/lugar.db"


def test_semeia_roots_a_partir_do_perfil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    perfil = tmp_path / "perfil"
    (perfil / "Desktop").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: perfil))

    base = tmp_path / "app"
    (base / "configs").mkdir(parents=True)

    criados = launcher.semear_configuracao(base)

    assert any("roots.yml" in c for c in criados)
    dados = yaml.safe_load((base / "configs" / "roots.yml").read_text(encoding="utf-8"))
    assert dados["allowed_roots"] == [(perfil / "Desktop").as_posix()]
    assert "Documents" not in str(dados["allowed_roots"]), "pasta inexistente não entra"
    assert dados["scan_max_depth"] == 3


def test_nao_sobrescreve_configuracao_existente(tmp_path: Path) -> None:
    base = tmp_path / "app"
    (base / "configs").mkdir(parents=True)
    roots = base / "configs" / "roots.yml"
    roots.write_text("allowed_roots:\n  - C:/meu/lugar\n", encoding="utf-8")

    criados = launcher.semear_configuracao(base)

    assert not any("roots.yml" in c for c in criados)
    assert "C:/meu/lugar" in roots.read_text(encoding="utf-8")


def test_porta_ocupada_cede_lugar_a_seguinte() -> None:
    with socket.socket() as ocupada:
        ocupada.bind(("127.0.0.1", 0))
        ocupada.listen(1)
        porta = ocupada.getsockname()[1]

        escolhida = launcher.escolher_porta(porta)

    assert escolhida is not None
    assert escolhida > porta, "insistir na ocupada fecharia o executável com WinError 10048"


def test_sem_porta_livre_devolve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "porta_disponivel", lambda _porta: False)

    assert launcher.escolher_porta(8765) is None


def test_porta_escolhida_vira_configuracao(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A porta real precisa chegar às `Settings`, não só ao uvicorn.

    Ela entra na lista de origens aceitas em requisição que altera estado
    (defesa D5). Subir em 8766 com as `Settings` dizendo 8765 devolvia 403 em
    todo botão do painel — com a tela carregando normalmente, que é o pior
    jeito de quebrar.
    """
    import os

    monkeypatch.setattr(launcher, "diretorio_de_dados", lambda: tmp_path)
    monkeypatch.setattr(launcher, "escolher_porta", lambda _preferida: 8899)
    monkeypatch.setattr(launcher, "aplicar_migracoes", lambda: None)

    registrado: dict[str, object] = {}

    def uvicorn_falso(app, host, port, log_level):  # type: ignore[no-untyped-def]
        registrado["port"] = port
        registrado["env"] = os.environ.get("DEVCOCKPIT_PORT")

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", uvicorn_falso)

    assert launcher.main(["--no-browser"]) == 0
    assert registrado["port"] == 8899
    assert registrado["env"] == "8899"


def test_sem_porta_livre_nao_sobe_servidor(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "diretorio_de_dados", lambda: tmp_path)
    monkeypatch.setattr(launcher, "escolher_porta", lambda _preferida: None)

    def nao_deveria() -> None:
        raise AssertionError("migração não pode rodar sem porta")

    monkeypatch.setattr(launcher, "aplicar_migracoes", nao_deveria)

    assert launcher.main(["--no-browser"]) == 1
