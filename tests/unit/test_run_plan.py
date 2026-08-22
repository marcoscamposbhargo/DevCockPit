"""De onde sai o comando que sobe um projeto, e o que ele recusa.

Esta é a peça que abriu uma exceção no ADR-003: o argv deixou de ser
exclusivamente literal no código. A contrapartida é que cada caminho de entrada
precisa ter um teste dizendo o que ele aceita e o que recusa — o que este
arquivo faz.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import ValidationError
from app.services.run_plan import (
    plan_from_manifest,
    plan_from_node,
    plan_from_python,
    resolve_run_plan,
)


def escreve(base: Path, nome: str, conteudo: str) -> Path:
    alvo = base / nome
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(conteudo, encoding="utf-8")
    return alvo


# --- manifesto ------------------------------------------------------------


def test_manifesto_declara_o_comando(tmp_path: Path) -> None:
    escreve(tmp_path, "devcockpit.yml", 'run:\n  cmd: ["npm", "run", "dev"]\n')

    plano = plan_from_manifest(tmp_path)

    assert plano is not None
    assert plano.argv == ["npm", "run", "dev"]
    assert plano.source == "manifest"


def test_manifesto_recusa_comando_como_texto(tmp_path: Path) -> None:
    """String de comando teria que ser partida por nós — e partir string de
    comando é de onde vem metade dos furos de injeção."""
    escreve(tmp_path, "devcockpit.yml", 'run:\n  cmd: "npm run dev"\n')

    with pytest.raises(ValidationError, match="lista de argumentos"):
        plan_from_manifest(tmp_path)


@pytest.mark.parametrize(
    "cmd",
    [
        '["docker", "compose", "down", "-v"]',
        '["git", "reset", "--hard"]',
        '["docker", "system", "prune", "--force"]',
    ],
)
def test_manifesto_recusa_comando_destrutivo(tmp_path: Path, cmd: str) -> None:
    """Não é defesa contra quem quer o mal — quem escreve o manifesto já pode
    mais que isso. É defesa contra o `run:` copiado de outro projeto que
    apagaria o volume do banco no primeiro clique."""
    escreve(tmp_path, "devcockpit.yml", f"run:\n  cmd: {cmd}\n")

    with pytest.raises(ValidationError):
        plan_from_manifest(tmp_path)


def test_manifesto_recusa_cwd_que_escapa_do_projeto(tmp_path: Path) -> None:
    escreve(tmp_path, "devcockpit.yml", 'run:\n  cmd: ["node", "x.js"]\n  cwd: "../fora"\n')

    with pytest.raises(Exception, match="escapa|relativo"):
        plan_from_manifest(tmp_path)


def test_manifesto_aceita_cwd_dentro_do_projeto(tmp_path: Path) -> None:
    escreve(tmp_path, "devcockpit.yml", 'run:\n  cmd: ["npm", "run", "dev"]\n  cwd: "frontend"\n')

    plano = plan_from_manifest(tmp_path)

    assert plano is not None
    assert plano.cwd == "frontend"


def test_manifesto_sem_bloco_run_nao_e_erro(tmp_path: Path) -> None:
    escreve(tmp_path, "devcockpit.yml", "version: 1\nname: x\n")

    assert plan_from_manifest(tmp_path) is None


def test_manifesto_ilegivel_nao_derruba(tmp_path: Path) -> None:
    """YAML quebrado vira "não sei subir", não uma exceção na cara do usuário."""
    escreve(tmp_path, "devcockpit.yml", "run:\n  cmd: [unclosed\n")

    assert plan_from_manifest(tmp_path) is None


# --- Node -----------------------------------------------------------------


def package(scripts: dict) -> str:
    return json.dumps({"name": "x", "scripts": scripts})


def test_node_prefere_dev_a_start(tmp_path: Path) -> None:
    """`start` roda a build de produção em muito projeto; `dev` é o que se quer."""
    escreve(tmp_path, "package.json", package({"start": "node .", "dev": "vite"}))

    plano = plan_from_node(tmp_path)

    assert plano is not None
    assert plano.argv == ["npm", "run", "dev"]


def test_node_usa_start_quando_nao_ha_dev(tmp_path: Path) -> None:
    escreve(tmp_path, "package.json", package({"start": "node ."}))

    assert plan_from_node(tmp_path).argv == ["npm", "run", "start"]


def test_node_sem_script_util_nao_inventa(tmp_path: Path) -> None:
    """Script que não existe não vira comando: falharia depois de clicar."""
    escreve(tmp_path, "package.json", package({"build": "tsc", "test": "vitest"}))

    assert plan_from_node(tmp_path) is None


@pytest.mark.parametrize(
    ("lockfile", "esperado"),
    [
        ("pnpm-lock.yaml", ["pnpm", "run", "dev"]),
        ("yarn.lock", ["yarn", "dev"]),
        ("bun.lockb", ["bun", "run", "dev"]),
        ("package-lock.json", ["npm", "run", "dev"]),
    ],
)
def test_node_respeita_o_gerenciador_do_lockfile(
    tmp_path: Path, lockfile: str, esperado: list[str]
) -> None:
    """Rodar `npm` num projeto com `pnpm-lock.yaml` reinstala a árvore errada."""
    escreve(tmp_path, "package.json", package({"dev": "vite"}))
    escreve(tmp_path, lockfile, "")

    assert plan_from_node(tmp_path).argv == esperado


def test_node_com_package_json_quebrado_nao_derruba(tmp_path: Path) -> None:
    escreve(tmp_path, "package.json", "{ isto não é json")

    assert plan_from_node(tmp_path) is None


# --- Python ---------------------------------------------------------------


def test_python_monta_uvicorn_com_o_modulo_que_existe(tmp_path: Path) -> None:
    escreve(tmp_path, "requirements.txt", "fastapi>=0.115\nuvicorn[standard]>=0.32\n")
    escreve(tmp_path, "app/main.py", "app = 1\n")

    plano = plan_from_python(tmp_path, port=8765)

    assert plano is not None
    assert plano.argv == [
        "python", "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8765",
    ]


def test_python_sem_ponto_de_entrada_nao_chuta(tmp_path: Path) -> None:
    """Um `app.main:app` inventado falha depois de subir, e o erro aparece
    longe da causa. Melhor não oferecer o botão."""
    escreve(tmp_path, "requirements.txt", "fastapi\n")

    assert plan_from_python(tmp_path) is None


def test_python_reconhece_django_pelo_manage(tmp_path: Path) -> None:
    escreve(tmp_path, "requirements.txt", "django>=5\n")
    escreve(tmp_path, "manage.py", "")

    plano = plan_from_python(tmp_path, port=8001)

    assert plano.argv == ["python", "manage.py", "runserver", "127.0.0.1:8001"]


def test_python_le_dependencia_do_pyproject(tmp_path: Path) -> None:
    escreve(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\ndependencies = ["flask>=3.0", "requests"]\n',
    )

    plano = plan_from_python(tmp_path, port=5000)

    assert plano is not None
    assert plano.argv[:4] == ["python", "-m", "flask", "run"]


def test_python_sem_framework_conhecido_nao_gera_plano(tmp_path: Path) -> None:
    escreve(tmp_path, "requirements.txt", "pandas\nnumpy\n")

    assert plan_from_python(tmp_path) is None


# --- composição -----------------------------------------------------------


def test_manifesto_vence_a_deteccao(tmp_path: Path) -> None:
    """Adivinhação nunca passa por cima de declaração explícita."""
    escreve(tmp_path, "package.json", package({"dev": "vite"}))
    escreve(tmp_path, "devcockpit.yml", 'run:\n  cmd: ["make", "dev"]\n')

    plano = resolve_run_plan(tmp_path)

    assert plano.argv == ["make", "dev"]
    assert plano.source == "manifest"


def test_projeto_sem_pista_alguma_nao_tem_plano(tmp_path: Path) -> None:
    escreve(tmp_path, "README.md", "# nada aqui")

    assert resolve_run_plan(tmp_path) is None
