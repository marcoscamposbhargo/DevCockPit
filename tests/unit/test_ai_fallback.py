"""A cadeia de fallback e o registro de cada tentativa (REQ-09, REQ-10).

Quatro coisas precisam ser verdade ao mesmo tempo, e nenhuma delas se defende
sozinha lendo o runner:

- **a cadeia anda enquanto vale a pena andar.** Timeout, 5xx e modelo ausente
  passam para o próximo candidato; chave recusada e erro que ninguém catalogou
  param ali mesmo, porque a partir deste ciclo cada tentativa custa dinheiro;
- **nenhum provider é tentado duas vezes** na mesma pergunta;
- **o banco não fica travado durante a resposta.** É o risco 1 do plano e a
  regressão que a Fase 3 já pagou (`fbabea1`): transação aberta pelos minutos de
  um stream local devolvia `database is locked` em botão sem relação com a IA.
  Aqui isso vira teste — inclusive o que prova que o teste tem dente;
- **o conteúdo da conversa não entra na linha de tentativa** (REQ-10). Uma
  varredura procura trechos do prompt nas colunas gravadas e falha se achar.

Tudo com `FakeProvider` roteirizado: sem rede, sem chave e sem Ollama (**P-06**).
"""

from __future__ import annotations

import textwrap
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ai_run import AiRun, RunStatus
from app.models.project import Project
from app.repositories.ai_repository import RunRepository
from app.services.ai.classifier import Classificacao
from app.services.ai.model_router import Candidato, Decisao
from app.services.ai.model_router import escolher as escolher_modelo
from app.services.ai.providers import (
    AIRequest,
    AIUsage,
    FakeProvider,
    Message,
    ProviderError,
    ProviderNotConfigured,
)
from app.services.ai.registry import AiConfig
from app.services.ai.runner import (
    CadeiaEsgotada,
    PerguntaRecusada,
    Runner,
    SemCandidato,
    classificar_erro,
)

pytestmark = pytest.mark.unit


#: Um provider local e dois de nuvem, com dois modelos no mesmo provider de
#: nuvem — é esse par que exercita "nenhum provider tentado duas vezes". Só
#: `rapido` tem preço declarado: custo é medição, não padrão (**P-02**).
REGISTRO = """
    providers:
      - id: caseiro
        enabled: true
        type: local
        base_url: http://127.0.0.1:11434
      - id: nuvem-a
        enabled: true
        type: cloud
        base_url: http://127.0.0.1:9
        api_key_env: DEVCOCKPIT_AI_KEY_TESTE_A
      - id: nuvem-b
        enabled: true
        type: cloud
        base_url: http://127.0.0.1:9
        api_key_env: DEVCOCKPIT_AI_KEY_TESTE_B

    modelos:
      - id: local-codigo
        model: modelo-caseiro
        capabilities: [coding]
        providers: [caseiro]
        cost_tier: free
        context_window: 32768
      - id: rapido
        model: modelo-rapido
        capabilities: [coding, qa]
        providers: [nuvem-a]
        cost_tier: low
        context_window: 64000
      - id: irmao
        model: modelo-irmao
        capabilities: [coding]
        providers: [nuvem-a]
        cost_tier: low
        context_window: 64000
      - id: reserva
        model: modelo-reserva
        capabilities: [coding, qa]
        providers: [nuvem-b]
        cost_tier: high
        context_window: 200000

    precos:
      rapido:
        input_por_milhao: 1.0
        output_por_milhao: 2.0
        anotado_em: "2026-09-03"

    roteamento:
      limiar_complexidade: 40
      modelo_padrao: rapido
"""

#: A pergunta de teste. Nenhum pedaço dela pode aparecer em `ai_run` (REQ-10).
PERGUNTA = "revise o contrato da Acme, que vence em março, no arquivo faturamento.py"

#: Trechos procurados na varredura. Palavra comum não serve: teria que ser
#: procurada e não achada por acaso.
TRECHOS_DO_PROMPT = ("acme", "faturamento.py", "vence em março")


@pytest.fixture
def registro(tmp_path: Path) -> AiConfig:
    caminho = tmp_path / "ai.yml"
    caminho.write_text(textwrap.dedent(REGISTRO), encoding="utf-8")
    return AiConfig.load(caminho)


# --- o provedor roteirizado -----------------------------------------------


class ProvedorRoteirizado(FakeProvider):
    """`FakeProvider` com roteiro: responde, ou levanta o erro combinado.

    `pedacos_antes` maior que zero é o caso do stream que quebra no meio, depois
    de já ter entregue texto à tela.
    """

    def __init__(
        self,
        name: str,
        *,
        resposta: str = "resposta boa",
        erro: Exception | None = None,
        tokens: tuple[int, int] = (0, 0),
        pedacos_antes: int = 0,
    ) -> None:
        super().__init__(model=f"{name}-modelo", resposta=resposta)
        self.name = name
        self.erro = erro
        self.pedacos_antes = pedacos_antes
        self.chamadas = 0
        self.last_usage = AIUsage(tokens_in=tokens[0], tokens_out=tokens[1])

    def stream(self, request: AIRequest):  # type: ignore[no-untyped-def]
        self.chamadas += 1
        self.last_request = request
        pedacos = [parte + " " for parte in self.resposta.split(" ")]
        if self.erro is not None:
            yield from pedacos[: self.pedacos_antes]
            raise self.erro
        yield from pedacos


def erro_de_timeout() -> ProviderError:
    return ProviderError("O Ollama conectou mas não respondeu a tempo (120s).")


def erro_de_conexao() -> ProviderError:
    """Erro de transporte cru, como o provider o embrulha na vida real."""
    erro = ProviderError("Falha ao falar com nuvem-a: [Errno 10061].")
    erro.__cause__ = httpx.ConnectError("connection refused")
    return erro


def erro_5xx(detalhe: str = "serviço indisponível") -> ProviderError:
    return ProviderError(f"O provedor respondeu 503. {detalhe}")


def erro_de_chave() -> ProviderError:
    return ProviderError(
        "O provedor recusou a chave de API. Confira `DEVCOCKPIT_AI_API_KEY` no seu `.env`."
    )


def erro_de_modelo_ausente() -> ProviderError:
    return ProviderError(
        "O modelo 'modelo-caseiro' não está instalado no Ollama. "
        "Baixe com `ollama pull modelo-caseiro`."
    )


def erro_desconhecido() -> ProviderError:
    return ProviderError("aconteceu algo que ninguém catalogou ainda.")


# --- montagem da execução -------------------------------------------------


def candidato(registro: AiConfig, modelo_id: str, provider_id: str) -> Candidato:
    modelo = registro.modelo(modelo_id)
    provider = registro.provider(provider_id)
    assert modelo is not None and provider is not None
    return Candidato(modelo=modelo, provider=provider)


def decisao(registro: AiConfig, *pares: tuple[str, str]) -> Decisao:
    """Uma cadeia explícita, na ordem que o teste quer exercitar."""
    return Decisao(
        candidatos=tuple(candidato(registro, m, p) for m, p in pares),
        modo="auto",
        motivo="cadeia montada pelo teste",
    )


def fabrica(roteiro: dict[str, ProvedorRoteirizado]) -> Callable[[Candidato], FakeProvider]:
    """Provider por id declarado. Ausente do roteiro = não configurado."""

    def montar(candidato: Candidato) -> FakeProvider:
        provedor = roteiro.get(candidato.provider_id)
        if provedor is None:
            raise ProviderNotConfigured(
                f"O provider {candidato.provider_id!r} não tem chave no ambiente."
            )
        return provedor

    return montar


def pedido(texto: str = PERGUNTA) -> AIRequest:
    return AIRequest(messages=[Message(role="user", content=texto)], system="instrução de teste")


def executar(
    runner: Runner, decidido: Decisao, *, texto: str = PERGUNTA
) -> tuple[str, object]:
    """Consome o stream inteiro e devolve o texto emitido mais a execução."""
    execucao = runner.executar(decidido, pedido(texto), task_type="coding")
    emitido = "".join(execucao.stream())
    return emitido, execucao


def linhas(session: Session, correlation_id: str) -> list[AiRun]:
    return RunRepository(session).list_for(correlation_id)


# --- 1. a cadeia anda: timeout -> erro -> sucesso -------------------------


class TestCadeiaQueAnda:
    def test_timeout_depois_erro_depois_sucesso_grava_tres_linhas(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        roteiro = {
            "caseiro": ProvedorRoteirizado("caseiro", erro=erro_de_timeout()),
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_5xx()),
            "nuvem-b": ProvedorRoteirizado(
                "nuvem-b", resposta="a resposta que chegou", tokens=(300, 120)
            ),
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        emitido, execucao = executar(
            runner,
            decisao(
                registro,
                ("local-codigo", "caseiro"),
                ("rapido", "nuvem-a"),
                ("reserva", "nuvem-b"),
            ),
        )

        assert "a resposta que chegou" in emitido
        assert execucao.resultado is not None
        assert execucao.resultado.texto.strip() == "a resposta que chegou"
        assert execucao.resultado.provider == "nuvem-b"

        cadeia = linhas(session, execucao.correlation_id)
        assert [linha.attempt for linha in cadeia] == [1, 2, 3]
        assert [linha.provider for linha in cadeia] == ["caseiro", "nuvem-a", "nuvem-b"]
        assert [linha.status for linha in cadeia] == ["timeout", "error", "ok"]
        assert cadeia[-1].status == RunStatus.OK.value
        assert (cadeia[-1].tokens_in, cadeia[-1].tokens_out) == (300, 120)
        assert all(linha.error for linha in cadeia[:2])
        assert cadeia[-1].error is None

    def test_correlation_id_e_o_mesmo_nas_tres_tentativas(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """Sem ele, a cadeia vira três execuções soltas e ninguém as reúne."""
        roteiro = {
            "caseiro": ProvedorRoteirizado("caseiro", erro=erro_de_conexao()),
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_de_modelo_ausente()),
            "nuvem-b": ProvedorRoteirizado("nuvem-b", tokens=(10, 5)),
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(
            runner,
            decisao(
                registro,
                ("local-codigo", "caseiro"),
                ("rapido", "nuvem-a"),
                ("reserva", "nuvem-b"),
            ),
        )

        cadeia = linhas(session, execucao.correlation_id)
        assert len(cadeia) == 3
        assert {linha.correlation_id for linha in cadeia} == {execucao.correlation_id}
        assert {linha.task_type for linha in cadeia} == {"coding"}

    def test_custo_da_tentativa_vem_da_tabela_datada(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """O runner consome `custo.estimar`; não recalcula preço por conta."""
        roteiro = {"nuvem-a": ProvedorRoteirizado("nuvem-a", tokens=(1_000_000, 1_000_000))}
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(runner, decisao(registro, ("rapido", "nuvem-a")))

        linha = linhas(session, execucao.correlation_id)[0]
        # 1M × 1.0 (entrada) + 1M × 2.0 (saída), por milhão de tokens.
        assert linha.estimated_cost == pytest.approx(3.0)
        assert linha.price_date == "2026-09-03"

    def test_modelo_sem_preco_declarado_grava_nulo_e_nao_zero(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        roteiro = {"nuvem-b": ProvedorRoteirizado("nuvem-b", tokens=(100, 50))}
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(runner, decisao(registro, ("reserva", "nuvem-b")))

        linha = linhas(session, execucao.correlation_id)[0]
        assert linha.estimated_cost is None
        assert linha.price_date is None

    def test_tentativa_que_falhou_nao_afirma_ter_custado_zero(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """A chamada pode ter consumido entrada do outro lado; ninguém mediu."""
        roteiro = {
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_5xx()),
            "nuvem-b": ProvedorRoteirizado("nuvem-b", tokens=(10, 5)),
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(
            runner, decisao(registro, ("rapido", "nuvem-a"), ("reserva", "nuvem-b"))
        )

        falhada = linhas(session, execucao.correlation_id)[0]
        assert falhada.estimated_cost is None
        assert (falhada.tokens_in, falhada.tokens_out) == (0, 0)

    def test_a_decisao_do_router_alimenta_o_runner_sem_tradução(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """O que sai de `escolher` entra em `executar` como está."""
        decidido = escolher_modelo(
            Classificacao(
                task_type="coding", complexity=10, privacy="internal", tools_required=False
            ),
            config=registro,
        )
        roteiro = {
            item.provider_id: ProvedorRoteirizado(item.provider_id, tokens=(1, 1))
            for item in decidido.candidatos
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(runner, decidido)

        cadeia = linhas(session, execucao.correlation_id)
        assert len(cadeia) == 1
        assert cadeia[0].provider == decidido.candidatos[0].provider_id
        assert cadeia[0].decision == "auto"


# --- 2. erro não repetível pula de provider, não para a cadeia ------------
#
# Corrigido em 2026-09-04 pela verificação ao vivo da T-14: a DeepSeek estava
# sem saldo (402) e o Kimi, saudável, nunca chegou a ser tentado — a cadeia
# parava no primeiro erro de configuração, mesmo com outro provider logo
# depois. `repetivel` decide se vale a pena tentar o MESMO provider de novo;
# `_fila()` já nunca repete provider (REQ-09), então "não repetível" nunca
# deveria significar "para tudo" — só "não insista com este endereço".
# Quem para a cadeia inteira é `_exigir_orcamento()`, que roda antes de
# qualquer tentativa: aquele é limite nosso, não falha de um provider.


class TestErroNaoRepetivelPulaDeProvider:
    def test_chave_invalida_avanca_para_o_proximo_provider(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        seguinte = ProvedorRoteirizado("nuvem-b")
        roteiro = {
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_de_chave()),
            "nuvem-b": seguinte,
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))
        execucao = runner.executar(
            decisao(registro, ("rapido", "nuvem-a"), ("reserva", "nuvem-b")),
            pedido(),
            task_type="coding",
        )

        resposta = "".join(execucao.stream())

        assert resposta
        assert seguinte.chamadas == 1

        cadeia = linhas(session, execucao.correlation_id)
        assert len(cadeia) == 2
        assert cadeia[0].status == RunStatus.ERROR.value
        assert cadeia[1].status == RunStatus.OK.value

    def test_chave_invalida_sem_segundo_provider_esgota_a_cadeia(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """Sem candidato depois, o comportamento de esgotar continua o mesmo."""
        roteiro = {"nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_de_chave())}
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))
        execucao = runner.executar(
            decisao(registro, ("rapido", "nuvem-a")), pedido(), task_type="coding"
        )

        with pytest.raises(CadeiaEsgotada) as capturado:
            "".join(execucao.stream())

        assert "1 tentativa." in capturado.value.message
        assert "chave de API" in capturado.value.message

        cadeia = linhas(session, execucao.correlation_id)
        assert len(cadeia) == 1
        assert cadeia[0].status == RunStatus.ERROR.value

    def test_erro_desconhecido_tambem_avanca_para_o_proximo_provider(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """Errar para o lado de não gastar é não insistir no MESMO provider —
        não é recusar um provider saudável só porque outro falhou antes."""
        seguinte = ProvedorRoteirizado("nuvem-b")
        roteiro = {
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_desconhecido()),
            "nuvem-b": seguinte,
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))
        execucao = runner.executar(
            decisao(registro, ("rapido", "nuvem-a"), ("reserva", "nuvem-b")),
            pedido(),
            task_type="coding",
        )

        resposta = "".join(execucao.stream())

        assert resposta
        assert seguinte.chamadas == 1
        assert len(linhas(session, execucao.correlation_id)) == 2

    def test_nenhum_provider_e_tentado_duas_vezes_mesmo_com_erro_nao_repetivel(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """A garantia que segue intocada: `_fila()` não repete provider,
        erro repetível ou não. `rapido` e `irmao` são dois modelos do MESMO
        provider (`nuvem-a`) — só o primeiro candidato chega a ser chamado."""
        unico = ProvedorRoteirizado("nuvem-a", erro=erro_de_chave())
        runner = Runner(
            session, settings, config=registro, fabrica=fabrica({"nuvem-a": unico})
        )
        execucao = runner.executar(
            decisao(registro, ("rapido", "nuvem-a"), ("irmao", "nuvem-a")),
            pedido(),
            task_type="coding",
        )

        with pytest.raises(CadeiaEsgotada):
            "".join(execucao.stream())

        assert unico.chamadas == 1
        assert len(linhas(session, execucao.correlation_id)) == 1

    def test_cadeia_esgotada_da_erro_unico_com_contagem_e_motivo(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        roteiro = {
            "caseiro": ProvedorRoteirizado("caseiro", erro=erro_de_timeout()),
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_5xx()),
            "nuvem-b": ProvedorRoteirizado(
                "nuvem-b", erro=erro_5xx("o último caiu também")
            ),
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))
        execucao = runner.executar(
            decisao(
                registro,
                ("local-codigo", "caseiro"),
                ("rapido", "nuvem-a"),
                ("reserva", "nuvem-b"),
            ),
            pedido(),
            task_type="coding",
        )

        with pytest.raises(CadeiaEsgotada) as capturado:
            "".join(execucao.stream())

        mensagem = capturado.value.message
        assert "3 tentativas" in mensagem
        assert "o último caiu também" in mensagem
        assert len(linhas(session, execucao.correlation_id)) == 3

    def test_teto_de_tentativas_encerra_a_cadeia(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        terceiro = ProvedorRoteirizado("nuvem-b")
        roteiro = {
            "caseiro": ProvedorRoteirizado("caseiro", erro=erro_de_timeout()),
            "nuvem-a": ProvedorRoteirizado("nuvem-a", erro=erro_5xx()),
            "nuvem-b": terceiro,
        }
        runner = Runner(
            session,
            settings.model_copy(update={"ai_max_attempts": 2}),
            config=registro,
            fabrica=fabrica(roteiro),
        )
        execucao = runner.executar(
            decisao(
                registro,
                ("local-codigo", "caseiro"),
                ("rapido", "nuvem-a"),
                ("reserva", "nuvem-b"),
            ),
            pedido(),
            task_type="coding",
        )

        with pytest.raises(CadeiaEsgotada) as capturado:
            "".join(execucao.stream())

        assert terceiro.chamadas == 0
        assert "2 tentativas" in capturado.value.message
        assert len(linhas(session, execucao.correlation_id)) == 2

    def test_recusa_do_router_nao_vira_tentativa(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """Recusa por política não é falha de provedor: não há o que tentar."""
        recusada = Decisao(
            candidatos=(),
            modo="auto",
            motivo="pergunta local sem modelo local",
            recusa="Esta pergunta está marcada para não sair desta máquina.",
        )
        runner = Runner(session, settings, config=registro, fabrica=fabrica({}))

        with pytest.raises(PerguntaRecusada) as capturado:
            runner.executar(recusada, pedido(), task_type="coding")

        assert "não sair desta máquina" in capturado.value.message

    def test_cadeia_vazia_e_ausencia_de_catalogo_nao_recusa(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        vazia = Decisao(candidatos=(), modo="auto", motivo="o registro não oferece modelo")
        runner = Runner(session, settings, config=registro, fabrica=fabrica({}))

        with pytest.raises(SemCandidato):
            runner.executar(vazia, pedido(), task_type="coding")

    def test_todos_sem_chave_no_ambiente_termina_sem_tentativa(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """Provider não configurado sai do fallback, e não vira linha de falha."""
        runner = Runner(session, settings, config=registro, fabrica=fabrica({}))
        execucao = runner.executar(
            decisao(registro, ("rapido", "nuvem-a"), ("reserva", "nuvem-b")),
            pedido(),
            task_type="coding",
        )

        with pytest.raises(CadeiaEsgotada) as capturado:
            "".join(execucao.stream())

        assert "chave" in capturado.value.message
        assert linhas(session, execucao.correlation_id) == []


# --- 3. nenhum provider duas vezes ----------------------------------------


class TestProviderUmaVezSo:
    def test_provider_repetido_na_cadeia_e_tentado_uma_vez_so(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        """Dois modelos do mesmo provider: quem caiu não melhora no segundo."""
        nuvem_a = ProvedorRoteirizado("nuvem-a", erro=erro_5xx())
        roteiro = {"nuvem-a": nuvem_a, "nuvem-b": ProvedorRoteirizado("nuvem-b", tokens=(1, 1))}
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(
            runner,
            decisao(
                registro,
                ("rapido", "nuvem-a"),
                ("irmao", "nuvem-a"),
                ("reserva", "nuvem-b"),
            ),
        )

        assert nuvem_a.chamadas == 1
        cadeia = linhas(session, execucao.correlation_id)
        assert [linha.provider for linha in cadeia] == ["nuvem-a", "nuvem-b"]
        assert [linha.attempt for linha in cadeia] == [1, 2]


# --- 4. o que é erro repetível (a lista explícita do REQ-09) --------------


class TestClassificacaoDeErro:
    @pytest.mark.parametrize(
        ("erro", "repetivel", "status"),
        [
            (erro_de_timeout(), True, RunStatus.TIMEOUT),
            (erro_de_conexao(), True, RunStatus.ERROR),
            (erro_5xx(), True, RunStatus.ERROR),
            (ProviderError("O provedor respondeu 429. calma aí"), True, RunStatus.ERROR),
            (erro_de_modelo_ausente(), True, RunStatus.ERROR),
            (erro_de_chave(), False, RunStatus.ERROR),
            (ProviderError("O provedor respondeu 400. pedido malformado"), False, RunStatus.ERROR),
            (erro_desconhecido(), False, RunStatus.ERROR),
        ],
    )
    def test_a_tabela_de_erro_repetivel(
        self, erro: Exception, repetivel: bool, status: RunStatus
    ) -> None:
        falha = classificar_erro(erro)
        assert falha.repetivel is repetivel
        assert falha.status is status

    def test_erro_de_dominio_que_nao_e_do_provedor_nao_repete(self) -> None:
        """Orçamento estourado e recusa por política param a cadeia (REQ-09)."""

        class Estourado(Exception):
            code = "AI_BUDGET_EXCEEDED"

        assert classificar_erro(Estourado("o orçamento do dia acabou")).repetivel is False

    def test_timeout_de_transporte_e_reconhecido_pelo_tipo(self) -> None:
        """Frase pode mudar; o tipo do `httpx` não."""
        erro = ProviderError("o provedor não devolveu nada")
        erro.__cause__ = httpx.ReadTimeout("read timeout")

        falha = classificar_erro(erro)
        assert falha.repetivel is True
        assert falha.status is RunStatus.TIMEOUT

    def test_o_que_vai_para_o_banco_e_frase_de_catalogo_e_o_resto_vem_mascarado(
        self,
    ) -> None:
        """`motivo` é escrito por nós; a fala do provedor fica só no `detalhe`."""
        falha = classificar_erro(
            ProviderError("O provedor respondeu 500. {'api_key': 'sk-teste-abcdefghijklmnop'}")
        )

        assert falha.motivo == "o provedor respondeu 500"
        assert "sk-teste" not in falha.detalhe
        assert "[REDIGIDO]" in falha.detalhe


# --- 5. o texto interrompido não vira resposta boa ------------------------


class TestStreamInterrompido:
    def test_texto_parcial_de_tentativa_que_caiu_nao_entra_no_resultado(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        roteiro = {
            "nuvem-a": ProvedorRoteirizado(
                "nuvem-a",
                resposta="começo que nao terminou",
                erro=erro_5xx(),
                pedacos_antes=2,
            ),
            "nuvem-b": ProvedorRoteirizado(
                "nuvem-b", resposta="a resposta inteira", tokens=(5, 5)
            ),
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        emitido, execucao = executar(
            runner, decisao(registro, ("rapido", "nuvem-a"), ("reserva", "nuvem-b"))
        )

        assert execucao.resultado is not None
        assert execucao.resultado.texto.strip() == "a resposta inteira"
        # Na tela o pedaço já saiu — e sai acompanhado da explicação, em vez de
        # emendar duas respostas diferentes como se fossem uma.
        assert "começo que" in emitido
        assert "resposta interrompida" in emitido


# --- 6. o banco não fica travado durante a resposta (risco 1 do plano) ----


class TestBancoLivreDuranteOStream:
    def test_escrita_do_painel_funciona_durante_um_stream_em_curso(
        self, session: Session, session_factory, settings: Settings, registro: AiConfig
    ) -> None:  # type: ignore[no-untyped-def]
        """A regressão da Fase 3 (`fbabea1`), agora com teste.

        Enquanto a resposta corre, o painel continua sendo um painel: o poller
        grava um ciclo, alguém fixa um projeto. Se o runner segurasse a
        transação, essas escritas voltariam `database is locked` — e o erro
        apareceria longe da IA, que é o que tornou o caso caro de achar.
        """
        roteiro = {"nuvem-a": ProvedorRoteirizado("nuvem-a", resposta="um dois", tokens=(9, 9))}
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))
        execucao = runner.executar(
            decisao(registro, ("rapido", "nuvem-a")), pedido(), task_type="coding"
        )

        fluxo = execucao.stream()
        assert next(fluxo).strip() == "um"

        # A prova direta: no meio da resposta, a sessão do runner não tem
        # transação aberta nem objeto pendurado esperando `flush`.
        assert not session.in_transaction()
        assert len(session.new) == 0

        painel = session_factory()
        # Sem esperar os 15 s de `busy_timeout`: o que interessa é que a escrita
        # passe **agora**, não que ela sobreviva a uma fila.
        painel.execute(text("PRAGMA busy_timeout=250"))
        comeco = time.monotonic()
        painel.add(Project(id="p-durante", name="Painel", path="/tmp/p-durante"))
        painel.commit()
        gasto = time.monotonic() - comeco
        painel.close()

        assert gasto < 2.0

        resto = "".join(fluxo)
        assert "dois" in resto

        cadeia = linhas(session, execucao.correlation_id)
        assert [linha.status for linha in cadeia] == ["ok"]

    def test_transacao_aberta_durante_o_stream_travaria_a_escrita_do_painel(
        self, session: Session, session_factory
    ) -> None:  # type: ignore[no-untyped-def]
        """O teste acima só vale se o erro que ele nega for possível.

        Aqui está o anti-padrão de `fbabea1` reproduzido de propósito: uma
        escrita com `flush` e sem `commit`, como ficaria se o runner gravasse a
        tentativa durante o stream. A escrita do painel falha.
        """
        segurando = session_factory()
        segurando.add(
            AiRun(
                correlation_id="c-travado",
                attempt=1,
                provider="nuvem-a",
                model="rapido",
                task_type="coding",
                decision="auto",
                status=RunStatus.OK.value,
            )
        )
        segurando.flush()  # sem commit: a transação fica aberta, como antes

        painel = session_factory()
        painel.execute(text("PRAGMA busy_timeout=250"))
        try:
            painel.add(Project(id="p-travado", name="Painel", path="/tmp/p-travado"))
            with pytest.raises(OperationalError, match="locked"):
                painel.commit()
        finally:
            painel.rollback()
            painel.close()
            segurando.rollback()
            segurando.close()


# --- 7. prompt e resposta não entram na linha (REQ-10) --------------------


class TestSemConteudoDeConversa:
    def test_varredura_das_linhas_nao_encontra_trecho_do_prompt(
        self, session: Session, settings: Settings, registro: AiConfig
    ) -> None:
        roteiro = {
            "nuvem-a": ProvedorRoteirizado(
                "nuvem-a",
                # O provedor devolve o erro ecoando o pedido, que é como um
                # trecho do prompt chegaria à coluna `error`.
                erro=erro_5xx(f"não entendi: {PERGUNTA} (chave sk-teste-abcdefghijklmnop)"),
            ),
            "nuvem-b": ProvedorRoteirizado(
                "nuvem-b", resposta="segredo comercial revelado", tokens=(10, 10)
            ),
        }
        runner = Runner(session, settings, config=registro, fabrica=fabrica(roteiro))

        _, execucao = executar(
            runner, decisao(registro, ("rapido", "nuvem-a"), ("reserva", "nuvem-b"))
        )

        cadeia = linhas(session, execucao.correlation_id)
        assert len(cadeia) == 2

        gravado = " ".join(
            str(getattr(linha, coluna.name))
            for linha in cadeia
            for coluna in AiRun.__table__.columns
        ).lower()

        for trecho in TRECHOS_DO_PROMPT:
            assert trecho not in gravado, (
                f"trecho do prompt gravado em ai_run: {trecho!r}. "
                "REQ-10: a linha de tentativa não guarda conteúdo de conversa."
            )
        assert "segredo comercial revelado" not in gravado
        assert "sk-teste" not in gravado
