"""Ponto de entrada do executável.

`uvicorn app.main:app` pressupõe repositório clonado, ambiente virtual e
terminal. O executável não tem nada disso: ele é uma pasta que alguém copia e
um `.exe` que alguém abre com dois cliques.

O que este módulo faz, nesta ordem, é o que os scripts de desenvolvimento
faziam à mão:

1. descobre **onde guardar** banco, log e configuração — ao lado do executável,
   não dentro dele (o conteúdo do `.exe` é somente leitura e, no modo
   empacotado, vive num diretório temporário que some ao fechar);
2. cria na primeira execução a configuração que a aplicação exige para fazer
   qualquer coisa — sem `roots.yml` a allowlist é vazia e nenhum projeto pode
   ser cadastrado, o que apareceria como um painel que não funciona;
3. aplica as migrações;
4. escolhe a porta;
5. sobe o servidor e abre o navegador.

Cada passo escreve uma linha no console. Quando algo falha na subida, a
mensagem é a única coisa entre o usuário e uma janela que fecha sozinha.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

PORTA_PADRAO = 8765


def diretorio_de_dados() -> Path:
    """Pasta ao lado do executável (ou a raiz do repositório, em desenvolvimento)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def preparar_ambiente(base: Path) -> None:
    """Aponta as `Settings` para a pasta de dados, com caminhos absolutos.

    Por variável de ambiente e não por argumento porque `Settings` é lida em
    vários pontos por `get_settings()`, que é cacheada — e porque assim quem
    quiser mudar qualquer uma delas continua podendo, pelo mesmo mecanismo de
    sempre. O `setdefault` garante isso: valor já definido pelo usuário ganha.
    """
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "configs").mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("DEVCOCKPIT_DATABASE_URL", f"sqlite:///{base / 'data' / 'devcockpit.db'}")
    os.environ.setdefault("DEVCOCKPIT_LOG_FILE", str(base / "logs" / "devcockpit.log"))
    os.environ.setdefault("DEVCOCKPIT_ROOTS_FILE", str(base / "configs" / "roots.yml"))
    os.environ.setdefault("DEVCOCKPIT_DEFAULTS_FILE", str(base / "configs" / "defaults.yml"))

    _carregar_env(base / ".env")


def _carregar_env(arquivo: Path) -> None:
    """Lê o `.env` que fica **ao lado do executável**.

    O `env_file=".env"` das `Settings` é relativo ao diretório de trabalho, que
    num aplicativo empacotado é onde quer que o atalho tenha sido clicado. O
    resultado era um `.env` escrito no lugar certo e ignorado em silêncio — e
    "a IA não liga e não diz por quê" é exatamente o modo de falha que este
    projeto não aceita.

    `setdefault` mantém a regra da casa: variável já definida no ambiente ganha
    do arquivo. Nada é validado aqui; quem valida é `Settings`.
    """
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip().strip("\"'"))


def semear_configuracao(base: Path) -> list[str]:
    """Cria `roots.yml` e `defaults.yml` na primeira execução. Devolve o que criou.

    `defaults.yml` é cópia do que veio empacotado. `roots.yml` **não** pode ser
    cópia: o arquivo do repositório aponta para o Desktop de quem desenvolveu.
    Ele é escrito a partir do perfil de quem está executando, e só com as pastas
    que existem de fato — apontar a allowlist para um diretório inexistente
    produziria erro de varredura em vez de uma lista vazia honesta.
    """
    from app.core.config import PROJECT_ROOT

    criados: list[str] = []

    defaults = base / "configs" / "defaults.yml"
    if not defaults.exists():
        origem = PROJECT_ROOT / "configs" / "defaults.yml"
        if origem.exists():
            defaults.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")
            criados.append(str(defaults))

    roots = base / "configs" / "roots.yml"
    if not roots.exists():
        perfil = Path.home()
        candidatos = [perfil / "Desktop", perfil / "Documents"]
        existentes = [c for c in candidatos if c.is_dir()]
        linhas = "\n".join(f"  - {c.as_posix()}" for c in existentes) or "  # []"

        roots.write_text(
            "# Allowlist de diretórios raiz do DevCockpit.\n"
            "#\n"
            "# Criado na primeira execução a partir do seu perfil de usuário.\n"
            "# Nenhum projeto pode ser cadastrado, varrido ou operado fora daqui,\n"
            "# e a API não altera este arquivo — só você altera (decisão D-10).\n"
            "#\n"
            "# Depois de editar, feche e abra o DevCockpit de novo.\n"
            "\n"
            f"allowed_roots:\n{linhas}\n"
            "\n"
            "scan_ignore:\n"
            "  - node_modules\n"
            "  - .venv\n"
            "  - venv\n"
            "  - env\n"
            "  - __pycache__\n"
            "  - .git\n"
            "  - dist\n"
            "  - build\n"
            "  - .next\n"
            "  - .nuxt\n"
            "  - target\n"
            "  - vendor\n"
            "  - .pytest_cache\n"
            "  - .mypy_cache\n"
            "  - .ruff_cache\n"
            "  - coverage\n"
            "  - htmlcov\n"
            "\n"
            "scan_max_depth: 3\n",
            encoding="utf-8",
        )
        criados.append(str(roots))

    return criados


def aplicar_migracoes() -> None:
    """`alembic upgrade head` em processo, sem depender do CLI nem do cwd."""
    from alembic import command
    from alembic.config import Config

    from app.core.config import PROJECT_ROOT

    config = Config()
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    # A URL é resolvida por `migrations/env.py` a partir das `Settings`, que já
    # apontam para a pasta de dados. Repetir aqui abriria espaço para as duas
    # discordarem.
    command.upgrade(config, "head")


def porta_disponivel(porta: int) -> bool:
    with socket.socket() as teste:
        teste.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            teste.bind(("127.0.0.1", porta))
        except OSError:
            return False
    return True


def escolher_porta(preferida: int) -> int | None:
    """A porta preferida, ou a primeira livre depois dela.

    Insistir na 8765 ocupada faria o executável fechar com um traceback de
    `WinError 10048` — que para quem abriu com dois cliques é indistinguível de
    "o programa não funciona".
    """
    for porta in range(preferida, preferida + 20):
        if porta_disponivel(porta):
            return porta
    return None


def abrir_navegador_quando_subir(url: str, timeout_s: float = 20.0) -> None:
    """Abre o navegador só depois que o servidor responde.

    Abrir junto com o `uvicorn` mostra uma página de erro de conexão no primeiro
    segundo, e a impressão que fica é a da primeira tela.
    """

    def esperar() -> None:
        limite = time.monotonic() + timeout_s
        while time.monotonic() < limite:
            with socket.socket() as teste:
                teste.settimeout(0.5)
                if teste.connect_ex(("127.0.0.1", int(url.rsplit(":", 1)[1]))) == 0:
                    webbrowser.open(url)
                    return
            time.sleep(0.25)

    threading.Thread(target=esperar, daemon=True).start()


def _servidor_em_thread(porta: int):  # type: ignore[no-untyped-def]
    """Sobe o uvicorn numa thread e devolve `(servidor, thread)`.

    A janela nativa precisa da thread principal — é exigência do laço de
    mensagens do Windows, não escolha da biblioteca. Então quem muda de lugar é
    o servidor.

    `install_signal_handlers` é desligado porque `signal.signal` só funciona na
    thread principal: sem isso o uvicorn levanta `ValueError` antes de aceitar a
    primeira conexão. Ninguém manda Ctrl+C numa janela mesmo; quem encerra é o
    fechamento dela.
    """
    import threading

    import uvicorn

    from app.main import create_app

    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=porta,
        log_level="info",
        # Sem console, `sys.stdout` é `None`, e a configuração de log padrão do
        # uvicorn — que monta um `StreamHandler` sobre `ext://sys.stdout` —
        # levanta antes de a primeira porta ser aberta. A thread morria em
        # silêncio e o app abria a janela contra um servidor que nunca existiu.
        #
        # O log da aplicação não se perde: `configure_logging` já escreve em
        # `logs/devcockpit.log`, ao lado do executável.
        log_config=None if sys.stdout is None else uvicorn.config.LOGGING_CONFIG,
    )
    servidor = uvicorn.Server(config)
    servidor.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    #: Exceção que matou o servidor, se matou. Sem isto, "não subiu" e "subiu e
    #: caiu" seriam a mesma tela vazia.
    falha: list[BaseException] = []

    def rodar() -> None:
        try:
            servidor.run()
        except BaseException as erro:  # noqa: BLE001 - é para ser reportado
            falha.append(erro)
            logging.getLogger(__name__).exception("servidor encerrou com erro")

    thread = threading.Thread(target=rodar, name="devcockpit-http", daemon=True)
    thread.start()
    return servidor, thread, falha


def esperar_servidor(porta: int, timeout_s: float = 30.0) -> bool:
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        with socket.socket() as teste:
            teste.settimeout(0.5)
            if teste.connect_ex(("127.0.0.1", porta)) == 0:
                return True
        time.sleep(0.2)
    return False


def abrir_janela(url: str, porta: int) -> bool:
    """Janela nativa com o painel dentro. Devolve `False` se não for possível.

    WebView2 — o motor do Edge, presente no Windows 11 — e não uma aba de
    navegador: sem barra de endereço, sem abas, com ícone próprio na barra de
    tarefas. O painel é uma ferramenta que fica aberta o dia inteiro ao lado do
    editor; uma aba se perde entre as outras vinte.

    Falhar aqui não é fatal: sem WebView2 instalado o programa cai para o
    navegador, que é o comportamento de antes.
    """
    try:
        import webview
    except ImportError:
        return False

    if not esperar_servidor(porta):
        return False

    janela = webview.create_window(
        "DevCockpit",
        url,
        width=1360,
        height=880,
        min_size=(900, 600),
        # Fundo igual ao `--bg-base` do tema escuro: sem isso o primeiro quadro
        # pisca branco antes de o CSS chegar, e o susto acontece toda abertura.
        background_color="#0E1116",
        text_select=True,
    )

    try:
        webview.start(private_mode=False, storage_path=None)
    except Exception:  # noqa: BLE001 - qualquer falha do backend cai no navegador
        return False
    finally:
        del janela
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="DevCockpit",
        description="Central local de gerenciamento dos projetos de desenvolvimento.",
    )
    parser.add_argument("--port", type=int, default=PORTA_PADRAO)
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="não abrir a janela nativa; usa o navegador",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="não abrir nada; só sobe o servidor",
    )
    args = parser.parse_args(argv)

    _console_em_utf8()

    base = diretorio_de_dados()
    _dizer(f"DevCockpit — dados em {base}")

    preparar_ambiente(base)
    for criado in semear_configuracao(base):
        _dizer(f"  criado: {criado}")

    porta = escolher_porta(args.port)
    if porta is None:
        return _falhar(f"Nenhuma porta livre entre {args.port} e {args.port + 19}.")
    if porta != args.port:
        _dizer(f"  porta {args.port} ocupada; usando {porta}")

    # Antes de qualquer coisa que leia `Settings` — e antes de o cache de
    # `get_settings()` fechar. A porta não é só onde o servidor escuta: ela
    # entra na lista de origens aceitas em requisição que altera estado (defesa
    # D5). Subir em 8766 com as `Settings` dizendo 8765 devolvia 403 em todo
    # botão do painel, com a tela carregando normalmente.
    os.environ["DEVCOCKPIT_PORT"] = str(porta)

    try:
        _dizer("  aplicando migrações…")
        aplicar_migracoes()
    except Exception as erro:  # noqa: BLE001 - a mensagem é o produto aqui
        return _falhar(f"Erro ao preparar o banco:\n\n{erro}")

    url = f"http://127.0.0.1:{porta}"
    _dizer(f"  no ar em {url}")

    if args.no_browser or args.no_window:
        # Modo servidor: sem janela. Continua sendo o caminho de quem roda em
        # terminal, e o que os testes exercitam.
        import uvicorn

        from app.main import create_app

        if not args.no_browser:
            abrir_navegador_quando_subir(url)
        try:
            uvicorn.run(create_app(), host="127.0.0.1", port=porta, log_level="info")
        except KeyboardInterrupt:
            _dizer("Encerrado.")
        except Exception as erro:  # noqa: BLE001
            return _falhar(f"Erro ao subir o servidor:\n\n{erro}")
        return 0

    servidor, thread, falha = _servidor_em_thread(porta)

    if not esperar_servidor(porta):
        motivo = f"{falha[0]}" if falha else "o servidor não respondeu a tempo."
        return _falhar(f"O DevCockpit não conseguiu subir:\n\n{motivo}")

    if not abrir_janela(url, porta):
        # Sem janela nativa, o navegador é a rede de segurança — mas o processo
        # precisa continuar de pé segurando o servidor, senão fechar não seria
        # degradar: seria não funcionar.
        _dizer("  janela nativa indisponível; abrindo no navegador")
        webbrowser.open(url)
        try:
            while thread.is_alive():
                thread.join(timeout=1.0)
        except KeyboardInterrupt:
            pass

    # Fechar a janela encerra o servidor: uma ferramenta de bandeja que continua
    # rodando invisível depois de fechada é a receita da segunda instância
    # brigando pela porta.
    servidor.should_exit = True
    thread.join(timeout=10.0)
    return 0


def _console_em_utf8() -> None:
    """Acento no console do Windows.

    O console herda a codepage do sistema (850 ou 1252 por aqui), e as
    mensagens saem como "migrações" com caracteres trocados. Trocar a
    codepage do próprio console e reconfigurar os fluxos resolve; falhar nisso
    não é motivo para não subir.
    """
    try:
        if os.name == "nt":
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 - cosmético
        pass


def _dizer(mensagem: str) -> None:
    """Escreve no console quando existe um.

    Empacotado como aplicativo de janela, o processo não tem console: no
    Windows, `sys.stdout` vira `None` e um `print` solto derruba a subida com
    `AttributeError` — falha por causa da mensagem, não do trabalho.
    """
    if sys.stdout is None:
        return
    # Registrar nunca pode ser o que quebra a subida.
    with contextlib.suppress(Exception):
        print(mensagem)


def _falhar(mensagem: str) -> int:
    """Único lugar por onde uma falha de subida chega ao usuário.

    Sem console não há para onde escrever, e o executável fecharia em silêncio
    — indistinguível de "cliquei e não aconteceu nada". A caixa de diálogo do
    próprio Windows não depende de nada estar de pé.
    """
    _dizer(f"ERRO: {mensagem}")

    if getattr(sys, "frozen", False):
        if sys.stdout is None and os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                None, f"{mensagem}\n\nDetalhes em logs/devcockpit.log", "DevCockpit", 0x10
            )
        elif sys.stdin is not None and sys.stdin.isatty():
            input("\nPressione Enter para fechar…")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
