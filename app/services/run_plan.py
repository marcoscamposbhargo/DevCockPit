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

    @property
    def display(self) -> str:
        return " ".join(self.argv)


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
                f"{origem}: a flag {flag!r} é destrutiva e não pode ser executada "
                "pelo painel."
            )


# --- origem 1: o manifesto do projeto ------------------------------------


def plan_from_manifest(project_dir: Path) -> RunPlan | None:
    """Lê o bloco `run:` do `devcockpit.yml`, se houver.

    Formato:

        run:
          cmd: ["npm", "run", "dev"]
          cwd: "frontend"        # opcional, relativo ao projeto
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

    return RunPlan(argv=argv, cwd=cwd, source="manifest", evidence="devcockpit.yml")


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

    if "django" in dependencias and (project_dir / "manage.py").is_file():
        argv = ["python", "manage.py", "runserver"]
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
            (modulo for arquivo, modulo in PY_ENTRYPOINT_CANDIDATES
             if (project_dir / arquivo).is_file()),
            None,
        )
        if alvo is None:
            return None
        argv = ["python", "-m", "uvicorn", alvo, "--host", "127.0.0.1"]
        if port:
            argv += ["--port", str(port)]
        return RunPlan(
            argv=_validate_argv(argv, origem="pyproject/requirements"),
            source="python",
            evidence=f"uvicorn · {alvo}",
        )

    if "flask" in dependencias:
        argv = ["python", "-m", "flask", "run", "--host", "127.0.0.1"]
        if port:
            argv += ["--port", str(port)]
        return RunPlan(
            argv=_validate_argv(argv, origem="pyproject/requirements"),
            source="python",
            evidence="flask run",
        )

    return None


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

    return encontrados


def _package_name(spec: str) -> str:
    """`fastapi[all]>=0.115` -> `fastapi`."""
    nome = spec.strip()
    for separador in ("[", "=", ">", "<", "!", "~", ";", " "):
        nome = nome.split(separador, 1)[0]
    return nome.strip().lower()


# --- composição ----------------------------------------------------------


def resolve_run_plan(project_dir: Path, port: int | None = None) -> RunPlan | None:
    """O plano de execução do projeto, ou `None` se não der para saber.

    Ordem: o manifesto vence sempre. Ele é a declaração explícita de quem
    conhece o projeto, e adivinhação nunca deve passar por cima de decisão.
    """
    do_manifesto = plan_from_manifest(project_dir)
    if do_manifesto is not None:
        return do_manifesto

    return plan_from_node(project_dir) or plan_from_python(project_dir, port=port)
