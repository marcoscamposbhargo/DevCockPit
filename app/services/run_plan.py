"""De onde sai o comando que sobe o servidor de um projeto.

Esta é a peça que muda o ADR-003, então vale ser explícito sobre o que muda e
o que não muda.

**Não muda:** nenhum valor vindo do cliente HTTP entra em argv. O cliente manda
o id do projeto e nada mais. Não existe campo de comando na requisição, não
existe shell, e `argv` continua sendo lista — nunca uma string que alguém
precise partir.

**Muda:** o argv deixa de ser exclusivamente literal no código-fonte. Ele passa
a poder vir de dois lugares novos, ambos **arquivos dentro de um root
permitido**:

1. o bloco `run:` do `devcockpit.yml` do projeto;
2. o `package.json` / `pyproject.toml` do projeto, via detecção.

Por que isso é aceitável: quem consegue escrever esses arquivos já consegue
executar o que quiser na máquina por caminhos muito mais curtos — `scripts` do
`package.json` roda em `npm install`, hook do Git roda em `git commit`. A
superfície que o modelo de segurança fecha é a *remota* (defesas D1, D5, D10):
uma página aberta no navegador não pode operar a ferramenta. Isso continua
inteiro.

Por que ainda assim há guarda: um comando lido de arquivo pode estar errado sem
ser malicioso. `plan_from_*` recusa string no lugar de lista, caminho que escapa
do projeto, e os mesmos fragmentos destrutivos que `app/runner/allowlist.py`
recusa no registro fixo.
"""

from __future__ import annotations

import json
import logging
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.errors import ValidationError
from app.core.paths import resolve_within_project
from app.runner.allowlist import FORBIDDEN_FLAGS, FORBIDDEN_FRAGMENTS

logger = logging.getLogger(__name__)

MANIFEST_NAME = "devcockpit.yml"

#: Nomes de script que significam "sobe o servidor de desenvolvimento", em
#: ordem de preferência. `dev` primeiro porque é a convenção atual do Vite, do
#: Next e do Nuxt; `start` depois porque em muitos projetos ele roda a build de
#: produção, que não é o que se quer daqui.
NODE_SCRIPT_PREFERENCE = ("dev", "develop", "start:dev", "serve", "start")

#: Gerenciador de pacote por arquivo de lock. Rodar `npm` num projeto com
#: `pnpm-lock.yaml` reinstala a árvore inteira do jeito errado.
LOCKFILE_TO_MANAGER = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
    ("package-lock.json", "npm"),
)

MAX_ARGS = 40
MAX_ARG_LENGTH = 500


@dataclass(frozen=True)
class RunPlan:
    """Como subir o servidor de um projeto."""

    argv: list[str]
    #: Relativo ao projeto. Vazio significa a raiz.
    cwd: str = ""
    #: De onde o plano veio: "manifest", "node", "python". A UI mostra isso
    #: para a pessoa saber o que vai rodar antes de clicar.
    source: str = "manifest"
    #: Texto curto do que foi encontrado, para a UI explicar a origem.
    evidence: str = ""
    #: Qual serviço declarado **este comando fornece**. É o que separa a
    #: aplicação da infraestrutura: tudo o que o projeto declara e não é este
    #: serviço é dependência, e é por essas portas que a subida espera antes de
    #: rodar o app. Sem isso, a espera incluiria a porta do próprio app — que
    #: por definição ainda não subiu — e estouraria o teto em toda subida.
    service: str | None = None

    @property
    def display(self) -> str:
        return " ".join(self.argv)

    @property
    def port(self) -> int | None:
        """A porta que **este comando** vai abrir, quando dá para ler do argv.

        Existe para uma coisa só: comparar com a porta que o projeto declara.
        Um manifesto com ``--port 8000`` e um serviço cadastrado em 3001 sobem
        o servidor num lugar e verificam outro — o painel fica dizendo "fora do
        ar" para algo que está no ar, e ninguém descobre por quê.

        Lê as três formas que aparecem na prática: ``--port 8000``,
        ``--port=8000`` e ``127.0.0.1:8000`` (o ``runserver`` do Django).
        Não achar porta nenhuma é resposta legítima — ``npm run dev`` decide a
        porta dentro do script, e chutar ali seria pior que calar.
        """
        return _port_from_argv(self.argv)


def _validate_argv(argv: object, *, origem: str) -> list[str]:
    """Recusa o que não pode virar comando, com a mensagem dizendo o porquê."""
    if isinstance(argv, str):
        raise ValidationError(
            f"{origem}: o comando precisa ser uma lista de argumentos, não uma "
            'linha de texto. Use ["npm", "run", "dev"] em vez de "npm run dev" — '
            "sem shell, quem parte a string seríamos nós, e partir string de "
            "comando é de onde vem metade dos furos de injeção."
        )
    if not isinstance(argv, (list, tuple)) or not argv:
        raise ValidationError(f"{origem}: o comando precisa ser uma lista não vazia.")
    if len(argv) > MAX_ARGS:
        raise ValidationError(f"{origem}: comando com argumentos demais (limite {MAX_ARGS}).")

    partes: list[str] = []
    for item in argv:
        if not isinstance(item, (str, int, float)):
            raise ValidationError(f"{origem}: argumento de tipo não suportado: {item!r}.")
        texto = str(item)
        if not texto:
            raise ValidationError(f"{origem}: argumento vazio no comando.")
        if len(texto) > MAX_ARG_LENGTH:
            raise ValidationError(f"{origem}: argumento longo demais.")
        if "\x00" in texto:
            raise ValidationError(f"{origem}: argumento com byte nulo.")
        partes.append(texto)

    _assert_not_destructive(partes, origem=origem)
    return partes


def _assert_not_destructive(argv: list[str], *, origem: str) -> None:
    """A mesma guarda que o registro fixo tem, aplicada ao comando de arquivo.

    Não é defesa contra alguém mal-intencionado — quem escreve o manifesto já
    pode mais que isso. É defesa contra o `run:` copiado de outro projeto que
    trazia um `down -v` junto e apagaria o volume do banco no primeiro clique.
    """
    baixo = [parte.lower() for parte in argv]

    for fragmento in FORBIDDEN_FRAGMENTS:
        if all(parte in baixo for parte in fragmento):
            raise ValidationError(
                f"{origem}: o comando {' '.join(fragmento)!r} é destrutivo e não "
                "pode ser executado pelo painel. Rode no terminal se for mesmo isso."
            )

    for flag in FORBIDDEN_FLAGS:
        if flag in baixo:
            raise ValidationError(
                f"{origem}: a flag {flag!r} é destrutiva e não pode ser executada pelo painel."
            )


# --- origem 1: o manifesto do projeto ------------------------------------


def plan_from_manifest(project_dir: Path) -> RunPlan | None:
    """Lê o bloco `run:` do `devcockpit.yml`, se houver.

    Formato:

        run:
          cmd: ["npm", "run", "dev"]
          cwd: "frontend"        # opcional, relativo ao projeto
          service: "backend"     # opcional, qual serviço declarado este
                                 # comando fornece; o resto vira dependência
                                 # a esperar antes de subir o app
    """
    manifesto = project_dir / MANIFEST_NAME
    if not manifesto.is_file():
        return None

    try:
        dados = yaml.safe_load(manifesto.read_text(encoding="utf-8", errors="replace")) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning(
            "devcockpit.yml não pôde ser lido para o comando de execução",
            extra={"extra_fields": {"error": str(exc)}},
        )
        return None

    bloco = dados.get("run")
    if not isinstance(bloco, dict):
        return None

    argv = _validate_argv(bloco.get("cmd"), origem="devcockpit.yml (run.cmd)")

    cwd = str(bloco.get("cwd") or "").strip()
    if cwd:
        # Recusa aqui, não lá na frente onde já seria diretório de execução.
        resolve_within_project(project_dir, cwd)

    service = str(bloco.get("service") or "").strip() or None

    return RunPlan(
        argv=argv,
        cwd=cwd,
        source="manifest",
        evidence="devcockpit.yml",
        service=service,
    )


#: Bandeiras que carregam número de porta no argumento seguinte ou depois do
#: ``=``. `-p` fica de fora de propósito: em muitos comandos ele é outra coisa
#: (``docker -p``, ``mkdir -p``), e errar a leitura aqui gera aviso falso.
PORT_FLAGS = ("--port", "--server-port")

_HOST_PORT = re.compile(r"^(?:\[[0-9a-fA-F:]+\]|[\w.-]+)?:(\d{2,5})$")


def _port_from_argv(argv: list[str]) -> int | None:
    for indice, argumento in enumerate(argv):
        for flag in PORT_FLAGS:
            if argumento == flag and indice + 1 < len(argv):
                if argv[indice + 1].isdigit():
                    return int(argv[indice + 1])
            elif argumento.startswith(f"{flag}="):
                cauda = argumento.split("=", 1)[1]
                if cauda.isdigit():
                    return int(cauda)

        casado = _HOST_PORT.match(argumento)
        if casado:
            return int(casado.group(1))

    return None


# --- origem 2: o que o projeto já declara --------------------------------


def _package_manager(project_dir: Path) -> str:
    for lockfile, manager in LOCKFILE_TO_MANAGER:
        if (project_dir / lockfile).is_file():
            return manager
    return "npm"


def plan_from_node(project_dir: Path) -> RunPlan | None:
    """Deriva o comando do `package.json`, sem inventar script que não existe."""
    package = project_dir / "package.json"
    if not package.is_file():
        return None

    try:
        dados = json.loads(package.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None

    scripts = dados.get("scripts")
    if not isinstance(scripts, dict):
        return None

    escolhido = next((nome for nome in NODE_SCRIPT_PREFERENCE if nome in scripts), None)
    if escolhido is None:
        return None

    manager = _package_manager(project_dir)
    # `yarn dev` e `bun run dev`; `npm`/`pnpm` querem o `run` no meio.
    argv = [manager, escolhido] if manager == "yarn" else [manager, "run", escolhido]

    return RunPlan(
        argv=_validate_argv(argv, origem="package.json"),
        source="node",
        evidence=f"package.json · scripts.{escolhido} ({manager})",
    )


#: Onde procurar o interpretador do próprio projeto, em ordem. Rodar um projeto
#: Python com o `python` do PATH é quase sempre errado: as dependências dele
#: estão no ambiente virtual dele, e o de fora não as tem. O sintoma é um
#: `ModuleNotFoundError` de uma biblioteca que está instalada — só que em outro
#: lugar.
VENV_INTERPRETERS = (
    ".venv/Scripts/python.exe",
    ".venv/bin/python",
    "venv/Scripts/python.exe",
    "venv/bin/python",
    ".virtualenv/Scripts/python.exe",
    ".virtualenv/bin/python",
)


def python_for(project_dir: Path) -> str:
    """O interpretador do projeto, com o do PATH como último recurso.

    O `python` do PATH tem as dependências de outra pessoa. Um projeto que
    declara `duckdb` no `requirements.txt` e o instalou no `.venv` dele quebra
    com `ModuleNotFoundError: No module named 'duckdb'` — de uma biblioteca que
    está instalada, só que em outro lugar. Foi assim que este código apareceu.
    """
    for relativo in VENV_INTERPRETERS:
        candidato = project_dir / relativo
        if candidato.is_file():
            return str(candidato)
    return "python"


#: Framework Python conhecido -> como subir em desenvolvimento. O módulo da
#: aplicação é procurado no disco, nunca chutado: um `app.main:app` que não
#: existe falha depois de subir, e o erro aparece longe da causa.
PY_ENTRYPOINT_CANDIDATES = (
    ("app/main.py", "app.main:app"),
    ("src/main.py", "src.main:app"),
    ("main.py", "main:app"),
    ("app.py", "app:app"),
    ("src/app.py", "src.app:app"),
)


def plan_from_python(project_dir: Path, port: int | None = None) -> RunPlan | None:
    """Deriva o comando de um projeto Python com framework ASGI/WSGI conhecido.

    Só cobre o caso em que dá para ter certeza. Projeto Python sem framework
    reconhecido não ganha plano nenhum — melhor não oferecer botão do que
    oferecer um que roda a coisa errada.
    """
    dependencias = _python_dependencies(project_dir)
    interpretador = python_for(project_dir)

    if "django" in dependencias and (project_dir / "manage.py").is_file():
        argv = [interpretador, "manage.py", "runserver"]
        if port:
            argv.append(f"127.0.0.1:{port}")
        return RunPlan(
            argv=_validate_argv(argv, origem="pyproject/requirements"),
            source="python",
            evidence="manage.py · django",
        )

    asgi = {"fastapi", "starlette", "uvicorn"} & dependencias
    if asgi:
        alvo = next(
            (
                modulo
                for arquivo, modulo in PY_ENTRYPOINT_CANDIDATES
                if (project_dir / arquivo).is_file()
            ),
            None,
        )
        if alvo is None:
            return None
        argv = [interpretador, "-m", "uvicorn", alvo, "--host", "127.0.0.1"]
        if port:
            argv += ["--port", str(port)]
        return RunPlan(
            argv=_validate_argv(argv, origem="pyproject/requirements"),
            source="python",
            evidence=f"uvicorn · {alvo}",
        )

    if "streamlit" in dependencias:
        alvo = next(
            (nome for nome in ("streamlit_app.py", "app.py", "main.py")
             if (project_dir / nome).is_file()),
            None,
        )
        if alvo:
            argv = [interpretador, "-m", "streamlit", "run", alvo]
            if port:
                argv += ["--server.port", str(port)]
            return RunPlan(
                argv=_validate_argv(argv, origem="dependências/código"),
                source="python",
                evidence=f"streamlit · {alvo}",
            )

    if "flask" in dependencias:
        argv = [interpretador, "-m", "flask", "run", "--host", "127.0.0.1"]
        if port:
            argv += ["--port", str(port)]
        return RunPlan(
            argv=_validate_argv(argv, origem="pyproject/requirements"),
            source="python",
            evidence="flask run",
        )

    return None


#: Arquivos de entrada olhados quando o projeto não declara dependência. São os
#: mesmos candidatos de ponto de entrada, mais os nomes clássicos de servidor.
CODIGO_DE_ENTRADA = (
    "app.py",
    "main.py",
    "server.py",
    "wsgi.py",
    "asgi.py",
    "run.py",
    "streamlit_app.py",
    "src/app.py",
    "src/main.py",
    "app/main.py",
)

#: Import que denuncia o framework. Só o que dá para subir sem adivinhar.
FRAMEWORKS_NO_CODIGO = ("flask", "fastapi", "starlette", "django", "streamlit", "uvicorn")


def _frameworks_no_codigo(project_dir: Path) -> set[str]:
    """Frameworks importados pelo código, quando não há arquivo de dependência.

    `import flask` num `app.py` é evidência **mais forte** que uma linha em
    `requirements.txt`: é o uso, não a intenção. O painel não olhava para isso,
    e por causa disso um Flask de um arquivo só — projeto leve, dos que mais
    aparecem — ficava sem botão de ligar, obrigando a escrever `devcockpit.yml`
    à mão para algo que estava explícito na primeira linha do arquivo.

    Só as primeiras linhas de cada candidato: import fica no topo, e ler o
    arquivo inteiro custaria caro num diretório grande.
    """
    encontrados: set[str] = set()

    for relativo in CODIGO_DE_ENTRADA:
        caminho = project_dir / relativo
        if not caminho.is_file():
            continue
        try:
            with caminho.open(encoding="utf-8", errors="replace") as arquivo:
                cabecalho = "".join(next(arquivo, "") for _ in range(40)).lower()
        except OSError:
            continue

        for framework in FRAMEWORKS_NO_CODIGO:
            if f"import {framework}" in cabecalho or f"from {framework}" in cabecalho:
                encontrados.add(framework)

    return encontrados


def _python_dependencies(project_dir: Path) -> set[str]:
    """Nomes de pacote declarados, em minúscula. Best-effort e sem executar nada."""
    encontrados: set[str] = set()

    pyproject = project_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            dados = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        except (tomllib.TOMLDecodeError, OSError):
            dados = {}
        bruto = (dados.get("project") or {}).get("dependencies") or []
        for item in bruto:
            if isinstance(item, str):
                encontrados.add(_package_name(item))

    requirements = project_dir / "requirements.txt"
    if requirements.is_file():
        try:
            linhas = requirements.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            linhas = []
        for linha in linhas:
            limpa = linha.strip()
            if limpa and not limpa.startswith(("#", "-")):
                encontrados.add(_package_name(limpa))

    # Sem nada declarado, o código responde. Com declaração, ela manda: quem
    # escreveu `requirements.txt` disse o que o projeto usa de verdade.
    if not encontrados:
        encontrados |= _frameworks_no_codigo(project_dir)

    return encontrados


def _package_name(spec: str) -> str:
    """`fastapi[all]>=0.115` -> `fastapi`."""
    nome = spec.strip()
    for separador in ("[", "=", ">", "<", "!", "~", ";", " "):
        nome = nome.split(separador, 1)[0]
    return nome.strip().lower()


# --- composição ----------------------------------------------------------


#: Subpastas de monorepo, na ordem em que fazem sentido subir. Backend antes de
#: frontend porque o front quase sempre depende dele — e porque subir o front
#: contra uma API morta produz uma tela que carrega e não funciona, que é pior
#: que não subir.
SUBPROJETOS = ("backend", "api", "server", "src/backend", "frontend", "web", "client", "app")


def plan_from_subproject(project_dir: Path, port: int | None = None) -> RunPlan | None:
    """Plano de um monorepo: procura um nível abaixo.

    Um repositório com `backend/` e `frontend/` não tem marcador nenhum na
    raiz, e o painel se declarava incapaz de subir — quando bastava olhar uma
    pasta adiante. Só um nível: dois já seria varredura, e varredura tem tela
    própria.
    """
    for relativo in SUBPROJETOS:
        sub = project_dir / relativo
        if not sub.is_dir():
            continue

        plano = plan_from_node(sub) or plan_from_python(sub, port=port)
        if plano is None:
            continue

        # `cwd` relativo ao projeto: o comando roda dentro da subpasta, e o
        # registro do painel continua apontando para a raiz do repositório.
        return RunPlan(
            argv=plano.argv,
            cwd=relativo,
            source=plano.source,
            evidence=f"{plano.evidence} · em {relativo}/",
            service=plano.service,
        )

    return None


#: Onde um site sem build costuma ter a página inicial.
RAIZES_ESTATICAS = ("", "app", "public", "dist", "site", "www")


def plan_from_static(project_dir: Path, port: int | None = None) -> RunPlan | None:
    """Site estático: serve a pasta, sem build nenhum.

    Existe porque projeto leve é justamente o que mais aparece e o que menos
    tinha resposta: um `index.html` com JavaScript solto não tem `dev script`
    nem framework, e mesmo assim precisa de um servidor — abrir o arquivo pelo
    `file://` quebra `fetch`, módulo ES e rota.

    `http.server` é da biblioteca padrão: não instala nada e existe em qualquer
    Python. Não serve para produção, e é justamente por isso que serve aqui.
    """
    for relativo in RAIZES_ESTATICAS:
        pasta = project_dir / relativo if relativo else project_dir
        if not (pasta / "index.html").is_file():
            continue

        argv = [python_for(project_dir), "-m", "http.server", str(port or 8080)]
        if relativo:
            argv += ["--directory", relativo]

        return RunPlan(
            argv=_validate_argv(argv, origem="estático"),
            source="static",
            evidence=f"index.html{f' em {relativo}/' if relativo else ''} · sem build",
        )

    return None


def resolve_run_plan(project_dir: Path, port: int | None = None) -> RunPlan | None:
    """O plano de execução do projeto, ou `None` se não der para saber.

    Ordem: o manifesto vence sempre. Ele é a declaração explícita de quem
    conhece o projeto, e adivinhação nunca deve passar por cima de decisão.
    """
    do_manifesto = plan_from_manifest(project_dir)
    if do_manifesto is not None:
        return do_manifesto

    # A ordem é a da confiança: framework declarado na raiz vence subpasta, que
    # vence servir estático. O estático é o último porque um `index.html` numa
    # pasta de build acompanharia um projeto que tem forma melhor de subir.
    return (
        plan_from_node(project_dir)
        or plan_from_python(project_dir, port=port)
        or plan_from_subproject(project_dir, port=port)
        or plan_from_static(project_dir, port=port)
    )
