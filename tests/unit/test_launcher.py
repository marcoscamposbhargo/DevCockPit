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


def test_env_ao_lado_do_executavel_e_lido(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O `.env` mora na pasta de dados, não no diretório de trabalho.

    `env_file=".env"` das `Settings` é relativo ao cwd, que num aplicativo
    empacotado é onde quer que o atalho tenha sido clicado. O usuário escrevia
    o arquivo no lugar certo e ele era ignorado em silêncio — "a IA não liga e
    não diz por quê" é o modo de falha que este projeto não aceita.
    """
    import os

    monkeypatch.delenv("DEVCOCKPIT_AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEVCOCKPIT_AI_MODEL", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "# comentário e linha vazia são ignorados",
                "",
                "DEVCOCKPIT_AI_PROVIDER=local",
                'DEVCOCKPIT_AI_MODEL="llama3.2:3b"',
                "linha sem igual",
            ]
        ),
        encoding="utf-8",
    )

    launcher.preparar_ambiente(tmp_path)

    assert os.environ["DEVCOCKPIT_AI_PROVIDER"] == "local"
    # As aspas são do formato do arquivo, não do valor.
    assert os.environ["DEVCOCKPIT_AI_MODEL"] == "llama3.2:3b"


def test_env_nao_sobrescreve_variavel_ja_definida(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mesma regra do resto do launcher: o ambiente ganha do arquivo."""
    import os

    monkeypatch.setenv("DEVCOCKPIT_AI_PROVIDER", "anthropic")
    (tmp_path / ".env").write_text("DEVCOCKPIT_AI_PROVIDER=local", encoding="utf-8")

    launcher.preparar_ambiente(tmp_path)

    assert os.environ["DEVCOCKPIT_AI_PROVIDER"] == "anthropic"


def test_sem_env_nao_e_erro(tmp_path: Path, ambiente_limpo: None) -> None:
    """Instalação nova não tem `.env`, e isso é o caso normal."""
    launcher.preparar_ambiente(tmp_path)  # não levanta


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
    # Sem isto o teste dependeria de a 8765 estar livre nesta máquina.
    monkeypatch.setattr(launcher, "painel_ja_no_ar", lambda _porta: False)
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
    monkeypatch.setattr(launcher, "painel_ja_no_ar", lambda _porta: False)

    def nao_deveria() -> None:
        raise AssertionError("migração não pode rodar sem porta")

    monkeypatch.setattr(launcher, "aplicar_migracoes", nao_deveria)

    assert launcher.main(["--no-browser"]) == 1


def test_painel_ja_aberto_nao_sobe_um_segundo(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duas instâncias contra o mesmo SQLite disputam a escrita.

    O launcher tratava porta ocupada sempre da mesma forma: pegar a próxima
    livre. Quando quem ocupa é o próprio painel, isso produz dois pollers
    escrevendo o mesmo banco — e "database is locked" aparecendo num botão sem
    relação nenhuma com o que a pessoa estava fazendo. As duas instâncias ainda
    podem servir versões diferentes do código.
    """
    monkeypatch.setattr(launcher, "diretorio_de_dados", lambda: tmp_path)
    monkeypatch.setattr(launcher, "porta_disponivel", lambda _porta: False)
    monkeypatch.setattr(launcher, "painel_ja_no_ar", lambda _porta: True)

    def nao_deveria(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("não pode subir um segundo servidor")

    monkeypatch.setattr(launcher, "aplicar_migracoes", nao_deveria)
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", nao_deveria)

    abertos: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", abertos.append)

    assert launcher.main([]) == 0
    assert abertos == ["http://127.0.0.1:8765"], "a janela existente é trazida à frente"


def test_porta_ocupada_por_estranho_faz_o_painel_mudar_de_porta(
    tmp_path: Path, ambiente_limpo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um `200` não basta: qualquer servidor pode responder nessa porta.

    Tratar um estranho como "o painel" mandaria a pessoa para a tela de outro
    programa e deixaria o DevCockpit sem subir.
    """
    monkeypatch.setattr(launcher, "diretorio_de_dados", lambda: tmp_path)
    monkeypatch.setattr(launcher, "porta_disponivel", lambda porta: porta != 8765)
    monkeypatch.setattr(launcher, "painel_ja_no_ar", lambda _porta: False)
    monkeypatch.setattr(launcher, "aplicar_migracoes", lambda: None)

    registrado: dict[str, object] = {}

    def uvicorn_falso(app, host, port, log_level):  # type: ignore[no-untyped-def]
        registrado["port"] = port

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", uvicorn_falso)

    assert launcher.main(["--no-browser"]) == 0
    assert registrado["port"] == 8766
