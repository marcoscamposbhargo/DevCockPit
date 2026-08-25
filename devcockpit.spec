# Empacotamento do DevCockpit com PyInstaller.
#
# Modo pasta (`onedir`) e não arquivo único: o `onefile` descompacta o pacote
# inteiro num diretório temporário a cada abertura — com FastAPI, SQLAlchemy e
# psutil dentro, isso custa segundos toda vez e é o padrão que mais dispara
# falso positivo de antivírus. A pasta abre em cerca de um segundo.
#
# Dados (banco, log, configuração) NÃO entram aqui: eles ficam ao lado do
# executável, criados na primeira execução por `app/launcher.py`. O conteúdo
# empacotado é somente leitura.
#
# Build:  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("frontend", "frontend"),
    # As migrações são carregadas pelo Alembic por caminho de arquivo, não por
    # import: precisam existir como arquivo dentro do pacote.
    ("migrations", "migrations"),
    # Só o que a aplicação lê. `configs/roots.yml` do repositório aponta para o
    # Desktop de quem desenvolveu — o do usuário é escrito na primeira execução.
    ("configs/defaults.yml", "configs"),
    ("configs/roots.example.yml", "configs"),
]

hiddenimports = [
    # A janela nativa: pywebview escolhe o backend em tempo de execucao, e o
    # do Windows entra por pythonnet/clr — nada disso aparece para o analisador
    # estatico.
    *collect_submodules("webview"),
    "clr_loader",
    "pythonnet",
    # O uvicorn escolhe loop, protocolo e ciclo de vida em tempo de execução,
    # por string. Sem import estático, o analisador não vê nenhum deles.
    *collect_submodules("uvicorn"),
    "anyio._backends._asyncio",
    # Import indireto: o Alembic carrega `migrations/env.py` como script, e é
    # ele quem alcança o resto da aplicação.
    "app.main",
    "app.launcher",
]

analysis = Analysis(
    ["app/launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Peso morto conhecido: nada no DevCockpit desenha gráfico em Tk nem abre
    # janela nativa, e a suíte de testes não viaja no executável.
    excludes=["tkinter", "pytest", "_pytest", "IPython", "matplotlib", "numpy"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DevCockpit",
    icon="frontend/assets/devcockpit.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Sem console: o DevCockpit abre como aplicativo, numa janela própria. O
    # preço é que uma falha de subida nao tem para onde escrever — por isso
    # `_falhar()` no launcher usa caixa de dialogo do Windows, e o log continua
    # em `logs/devcockpit.log` ao lado do executavel.
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="DevCockpit",
)
