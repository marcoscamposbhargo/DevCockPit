"""Health Score — Fase 4.

O que estes testes protegem é uma regra, não um cálculo: **indicador sem dado
não vira zero**. Zero é uma afirmação sobre o projeto ("está ruim"); ausência é
uma afirmação sobre o painel ("não sei"). Toda ferramenta que já confundiu as
duas produziu uma barra vermelha que ninguém sabia como responder.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.ai import AiMemory, AiSession, MemoryKind
from app.models.base import utcnow
from app.models.project import ActivityLog, ActivityStatus, Project
from app.models.task import AiTask, TaskStatus
from app.services.intelligence_service import IntelligenceService

pytestmark = pytest.mark.unit


@pytest.fixture
def projeto(session: Session, workspace: Path) -> Project:
    pasta = workspace / "app"
    pasta.mkdir()
    project = Project(id="app", name="App", path=str(pasta))
    session.add(project)
    session.flush()
    return project


def indicador(score, chave: str):  # type: ignore[no-untyped-def]
    return next(i for i in score.indicadores if i.chave == chave)


# --- a regra que sustenta o resto -----------------------------------------


def test_projeto_vazio_nao_recebe_nota_zero(session: Session, projeto: Project) -> None:
    """Um projeto recém-cadastrado não é um projeto ruim: é um desconhecido."""
    score = IntelligenceService(session).score(projeto)

    sem_dado = [i.chave for i in score.indicadores if i.nota is None]
    assert {"ambiente", "atividade", "tarefas", "divida"} <= set(sem_dado)


def test_o_agregado_ignora_o_que_nao_foi_medido(session: Session, projeto: Project) -> None:
    """Média sobre os medidos, e a cobertura dita junto.

    Sem a cobertura, 80 com dois indicadores e 80 com seis pareceriam a mesma
    coisa — e não são.
    """
    (Path(projeto.path) / "README.md").write_text("# App\n", encoding="utf-8")
    (Path(projeto.path) / "docs").mkdir()
    (Path(projeto.path) / "devcockpit.yml").write_text("version: 1\n", encoding="utf-8")

    score = IntelligenceService(session).score(projeto)

    assert indicador(score, "documentacao").nota == 100
    assert score.score is not None
    assert score.cobertura.endswith(f"de {len(score.indicadores)}")
    assert len(score.medidos) < len(score.indicadores), "o resto continua não medido"


def test_pasta_ausente_nao_e_nota_ruim(session: Session, workspace: Path) -> None:
    """Projeto cujo diretório sumiu não tem documentação ruim: não tem resposta."""
    project = Project(id="sumido", name="Sumido", path=str(workspace / "nao-existe"))
    session.add(project)
    session.flush()

    score = IntelligenceService(session).score(project)

    assert indicador(score, "documentacao").nota is None
    assert indicador(score, "testes").nota is None


# --- indicadores um a um ---------------------------------------------------


def test_pasta_de_teste_vazia_vale_menos_que_teste_de_verdade(
    session: Session, projeto: Project
) -> None:
    (Path(projeto.path) / "tests").mkdir()

    vazia = indicador(IntelligenceService(session).score(projeto), "testes")
    assert vazia.nota == 50

    (Path(projeto.path) / "tests" / "test_algo.py").write_text("", encoding="utf-8")
    cheia = indicador(IntelligenceService(session).score(projeto), "testes")
    assert cheia.nota == 100


def test_sem_pasta_de_teste_e_zero_de_verdade(session: Session, projeto: Project) -> None:
    """Aqui zero é afirmação legítima: o painel olhou e não havia.

    A distinção com "não medido" é o ponto: um foi verificado, o outro não.
    """
    testes = indicador(IntelligenceService(session).score(projeto), "testes")

    assert testes.nota == 0
    assert "Nenhuma pasta de teste" in testes.evidencia


def test_ambiente_mede_o_que_o_painel_executou(session: Session, projeto: Project) -> None:
    for status in (ActivityStatus.SUCCESS, ActivityStatus.SUCCESS, ActivityStatus.FAILED):
        session.add(
            ActivityLog(
                project_id=projeto.id,
                action="environment.up",
                status=status.value,
                actor="user",
            )
        )
    session.flush()

    ambiente = indicador(IntelligenceService(session).score(projeto), "ambiente")

    assert ambiente.nota == 67, "2 de 3 concluíram"
    assert "2 de 3" in ambiente.evidencia


def test_operacao_antiga_nao_conta_como_ambiente_medido(
    session: Session, projeto: Project
) -> None:
    """Sucesso de três meses atrás não diz nada sobre o ambiente de hoje."""
    session.add(
        ActivityLog(
            project_id=projeto.id,
            action="environment.up",
            status=ActivityStatus.SUCCESS.value,
            actor="user",
            created_at=utcnow() - timedelta(days=90),
        )
    )
    session.flush()

    assert indicador(IntelligenceService(session).score(projeto), "ambiente").nota is None


def test_tarefas_medem_o_que_foi_fechado(session: Session, projeto: Project) -> None:
    session.add(AiTask(project_id=projeto.id, title="a", status=TaskStatus.DONE.value))
    session.add(AiTask(project_id=projeto.id, title="b", status=TaskStatus.OPEN.value))
    session.flush()

    tarefas = indicador(IntelligenceService(session).score(projeto), "tarefas")

    assert tarefas.nota == 50
    assert "1 em aberto" in tarefas.evidencia


def test_divida_registrada_derruba_a_nota_e_satura(session: Session, projeto: Project) -> None:
    """Dez itens ou trinta são a mesma mensagem.

    Fingir precisão entre eles seria o número inventado que este módulo recusa.
    """
    for indice in range(30):
        session.add(
            AiMemory(
                project_id=projeto.id,
                kind=MemoryKind.DEBT.value,
                title=f"dívida {indice}",
                body="x",
            )
        )
    session.flush()

    assert indicador(IntelligenceService(session).score(projeto), "divida").nota == 0


def test_sessao_recente_conta_como_atividade(session: Session, projeto: Project) -> None:
    for indice in range(3):
        session.add(AiSession(id=f"s{indice}", project_id=projeto.id, started_at=utcnow()))
    session.flush()

    atividade = indicador(IntelligenceService(session).score(projeto), "atividade")

    assert atividade.nota == 100


def test_projeto_parado_ha_muito_tempo_e_zero_e_diz_desde_quando(
    session: Session, projeto: Project
) -> None:
    session.add(
        AiSession(id="s", project_id=projeto.id, started_at=utcnow() - timedelta(days=60))
    )
    session.flush()

    atividade = indicador(IntelligenceService(session).score(projeto), "atividade")

    assert atividade.nota == 0
    assert "60 dia" in atividade.evidencia


# --- contrato HTTP ---------------------------------------------------------


def test_rota_devolve_indicadores_com_evidencia(client, sample_project) -> None:  # type: ignore[no-untyped-def]
    """Número sem explicação não dá para agir.

    A evidência é o que separa "62" de "62 porque falta README e dois testes".
    """
    from tests.conftest import WRITE_HEADERS

    criado = client.post(
        "/api/projects", json={"path": str(sample_project)}, headers=WRITE_HEADERS
    ).json()

    dados = client.get(f"/api/projects/{criado['id']}/intelligence").json()

    assert dados["project_id"] == criado["id"]
    assert dados["cobertura"]
    assert all(i["evidencia"] for i in dados["indicadores"])


def test_teste_em_subpasta_de_monorepo_conta(session: Session, projeto: Project) -> None:
    """Olhar só a raiz daria "0 testes" para um projeto com `backend/tests` cheio.

    É a forma de defeito que este painel já produziu três vezes — correção que
    para na raiz —, e aqui ela seria pior: zero é afirmação forte, e afirmação
    forte errada vale menos que silêncio.
    """
    backend = Path(projeto.path) / "backend" / "tests"
    backend.mkdir(parents=True)
    (backend / "test_algo.py").write_text("", encoding="utf-8")

    testes = indicador(IntelligenceService(session).score(projeto), "testes")

    assert testes.nota == 100
    assert "backend/tests" in testes.evidencia


# --- próxima ação (4.3) ----------------------------------------------------


def test_sem_fato_nenhum_nao_ha_recomendacao(session: Session, workspace: Path) -> None:
    """Lista vazia é resposta legítima.

    Recomendação sem fato para citar seria o palpite que este módulo recusa, e
    o custo de inventar é alto: uma sugestão errada some com a confiança nas
    certas.

    O caso é o projeto cuja pasta sumiu — nada pôde ser medido. Um projeto
    vazio **com** pasta é diferente: "não tem README" é fato, e vira
    recomendação com razão.
    """
    project = Project(id="sumido", name="Sumido", path=str(workspace / "nao-existe"))
    session.add(project)
    session.flush()

    assert IntelligenceService(session).recomendacoes(project) == []


def test_projeto_vazio_com_pasta_recomenda_pelo_que_foi_medido(
    session: Session, projeto: Project
) -> None:
    """"Falta README" é fato apurado, não palpite — e por isso pode recomendar."""
    recomendacoes = IntelligenceService(session).recomendacoes(projeto)

    assert len(recomendacoes) == 1
    assert "Documentação está em 0" in recomendacoes[0].porque


def test_o_que_voce_escreveu_vem_antes_de_tudo(session: Session, projeto: Project) -> None:
    """A única coisa pior que não recomendar nada é recomendar por cima de uma
    decisão que o dono do projeto já tomou."""
    session.add(
        AiSession(
            id="s",
            project_id=projeto.id,
            started_at=utcnow() - timedelta(days=1),
            ended_at=utcnow() - timedelta(days=1),
            next_steps="Trocar o driver do banco\nDepois: revisar o schema",
        )
    )
    session.add(AiTask(project_id=projeto.id, title="Outra coisa", priority=1))
    session.flush()

    primeira = IntelligenceService(session).recomendacoes(projeto)[0]

    assert primeira.titulo == "Trocar o driver do banco"
    assert "declarou isso ao fechar a sessão" in primeira.porque


def test_tarefa_aberta_entra_com_a_prioridade_como_motivo(
    session: Session, projeto: Project
) -> None:
    session.add(AiTask(project_id=projeto.id, title="Baixa", priority=3))
    session.add(AiTask(project_id=projeto.id, title="Alta", priority=1))
    session.flush()

    titulos = [r.titulo for r in IntelligenceService(session).recomendacoes(projeto)]

    assert "Alta" in titulos and "Baixa" not in titulos, "uma tarefa por vez, a mais urgente"


def test_aviso_de_porta_vira_recomendacao_com_o_texto_do_aviso(
    session: Session, projeto: Project
) -> None:
    """Incoerência medida vale mais que indicador baixo: ela quebra o painel."""
    aviso = "O comando sobe na porta 3001, mas o serviço está cadastrado na 3013."

    recomendacoes = IntelligenceService(session).recomendacoes(projeto, aviso_de_porta=aviso)

    assert any(r.porque == aviso and r.onde == "server" for r in recomendacoes)


def test_toda_recomendacao_carrega_um_fato(session: Session, projeto: Project) -> None:
    session.add(AiTask(project_id=projeto.id, title="Fazer algo", priority=2))
    session.flush()

    for recomendacao in IntelligenceService(session).recomendacoes(projeto):
        assert recomendacao.porque, f"{recomendacao.titulo} não diz por quê"
