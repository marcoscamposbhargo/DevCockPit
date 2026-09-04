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
    os.environ.setdefault("DEVCOCKPIT_AI_CONFIG_FILE", str(base / "configs" / "ai.yml"))

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


#: Quantas portas o painel considera a partir da preferida. Uma constante, e
#: não dois números iguais em lugares diferentes: a busca por um painel já
#: aberto precisa cobrir exatamente onde a escolha pode tê-lo colocado.
FAIXA_DE_PORTAS = 20


def escolher_porta(preferida: int) -> int | None:
    """A porta preferida, ou a primeira livre depois dela.

    Insistir na 8765 ocupada faria o executável fechar com um traceback de
    `WinError 10048` — que para quem abriu com dois cliques é indistinguível de
    "o programa não funciona".
    """
    for porta in range(preferida, preferida + FAIXA_DE_PORTAS):
        if porta_disponivel(porta):
            return porta
    return None


def painel_ja_no_ar(porta: int, timeout_s: float = 0.5) -> bool:
    """Já existe um DevCockpit atendendo nesta porta?

    A pergunta importa porque a resposta muda o que fazer. Porta ocupada por
    outro programa é motivo para escolher a próxima livre; porta ocupada pelo
    **próprio painel** é motivo para abrir aquele, e não subir um rival.

    Duas instâncias contra o mesmo SQLite disputam a escrita — e o SQLite
    admite um escritor por vez. Foi assim que apareceu "database is locked"
    num botão que não tinha nada a ver com o que estava sendo feito. Elas
    também podem rodar versões diferentes: depois de reconstruir o executável,
    a janela aberta continua servindo o código velho.

    A verificação é a assinatura do próprio `/api/health`, não só um `200`:
    qualquer servidor pode responder 200 nessa porta, e tratar um estranho como
    "o painel" mandaria a pessoa para a tela errada.
    """
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/api/health", timeout=timeout_s
        ) as resposta:
            dados = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, ValueError):
        return False

    return isinstance(dados, dict) and "tools" in dados and "allowed_roots" in dados


#: Onde a instância viva anuncia em que porta está. Fica no diretório de dados,
#: que é compartilhado por qualquer instância — é o que torna a checagem
#: independente de porta.
ARQUIVO_DE_EXECUCAO = "runtime.json"


def registrar_execucao(base: Path, porta: int) -> None:
    """Anota porta e PID desta instância, para a próxima abertura encontrá-la.

    Sem isto, achar o painel já aberto dependia de adivinhar a porta. Varrer
    uma faixa a partir da preferida cobre o caso comum e falha no caso real:
    quem abre com `--port 8790` fica fora de qualquer faixa razoável, e a
    abertura seguinte sobe uma segunda instância contra o mesmo banco.

    Falha ao escrever não impede o painel de subir. Perder a anotação degrada a
    checagem para a varredura; não conseguir abrir o painel por causa dela
    seria trocar um defeito por outro pior.
    """
    import json

    with contextlib.suppress(OSError):
        (base / ARQUIVO_DE_EXECUCAO).write_text(
            json.dumps({"pid": os.getpid(), "porta": porta}),
            encoding="utf-8",
        )


def porta_registrada(base: Path) -> int | None:
    """A porta anotada pela instância anterior, se o arquivo existir e servir."""
    import json

    try:
        dados = json.loads((base / ARQUIVO_DE_EXECUCAO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    porta = dados.get("porta") if isinstance(dados, dict) else None
    return porta if isinstance(porta, int) and 1 <= porta <= 65535 else None


def trazer_janela_para_frente(pid: int) -> bool:
    """Traz a janela daquele processo ao topo. `False` se ele não tem janela.

    Sem isto, clicar no atalho com o painel aberto abria uma **aba do
    navegador** — duas telas do mesmo painel, e a janela nativa continuava
    escondida atrás de tudo. O navegador vira alternativa, não resposta padrão.

    Só Windows, que é onde o executável roda. Em qualquer outro lugar devolve
    `False` e o navegador assume.
    """
    if sys.platform != "win32":
        return False

    try:
        user32 = ctypes.windll.user32
    except AttributeError:  # pragma: no cover - só ocorre fora do Windows
        return False

    encontrada: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _visitar(hwnd, _lparam):  # type: ignore[no-untyped-def]
        dono = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dono))
        if dono.value == pid and user32.IsWindowVisible(hwnd):
            encontrada.append(hwnd)
            return False
        return True

    with contextlib.suppress(OSError, ValueError):
        user32.EnumWindows(_visitar, 0)

    if not encontrada:
        return False

    janela = encontrada[0]
    SW_RESTORE = 9
    with contextlib.suppress(OSError, ValueError):
        user32.ShowWindow(janela, SW_RESTORE)
        user32.SetForegroundWindow(janela)
        return True
    return False


def pid_registrado(base: Path) -> int | None:
    """O PID anotado pela instância viva, para achar a janela dela."""
    import json

    try:
        dados = json.loads((base / ARQUIVO_DE_EXECUCAO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    pid = dados.get("pid") if isinstance(dados, dict) else None
    return pid if isinstance(pid, int) and pid > 0 else None


def encontrar_painel_no_ar(preferida: int, base: Path | None = None) -> int | None:
    """Em qual porta já existe um DevCockpit, se houver algum.

    Duas fontes, nesta ordem: a porta que a instância viva **anotou**, e depois
    a varredura da faixa. A anotação cobre quem subiu em porta arbitrária; a
    varredura cobre instância de versão antiga, que não anotava nada.

    A anotação sozinha não basta como prova: o arquivo sobrevive a um
    encerramento abrupto. Quem decide é sempre a resposta do `/api/health`.

    Só porta ocupada é sondada; porta livre não tem ninguém para responder. Na
    prática isso é uma ou duas sondagens, não vinte.
    """
    anotada = porta_registrada(base) if base is not None else None
    if anotada is not None and not porta_disponivel(anotada) and painel_ja_no_ar(anotada):
        return anotada

    for porta in range(preferida, preferida + FAIXA_DE_PORTAS):
        if porta == anotada or porta_disponivel(porta):
            continue
        if painel_ja_no_ar(porta):
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

    # Painel já aberto, em qualquer porta da faixa: traz aquele para a frente
    # em vez de subir um segundo contra o mesmo banco.
    aberto = encontrar_painel_no_ar(args.port, base)
    if aberto is not None:
        url = f"http://127.0.0.1:{aberto}"
        pid = pid_registrado(base)
        # A janela primeiro. Abrir o navegador com a janela nativa aberta dá
        # duas telas do mesmo painel, e deixa escondida justamente a que a
        # pessoa clicou para ver.
        if pid is not None and trazer_janela_para_frente(pid):
            _dizer("  o DevCockpit já está aberto; janela trazida para a frente")
            return 0
        # Sem janela — quem subiu em modo servidor, por exemplo: o navegador é
        # a única porta de entrada, e ficar sem nada seria pior.
        _dizer(f"  o DevCockpit já está aberto em {url}")
        webbrowser.open(url)
        return 0

    porta = escolher_porta(args.port)
    if porta is None:
        return _falhar(f"Nenhuma porta livre entre {args.port} e {args.port + 19}.")
    if porta != args.port:
        _dizer(f"  porta {args.port} ocupada por outro programa; usando {porta}")

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

    registrar_execucao(base, porta)

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
