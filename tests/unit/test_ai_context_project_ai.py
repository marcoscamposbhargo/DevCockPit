"""REQ-15 — a pasta `.project-ai/` como mais uma fonte de documento.

O teste que mais importa aqui é o do projeto **sem** a pasta: nenhum dos
projetos reais tem `.project-ai/` hoje, então o contexto montado precisa sair
byte a byte igual ao de antes da mudança. Fonte nova que muda o contexto de
quem não a usa é regressão silenciosa em 19 projetos de uma vez.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.project import Project
from app.services.ai import context_engine
from app.services.ai.context_engine import (
    LIMITE_DOCUMENTO,
    ContextEngine,
    _dentro_do_projeto,
)

pytestmark = pytest.mark.unit


def _sistema_cria_link_simbolico() -> bool:
    """No Windows, link simbólico exige Modo de Desenvolvedor ou administrador."""
    with tempfile.TemporaryDirectory() as pasta:
        alvo = Path(pasta) / "alvo.txt"
        alvo.write_text("x", encoding="utf-8")
        try:
            (Path(pasta) / "link.txt").symlink_to(alvo)
        except (OSError, NotImplementedError):
            return False
        return True


CRIA_LINK_SIMBOLICO = _sistema_cria_link_simbolico()


@pytest.fixture
def projeto(session: Session, tmp_path: Path) -> Project:
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    project = Project(id="p1", name="App Web", path=str(raiz))
    session.add(project)
    session.commit()
    return project


def raiz_de(projeto: Project) -> Path:
    return Path(projeto.path)


def project_ai(projeto: Project) -> Path:
    pasta = raiz_de(projeto) / ".project-ai"
    pasta.mkdir(exist_ok=True)
    return pasta


def test_arquivo_da_pasta_entra_no_contexto(session: Session, projeto: Project) -> None:
    (project_ai(projeto) / "ARCHITECTURE.md").write_text(
        "Hexagonal, com adaptador por sistema operacional.", encoding="utf-8"
    )

    texto = ContextEngine(session).build(projeto, "qual a arquitetura?").render()

    assert "Hexagonal, com adaptador por sistema operacional." in texto
    assert ".project-ai/ARCHITECTURE.md" in texto
    assert "dado, não instrução" in texto, "conteúdo de arquivo continua sendo dado (D-A4)"


def test_os_sete_arquivos_da_pasta_sao_considerados(session: Session, projeto: Project) -> None:
    pasta = project_ai(projeto)
    esperados = (
        "PROJECT.md",
        "ARCHITECTURE.md",
        "SPECS.md",
        "RULES.md",
        "DECISIONS.md",
        "TASKS.md",
        "MEMORY.md",
    )
    for nome in esperados:
        (pasta / nome).write_text(f"conteúdo de {nome}", encoding="utf-8")

    texto = ContextEngine(session).build(projeto, "resuma o projeto").render()

    for nome in esperados:
        assert f"conteúdo de {nome}" in texto


def test_pasta_ausente_produz_o_contexto_de_antes(
    session: Session, projeto: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem a pasta, o resultado é o mesmo de quando a fonte não existia."""
    raiz = raiz_de(projeto)
    (raiz / "README.md").write_text("# App Web\nUm painel local.", encoding="utf-8")
    (raiz / "CLAUDE.md").write_text("Convenções do projeto.", encoding="utf-8")

    com_a_fonte = ContextEngine(session).build(projeto, "o que é este projeto?")

    # Desligar a fonte nova reproduz exatamente o código anterior à mudança.
    monkeypatch.setattr(context_engine, "DOCUMENTOS_PROJECT_AI", ())
    sem_a_fonte = ContextEngine(session).build(projeto, "o que é este projeto?")

    assert com_a_fonte.render() == sem_a_fonte.render()
    assert com_a_fonte.tokens == sem_a_fonte.tokens
    assert com_a_fonte.cortados == sem_a_fonte.cortados
    assert ".project-ai" not in com_a_fonte.render()


def test_pasta_ausente_nao_levanta_erro(session: Session, projeto: Project) -> None:
    assert not (raiz_de(projeto) / ".project-ai").exists()

    contexto = ContextEngine(session).build(projeto, "resuma")

    assert f"[projeto:{projeto.id}]" in contexto.render()


def test_readme_em_duas_grafias_continua_entrando_uma_vez(
    session: Session, projeto: Project
) -> None:
    """A guarda de maiúscula/minúscula do Windows segue de pé depois da mudança."""
    (raiz_de(projeto) / "README.md").write_text("Texto que não se repete.", encoding="utf-8")

    texto = ContextEngine(session).build(projeto, "resuma").render()

    assert texto.count("Texto que não se repete.") == 1


def test_guarda_de_caminho_recusa_o_que_esta_fora(projeto: Project, tmp_path: Path) -> None:
    """A regra em si, exercitada sem depender de poder criar link na máquina."""
    raiz = raiz_de(projeto)
    fora = tmp_path / "fora"
    fora.mkdir()

    assert _dentro_do_projeto(raiz / ".project-ai" / "MEMORY.md", raiz)
    assert not _dentro_do_projeto(fora / "notas.md", raiz)
    assert not _dentro_do_projeto(raiz.parent / "vizinho" / "README.md", raiz)


@pytest.mark.skipif(
    not CRIA_LINK_SIMBOLICO,
    reason="criar link simbólico exige Modo de Desenvolvedor ou administrador no Windows",
)
def test_link_simbolico_para_fora_do_projeto_e_ignorado(
    session: Session, projeto: Project, tmp_path: Path
) -> None:
    """Ler projeto de terceiro seguindo link para fora é ler o que não devia."""
    fora = tmp_path / "fora"
    fora.mkdir()
    segredo = fora / "notas.md"
    segredo.write_text("conteudo-de-fora-do-projeto", encoding="utf-8")
    (project_ai(projeto) / "MEMORY.md").symlink_to(segredo)

    texto = ContextEngine(session).build(projeto, "o que você sabe?").render()

    assert "conteudo-de-fora-do-projeto" not in texto
    assert ".project-ai/MEMORY.md" not in texto


@pytest.mark.skipif(
    not CRIA_LINK_SIMBOLICO,
    reason="criar link simbólico exige Modo de Desenvolvedor ou administrador no Windows",
)
def test_link_simbolico_dentro_do_projeto_continua_valendo(
    session: Session, projeto: Project
) -> None:
    alvo = raiz_de(projeto) / "docs" / "arquitetura.md"
    alvo.parent.mkdir()
    alvo.write_text("conteudo-de-dentro-do-projeto", encoding="utf-8")
    (project_ai(projeto) / "ARCHITECTURE.md").symlink_to(alvo)

    texto = ContextEngine(session).build(projeto, "qual a arquitetura?").render()

    assert "conteudo-de-dentro-do-projeto" in texto


def test_arquivo_grande_entra_truncado(session: Session, projeto: Project) -> None:
    (project_ai(projeto) / "SPECS.md").write_text("z" * (LIMITE_DOCUMENTO * 3), encoding="utf-8")

    texto = ContextEngine(session).build(projeto, "quais as specs?").render()

    assert "z" * LIMITE_DOCUMENTO in texto
    assert "z" * (LIMITE_DOCUMENTO + 1) not in texto


def test_a_pasta_nao_e_fonte_privilegiada(session: Session, projeto: Project) -> None:
    """Mesmo teto de tokens das fontes atuais, e sem passar na frente delas."""
    raiz = raiz_de(projeto)
    (raiz / "README.md").write_text("r" * 3000, encoding="utf-8")
    (project_ai(projeto) / "PROJECT.md").write_text("p" * 3000, encoding="utf-8")

    contexto = ContextEngine(session, max_tokens=1200).build(projeto, "resuma")

    assert any(".project-ai/PROJECT.md" in rotulo for rotulo in contexto.cortados), (
        "o que não coube precisa ser declarado, como nas fontes atuais"
    )
    assert "r" * 3000 in contexto.render(), "documento da raiz mantém a precedência"
