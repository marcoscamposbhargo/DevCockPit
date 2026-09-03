"""A linha por tentativa de execução da IA (REQ-10) e o agregado do período.

Dois compromissos são testados aqui porque nenhum dos dois se defende sozinho no
código:

- **o conteúdo da conversa não entra nesta tabela.** Uma varredura das colunas
  prova que não existe onde guardar prompt nem resposta, e ela falha no dia em
  que alguém adicionar a coluna "só para depurar";
- **custo e latência sem medição são `null`, nunca `0`** (**P-02**). Banco vazio
  devolve "não medido"; um teste falha se algum indicador vier zerado por
  ausência de dado.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.ai_run import AiRun, RunDecision, RunStatus
from app.models.base import utcnow
from app.repositories.ai_repository import RunRepository

pytestmark = pytest.mark.unit

#: As colunas que o plano fixou. Comparação por igualdade, e não por "contém":
#: é o que faz a coluna nova aparecer no teste em vez de passar despercebida.
COLUNAS_ESPERADAS = {
    "id",
    "correlation_id",
    "attempt",
    "provider",
    "model",
    "task_type",
    "decision",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "status",
    "estimated_cost",
    "price_date",
    "error",
    "created_at",
}

#: Vocabulário de coluna que guardaria conteúdo de conversa.
PALAVRAS_DE_CONTEUDO = (
    "prompt",
    "resposta",
    "response",
    "content",
    "conteudo",
    "message",
    "mensagem",
    "texto",
    "text",
    "pergunta",
    "question",
    "answer",
    "completion",
    "body",
)


def tentativa(**campos) -> AiRun:  # type: ignore[no-untyped-def]
    base = {
        "correlation_id": "c-1",
        "attempt": 1,
        "provider": "ollama",
        "model": "qwen2.5-coder:7b",
        "task_type": "code_review",
        "decision": RunDecision.AUTO.value,
        "tokens_in": 100,
        "tokens_out": 50,
        "latency_ms": 900,
        "status": RunStatus.OK.value,
    }
    base.update(campos)
    return AiRun(**base)


class TestSemConteudoDeConversa:
    def test_a_tabela_nao_tem_onde_guardar_prompt_nem_resposta(self) -> None:
        nomes = {coluna.name for coluna in AiRun.__table__.columns}

        assert nomes == COLUNAS_ESPERADAS

        suspeitas = {
            nome for nome in nomes for palavra in PALAVRAS_DE_CONTEUDO if palavra in nome.lower()
        }
        assert suspeitas == set(), (
            f"Coluna de conteúdo em ai_run: {sorted(suspeitas)}. "
            "REQ-10: prompt e resposta não entram na linha de tentativa."
        )

    def test_a_unica_coluna_de_texto_livre_e_a_mensagem_de_erro(self) -> None:
        """`error` é a única com espaço para texto — e ela chega mascarada.

        Se amanhã existir uma segunda coluna de texto livre, é nela que o prompt
        vai acabar entrando. O teste falha antes disso.
        """
        livres = [
            coluna.name
            for coluna in AiRun.__table__.columns
            if coluna.type.__class__.__name__ == "Text"
        ]
        assert livres == ["error"]

    def test_nao_ha_atributo_que_aceite_o_texto_da_pergunta(self) -> None:
        """Quem tentar levar o prompt para cá esbarra no construtor."""
        for campo in ("prompt", "content", "resposta", "answer"):
            with pytest.raises(TypeError):
                AiRun(correlation_id="c-1", **{campo: "revise este arquivo"})


class TestCadeiaDeTentativas:
    def test_tres_tentativas_do_mesmo_correlation_id_voltam_em_ordem(
        self, session: Session
    ) -> None:
        repositorio = RunRepository(session)
        repositorio.add_all(
            [
                tentativa(
                    attempt=3,
                    provider="kimi",
                    model="kimi-k2",
                    latency_ms=1200,
                    status=RunStatus.OK.value,
                ),
                tentativa(
                    attempt=1,
                    provider="ollama",
                    model="qwen2.5-coder:7b",
                    latency_ms=30_000,
                    status=RunStatus.TIMEOUT.value,
                    error="tempo esgotado em 30s",
                ),
                tentativa(
                    attempt=2,
                    provider="deepseek",
                    model="deepseek-chat",
                    latency_ms=400,
                    status=RunStatus.ERROR.value,
                    error="HTTP 429",
                ),
            ]
        )
        session.commit()

        cadeia = repositorio.list_for("c-1")

        assert [linha.attempt for linha in cadeia] == [1, 2, 3]
        assert [linha.provider for linha in cadeia] == ["ollama", "deepseek", "kimi"]
        assert [linha.status for linha in cadeia] == ["timeout", "error", "ok"]
        assert all(linha.latency_ms > 0 for linha in cadeia)
        assert [linha.falhou for linha in cadeia] == [True, True, False]

    def test_correlation_id_de_outra_pergunta_nao_entra_na_cadeia(
        self, session: Session
    ) -> None:
        repositorio = RunRepository(session)
        repositorio.add_all([tentativa(), tentativa(correlation_id="c-2", attempt=1)])
        session.commit()

        assert len(repositorio.list_for("c-1")) == 1
        assert len(repositorio.list_for("c-3")) == 0

    def test_gravar_lista_vazia_nao_faz_nada(self, session: Session) -> None:
        assert RunRepository(session).add_all([]) == []


class TestCustoNaoMedido:
    def test_tentativa_sem_preco_declarado_grava_nulo(self, session: Session) -> None:
        repositorio = RunRepository(session)
        repositorio.add(tentativa())
        session.commit()

        linha = repositorio.list_for("c-1")[0]
        assert linha.estimated_cost is None
        assert linha.price_date is None

    def test_tentativa_com_preco_guarda_valor_e_data(self, session: Session) -> None:
        repositorio = RunRepository(session)
        repositorio.add(tentativa(estimated_cost=0.000123, price_date="2026-09-03"))
        session.commit()

        linha = repositorio.list_for("c-1")[0]
        assert linha.estimated_cost == pytest.approx(0.000123)
        assert linha.price_date == "2026-09-03"


class TestAgregadoDoPeriodo:
    def test_banco_vazio_devolve_nao_medido_em_vez_de_zero(self, session: Session) -> None:
        resumo = RunRepository(session).aggregate(
            since=utcnow() - timedelta(days=7), local_providers=["ollama"]
        )

        assert resumo.attempts == 0
        assert resumo.estimated_cost is None
        assert resumo.avg_latency_ms is None
        assert resumo.price_date is None

    def test_periodo_com_dados_soma_tudo_o_que_a_tela_de_consumo_mostra(
        self, session: Session
    ) -> None:
        agora = utcnow()
        repositorio = RunRepository(session)
        repositorio.add_all(
            [
                tentativa(
                    attempt=1,
                    provider="ollama",
                    tokens_in=100,
                    tokens_out=50,
                    latency_ms=30_000,
                    status=RunStatus.TIMEOUT.value,
                    error="tempo esgotado",
                    created_at=agora - timedelta(hours=1),
                ),
                tentativa(
                    attempt=2,
                    provider="deepseek",
                    model="deepseek-chat",
                    tokens_in=200,
                    tokens_out=300,
                    latency_ms=1_000,
                    estimated_cost=0.002,
                    price_date="2026-09-01",
                    created_at=agora - timedelta(minutes=59),
                ),
                tentativa(
                    correlation_id="c-2",
                    provider="kimi",
                    model="kimi-k2",
                    tokens_in=10,
                    tokens_out=20,
                    latency_ms=500,
                    estimated_cost=0.001,
                    price_date="2026-09-03",
                    created_at=agora - timedelta(minutes=30),
                ),
                # Candidato que a cadeia nem chegou a tentar: não é falha, e não
                # entra na média de latência.
                tentativa(
                    correlation_id="c-2",
                    attempt=2,
                    provider="deepseek",
                    model="deepseek-chat",
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=0,
                    status=RunStatus.SKIPPED.value,
                    created_at=agora - timedelta(minutes=30),
                ),
            ]
        )
        session.commit()

        resumo = repositorio.aggregate(
            since=agora - timedelta(days=1), local_providers=["ollama"]
        )

        assert resumo.attempts == 4
        assert resumo.questions == 2
        assert resumo.tokens_in == 310
        assert resumo.tokens_out == 370
        assert (resumo.local_attempts, resumo.local_tokens) == (1, 150)
        assert (resumo.cloud_attempts, resumo.cloud_tokens) == (3, 530)
        assert resumo.estimated_cost == pytest.approx(0.003)
        assert resumo.price_date == "2026-09-03"
        assert resumo.attempts_without_cost == 2
        # Só as três executadas: (30000 + 1000 + 500) / 3.
        assert resumo.avg_latency_ms == pytest.approx(10_500)
        assert resumo.failures == 1
        # As duas perguntas precisaram de uma segunda tentativa.
        assert resumo.fallbacks == 2

    def test_tentativa_fora_da_janela_nao_entra(self, session: Session) -> None:
        agora = utcnow()
        repositorio = RunRepository(session)
        repositorio.add_all(
            [
                tentativa(created_at=agora - timedelta(days=30)),
                tentativa(correlation_id="c-2", created_at=agora - timedelta(hours=2)),
            ]
        )
        session.commit()

        resumo = repositorio.aggregate(
            since=agora - timedelta(days=1), local_providers=["ollama"]
        )
        assert resumo.attempts == 1
        assert resumo.questions == 1

    def test_sem_provedor_local_declarado_tudo_conta_como_nuvem(
        self, session: Session
    ) -> None:
        repositorio = RunRepository(session)
        repositorio.add(tentativa(provider="deepseek", model="deepseek-chat"))
        session.commit()

        resumo = repositorio.aggregate(
            since=utcnow() - timedelta(days=1), local_providers=[]
        )
        assert (resumo.local_attempts, resumo.cloud_attempts) == (0, 1)

    def test_custo_parcial_diz_quantas_tentativas_ficaram_sem_conta(
        self, session: Session
    ) -> None:
        """Somar só o que tem preço e calar sobre o resto seria mentir por omissão."""
        agora = utcnow()
        repositorio = RunRepository(session)
        repositorio.add_all(
            [
                tentativa(estimated_cost=0.005, price_date="2026-09-03"),
                tentativa(correlation_id="c-2", provider="ollama"),
            ]
        )
        session.commit()

        resumo = repositorio.aggregate(
            since=agora - timedelta(days=1), local_providers=["ollama"]
        )
        assert resumo.estimated_cost == pytest.approx(0.005)
        assert resumo.attempts_without_cost == 1
