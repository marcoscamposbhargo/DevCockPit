"""A cadeia de tentativas: quem tenta, quem tenta depois, e o que fica registrado.

O router (`model_router.escolher`) devolve uma fila ordenada de candidatos. Este
módulo é quem a percorre: tenta de cima para baixo, para no primeiro sucesso,
mede cada tentativa e grava uma linha por tentativa em `ai_run` (REQ-09,
REQ-10).

Três decisões mandam aqui, e nenhuma delas se defende sozinha lendo o código:

**1. Erro repetível é lista explícita, nunca `except Exception`.** Repetem
timeout, erro de conexão, 5xx, 429 e "modelo não encontrado" — situações em que
o próximo candidato tem chance real de responder. Não repetem 401 e 403 (a
chave não melhora na segunda tentativa), orçamento estourado e recusa por
política. **Erro desconhecido não repete**: a partir deste ciclo cada tentativa
custa dinheiro, e errar para o lado de tentar de novo gasta em cima de um
defeito que ninguém entendeu ainda.

**2. Nenhum provider é tentado duas vezes na mesma execução** (REQ-09), mesmo
que apareça duas vezes na fila servindo modelos diferentes. Se ele acabou de
recusar a chave ou de não atender, o segundo modelo dele cai no mesmo lugar.

**3. As tentativas são acumuladas em memória e gravadas em transação curta e
própria, depois de o stream fechar.** Este é o ponto que já quebrou o painel: na
Fase 3 (`fbabea1`) o repositório de mensagens só dava `flush`, a transação ficava
aberta durante os minutos inteiros da resposta, e o SQLite — que admite um
escritor por vez — devolvia `database is locked` em botão sem nenhuma relação
com a IA, longe da causa. Enquanto o stream corre, este módulo não toca na
sessão. Nada de `add`, nada de `flush`. O que ele tem a dizer sobre a tentativa
fica numa lista de `Tentativa`, e vira linha depois, num `add_all` seguido de
`commit`.

Uma ausência de propósito: **candidato que a cadeia não chegou a tentar não vira
linha `skipped`.** A tabela tem o status, mas gravá-lo aqui daria, em toda
pergunta respondida de primeira, linhas com `attempt > 1` — e é exatamente
assim que o agregado do REQ-12 conta fallback (`RunRepository.aggregate`). A
tela passaria a anunciar fallback em pergunta que nunca precisou de nenhum.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.ai_run import AiRun, RunStatus
from app.repositories.ai_repository import RunRepository
from app.services.ai.custo import NAO_MEDIDO, CustoEstimado, estimar
from app.services.ai.model_router import Candidato, Decisao
from app.services.ai.providers import (
    AIProvider,
    AIRequest,
    ProviderNotConfigured,
    construir_provider,
)
from app.services.ai.redaction import redigir
from app.services.ai.registry import AiConfig, get_ai_config

logger = logging.getLogger(__name__)

#: Teto da mensagem gravada em `ai_run.error`. A coluna é `Text`, mas o registro
#: existe para explicar a tentativa, não para arquivar o corpo da resposta do
#: provedor — que já vem cortado em 200 caracteres pelo próprio provider.
LIMITE_DA_MENSAGEM = 500


class PerguntaRecusada(DomainError):
    """A pergunta não pode ir para nenhum candidato (REQ-07, item 1).

    Separada de `SemCandidato` porque as duas pedem coisas diferentes de quem
    chama: aqui, **não** há caminho alternativo. Cair no provider do `.env`
    depois desta recusa mandaria para a nuvem exatamente o que a marca de
    privacidade proíbe.
    """

    code = "AI_REFUSED"
    status_code = 409
    default_message = "Esta pergunta não pode ser enviada a nenhum modelo disponível."


class SemCandidato(DomainError):
    """O registro não oferece modelo para esta pergunta.

    Não é recusa: é ausência de catálogo — instalação sem `configs/ai.yml`, ou
    com todos os providers desligados. Quem chama pode seguir pelo provider do
    `.env`, como antes deste ciclo (REQ-04).
    """

    code = "AI_NO_CANDIDATE"
    status_code = 409
    default_message = "O registro de IA não oferece modelo para esta pergunta."


class CadeiaEsgotada(DomainError):
    """Erro único do fim da cadeia: quantas tentativas houve e o motivo da última.

    Um erro por tentativa faria a pessoa ler três mensagens para descobrir que
    a IA está fora do ar. A borda do spec pede uma só, e que ela diga o número.
    """

    code = "AI_CHAIN_EXHAUSTED"
    status_code = 502
    default_message = "Nenhum provedor da cadeia respondeu."


# --- o que é erro repetível (REQ-09) --------------------------------------
#
# A lista é explícita, e é curta de propósito: o que não estiver descrito aqui
# termina a cadeia. Cada linha abaixo responde "por que vale a pena tentar o
# próximo candidato com este erro?" — quem não responde, não entra.

#: Códigos de erro de domínio que encerram a cadeia na hora. Comparados pelo
#: atributo `code`, e não pela classe, para o runner não importar `chat_service`
#: — que vai importar o runner (T-12), e o ciclo de import fecharia.
CODIGOS_QUE_NAO_REPETEM = frozenset(
    {
        "AI_BUDGET_EXCEEDED",  # orçamento não é falha de provedor
        "AI_REFUSED",  # recusa por política
        "AI_DISABLED",
        "AI_NOT_CONFIGURED",
        "VALIDATION_ERROR",
    }
)

#: Status HTTP que valem uma nova tentativa em outro candidato. O que não está
#: aqui — 400, 401, 403, 413, 422 — é defeito do pedido ou da credencial, e o
#: próximo provedor devolveria o mesmo.
CODIGOS_HTTP_REPETIVEIS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})

#: O provider já traduz o status HTTP em frase antes de levantar
#: (`_HttpProvider._explicar`), então a frase é o que chega aqui na maioria dos
#: casos. Cada linha traz o motivo **canônico** — a frase curta que vai para
#: `ai_run.error`, escrita por nós. Ordem importa: a primeira que casar decide.
ASSINATURAS: tuple[tuple[re.Pattern[str], str, RunStatus, bool], ...] = (
    # 401/403. Repetir com a mesma chave em outro modelo do mesmo formato só
    # gastaria uma ida à rede para receber a mesma recusa.
    (
        re.compile(r"recusou a chave|chave de API inválida|unauthorized|forbidden", re.I),
        "o provedor recusou a chave de API",
        RunStatus.ERROR,
        False,
    ),
    # Timeout. O candidato seguinte costuma ser justamente o mais rápido.
    (
        re.compile(r"tempo esgotad|não respondeu a tempo|timed? ?out", re.I),
        "o provedor não respondeu a tempo",
        RunStatus.TIMEOUT,
        True,
    ),
    # 429: excesso de requisições neste provedor, não em todos.
    (
        re.compile(r"excesso de requisi|rate.?limit", re.I),
        "o provedor recusou por excesso de requisições",
        RunStatus.ERROR,
        True,
    ),
    # Modelo ausente — o caso mais comum nesta máquina, com o Ollama de pé e o
    # modelo não baixado. É falha de catálogo, e outro candidato responde.
    (
        re.compile(r"não encontrad|não está instalado|not found", re.I),
        "o modelo não está disponível neste provedor",
        RunStatus.ERROR,
        True,
    ),
)

#: `_HttpProvider._explicar` monta "O provedor respondeu 503. ..." quando não
#: tem frase própria para o status. É por aqui que 5xx entra na lista.
CODIGO_NA_MENSAGEM = re.compile(r"respondeu (\d{3})")

#: O que um provedor tem permissão de levantar. Qualquer outra exceção é defeito
#: nosso e sobe inteira: transformar `AttributeError` em fallback esconderia o
#: bug e ainda pagaria por uma segunda chamada para descobrir o mesmo.
ERROS_DE_PROVEDOR = (DomainError, httpx.HTTPError)

#: Dito ao usuário quando a cadeia recomeça depois de já ter emitido texto. O
#: pedaço já enviado não pode ser desfeito na tela, mas pode — e deve — ser
#: explicado, senão duas respostas diferentes aparecem coladas como se fossem
#: uma. O texto descartado não entra em `Resultado.texto`.
MARCA_DE_RECOMECO = "\n\n_(resposta interrompida: {motivo}. Recomeçando com outro modelo.)_\n\n"


@dataclass(frozen=True)
class Falha:
    """Como a tentativa terminou, e se vale tentar o próximo candidato.

    Os dois textos existem separados porque têm destinos com regras diferentes.
    `motivo` é frase de catálogo, escrita aqui, e é a única que vai para
    `ai_run.error`: a mensagem do provedor costuma ecoar o pedido, e um provedor
    que devolve "não entendi: <o pedido inteiro>" levaria o prompt para dentro
    da tabela que o REQ-10 proíbe de guardar conversa. `detalhe` é a mensagem
    dele, mascarada, e vai só para a pessoa ler e para o log — nunca para o
    banco.
    """

    #: Frase de catálogo. É o que `ai_run.error` guarda.
    motivo: str
    #: A mensagem do provedor, já mascarada (**P-05**) e cortada. Não é gravada.
    detalhe: str
    status: RunStatus
    repetivel: bool


def classificar_erro(erro: BaseException) -> Falha:
    """Traduz a exceção do provedor na decisão de repetir, ou não.

    A ordem das perguntas é a ordem da certeza: código de domínio primeiro (é
    declaração nossa), depois a frase que o provider escreveu, depois o status
    HTTP embutido nela, e só então o tipo de exceção de rede. Nada casou: não
    repete.
    """
    detalhe = redigir(str(erro) or type(erro).__name__)[:LIMITE_DA_MENSAGEM]

    codigo = str(getattr(erro, "code", "") or "")
    if codigo in CODIGOS_QUE_NAO_REPETEM:
        return Falha(f"interrompido por {codigo}", detalhe, RunStatus.ERROR, False)

    for padrao, motivo, status, repetivel in ASSINATURAS:
        if padrao.search(detalhe):
            return Falha(motivo, detalhe, status, repetivel)

    achado = CODIGO_NA_MENSAGEM.search(detalhe)
    if achado is not None:
        status_http = int(achado.group(1))
        return Falha(
            f"o provedor respondeu {status_http}",
            detalhe,
            RunStatus.ERROR,
            status_http in CODIGOS_HTTP_REPETIVEIS,
        )

    rede = _falha_de_rede(erro, detalhe)
    if rede is not None:
        return rede

    # Desconhecido. O tipo da exceção é o que sobra de catalogado, e é por ele
    # que se procura o defeito no log; a cadeia para aqui.
    return Falha(
        f"erro não catalogado do provedor ({type(erro).__name__})",
        detalhe,
        RunStatus.ERROR,
        False,
    )


def _falha_de_rede(erro: BaseException, detalhe: str) -> Falha | None:
    """Procura um erro do `httpx` na cadeia de causas.

    O provider embrulha o erro de transporte (`raise ProviderError(...) from
    erro`), então o tipo original continua alcançável — e ele é mais confiável
    que qualquer frase, porque não depende de tradução.
    """
    for causa in _cadeia_de_causas(erro):
        # Timeout antes de `HTTPError`: `TimeoutException` é subclasse dele, e
        # a ordem contrária gravaria todo timeout como erro genérico.
        if isinstance(causa, httpx.TimeoutException):
            return Falha("tempo esgotado ao falar com o provedor", detalhe, RunStatus.TIMEOUT, True)
        if isinstance(causa, httpx.HTTPError):
            return Falha("falha de conexão com o provedor", detalhe, RunStatus.ERROR, True)
    return None


def _cadeia_de_causas(erro: BaseException) -> Iterator[BaseException]:
    """A exceção e o que a causou, sem entrar em laço se o encadeamento voltar."""
    vistos: set[int] = set()
    atual: BaseException | None = erro
    while atual is not None and id(atual) not in vistos:
        vistos.add(id(atual))
        yield atual
        atual = atual.__cause__ or atual.__context__


# --- o que fica registrado ------------------------------------------------


@dataclass
class Tentativa:
    """Uma tentativa, ainda em memória. Vira linha de `ai_run` no fim (REQ-10).

    Não há campo de prompt nem de resposta, pelo mesmo motivo que a tabela não
    tem coluna para eles: o conteúdo da conversa vive em `ai_message`, e repetir
    o texto do usuário aqui o espalharia por mais um lugar sem ganho nenhum de
    diagnóstico.
    """

    numero: int
    provider: str
    #: O id lógico do registro, não o nome do modelo no fornecedor: é por ele
    #: que a tabela de preço indexa, e corrigir o nome real do fornecedor não
    #: pode mudar o significado do histórico.
    modelo: str
    status: RunStatus
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    custo: CustoEstimado = NAO_MEDIDO
    #: Mensagem já mascarada. Vazia quando a tentativa deu certo.
    erro: str = ""

    @property
    def falhou(self) -> bool:
        return self.status is not RunStatus.OK

    def para_linha(self, correlation_id: str, task_type: str, decision: str) -> AiRun:
        return AiRun(
            correlation_id=correlation_id,
            attempt=self.numero,
            provider=self.provider,
            model=self.modelo,
            task_type=task_type,
            decision=decision,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            latency_ms=self.latency_ms,
            status=self.status.value,
            estimated_cost=self.custo.valor,
            price_date=self.custo.price_date,
            error=self.erro or None,
        )


@dataclass
class Resultado:
    """A resposta que chegou, e a cadeia inteira que levou até ela."""

    texto: str
    provider: str
    #: Id lógico do modelo, o mesmo que a linha de `ai_run` guarda.
    modelo: str
    #: Nome do modelo no fornecedor, para a tela dizer quem respondeu.
    modelo_real: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    custo: CustoEstimado
    correlation_id: str
    tentativas: tuple[Tentativa, ...] = ()

    @property
    def houve_fallback(self) -> bool:
        return len(self.tentativas) > 1


# --- o runner -------------------------------------------------------------
#
# A construção do provedor a partir de um `Candidato` do registro
# (`construir_provider`, e o dicionário `FORMATOS_POR_PROVIDER` que ela usa)
# mora em `providers.py`, ao lado de `build_provider` — a mesma
# responsabilidade (config/candidato -> cliente `AIProvider`), só que a partir
# de fontes diferentes (`.env` vs. `configs/ai.yml`). Nasceu aqui na T-09
# porque a T-02 fechou antes de o registro (T-01) existir; a T-09 seguinte
# alinhou o código ao plano.


class Runner:
    """Percorre a cadeia de candidatos e registra o que aconteceu.

    Vive fora do `chat_service` de propósito: o fallback precisa valer para
    qualquer chamada ao modelo, e amarrá-lo à conversa o tornaria intestável
    sem subir rota e sessão.
    """

    def __init__(
        self,
        session: Session,
        settings,  # type: ignore[no-untyped-def]
        config: AiConfig | None = None,
        fabrica: Callable[[Candidato], AIProvider] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.config = config if config is not None else get_ai_config()
        #: Como um candidato vira cliente. Injetável para o teste rodar a cadeia
        #: inteira sem rede e sem chave (**P-06**).
        self.fabrica = fabrica or (lambda candidato: construir_provider(candidato, settings))

    @property
    def max_tentativas(self) -> int:
        """Teto da cadeia. Existe para ela terminar mesmo com muitos modelos."""
        return max(1, int(getattr(self.settings, "ai_max_attempts", 3) or 1))

    def executar(
        self,
        decisao: Decisao,
        pedido: AIRequest,
        *,
        task_type: str = "qa",
        correlation_id: str = "",
    ) -> Execucao:
        """Prepara a execução da decisão do router. Não fala com ninguém ainda.

        As duas recusas acontecem aqui, antes de qualquer byte sair: quem chama
        precisa saber que não há tentativa a fazer **antes** de começar a
        transmitir resposta para a tela.
        """
        if decisao.recusada:
            raise PerguntaRecusada(decisao.recusa)
        if not decisao.candidatos:
            raise SemCandidato(
                f"{decisao.motivo}. Declare o modelo em configs/ai.yml, ou "
                "habilite um provider que o sirva."
            )
        return Execucao(
            runner=self,
            decisao=decisao,
            pedido=pedido,
            task_type=task_type,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )


@dataclass
class Execucao:
    """Uma pergunta percorrendo a cadeia. Consumível uma vez.

    O objeto existe para separar duas coisas que um gerador sozinho não separa:
    o texto que vai saindo (que quem chama repassa à tela) e o que ficou sabido
    no fim (tokens, custo, quem respondeu). Quem chama faz:

        execucao = runner.executar(decisao, pedido, task_type=tipo)
        for pedaco in execucao.stream():
            yield pedaco
        resultado = execucao.resultado
    """

    runner: Runner
    decisao: Decisao
    pedido: AIRequest
    task_type: str
    correlation_id: str

    tentativas: list[Tentativa] = field(default_factory=list)
    resultado: Resultado | None = None
    _consumida: bool = False

    def stream(self) -> Iterator[str]:
        """Percorre a cadeia emitindo o texto do candidato que responder.

        A gravação fica no `finally`, e não depois do laço, porque o consumidor
        pode desistir no meio (a pessoa fecha a aba, o SSE cai) — e uma
        tentativa que aconteceu precisa constar mesmo assim.
        """
        if self._consumida:
            raise RuntimeError("Esta execução já foi consumida; peça outra ao runner.")
        self._consumida = True
        try:
            yield from self._percorrer()
        finally:
            self._gravar()

    # --- a cadeia ---------------------------------------------------------

    def _percorrer(self) -> Iterator[str]:
        ultima: Falha | None = None

        for candidato in self._fila():
            if len(self.tentativas) >= self.runner.max_tentativas:
                logger.info(
                    "cadeia interrompida pelo teto de tentativas",
                    extra={
                        "extra_fields": {
                            "correlation_id": self.correlation_id,
                            "max_attempts": self.runner.max_tentativas,
                        }
                    },
                )
                break

            provedor = self._provedor(candidato)
            if provedor is None:
                continue

            comeco = time.monotonic()
            partes: list[str] = []
            try:
                for pedaco in provedor.stream(self.pedido):
                    partes.append(pedaco)
                    yield pedaco
            except ERROS_DE_PROVEDOR as erro:
                ultima = classificar_erro(erro)
                self._registrar_falha(candidato, ultima, comeco)
                if not ultima.repetivel:
                    raise self._esgotada(ultima) from erro
                if partes:
                    # Texto já entregue de uma resposta que não terminou. Ele
                    # não vira `Resultado.texto` — mas está na tela, e emendar
                    # a próxima resposta nele sem avisar seria apresentar duas
                    # respostas como se fossem uma.
                    yield MARCA_DE_RECOMECO.format(motivo=ultima.motivo)
                continue

            self._registrar_sucesso(candidato, "".join(partes), provedor, comeco)
            return

        raise self._esgotada(ultima)

    def _fila(self) -> Iterator[Candidato]:
        """Os candidatos, sem repetir provider (REQ-09).

        O corte é pelo provider, não pelo par modelo × provider: quem acabou de
        recusar a chave, estourar o limite ou não responder devolve o mesmo com
        outro modelo no mesmo endereço.
        """
        vistos: set[str] = set()
        for candidato in self.decisao.candidatos:
            if candidato.provider_id in vistos:
                logger.debug(
                    "candidato ignorado: provider já tentado nesta execução",
                    extra={"extra_fields": {"candidato": str(candidato)}},
                )
                continue
            vistos.add(candidato.provider_id)
            yield candidato

    def _provedor(self, candidato: Candidato) -> AIProvider | None:
        """O cliente do candidato, ou `None` quando ele não está configurado.

        Provider com `api_key_env` apontando para variável ausente é "não
        configurado", e o spec o exclui do roteamento **e do fallback**: não é
        tentativa, não é falha, e não vira linha — só sai da fila.
        """
        try:
            return self.runner.fabrica(candidato)
        except ProviderNotConfigured as erro:
            logger.info(
                "candidato fora da cadeia: provider não configurado",
                extra={
                    "extra_fields": {
                        "candidato": str(candidato),
                        "motivo": redigir(erro.message),
                    }
                },
            )
            return None

    # --- o que cada desfecho registra -------------------------------------

    def _registrar_falha(self, candidato: Candidato, falha: Falha, comeco: float) -> None:
        self.tentativas.append(
            Tentativa(
                numero=len(self.tentativas) + 1,
                provider=candidato.provider_id,
                modelo=candidato.modelo_id,
                status=falha.status,
                latency_ms=self._ms(comeco),
                erro=falha.motivo,
                # Sem custo, e não custo zero: a tentativa pode ter consumido
                # tokens de entrada do outro lado, e ninguém mediu quantos
                # (**P-02**).
                custo=NAO_MEDIDO,
            )
        )

    def _registrar_sucesso(
        self,
        candidato: Candidato,
        texto: str,
        provedor: AIProvider,
        comeco: float,
    ) -> None:
        uso = getattr(provedor, "last_usage", None)
        tokens_in = max(0, int(getattr(uso, "tokens_in", 0) or 0))
        tokens_out = max(0, int(getattr(uso, "tokens_out", 0) or 0))
        # Sem contagem não há o que multiplicar por preço, e um zero com data
        # afirmaria que a chamada foi de graça (**P-02**).
        custo = (
            estimar(candidato.modelo_id, tokens_in, tokens_out, config=self.runner.config)
            if tokens_in or tokens_out
            else NAO_MEDIDO
        )
        latencia = self._ms(comeco)

        self.tentativas.append(
            Tentativa(
                numero=len(self.tentativas) + 1,
                provider=candidato.provider_id,
                modelo=candidato.modelo_id,
                status=RunStatus.OK,
                latency_ms=latencia,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                custo=custo,
            )
        )
        self.resultado = Resultado(
            texto=texto,
            provider=candidato.provider_id,
            modelo=candidato.modelo_id,
            modelo_real=candidato.modelo.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latencia,
            custo=custo,
            correlation_id=self.correlation_id,
            tentativas=tuple(self.tentativas),
        )

    def _esgotada(self, ultima: Falha | None) -> CadeiaEsgotada:
        """O erro único do fim da cadeia, com a contagem e o motivo da última."""
        quantas = len(self.tentativas)
        plural = "s" if quantas != 1 else ""
        if ultima is None:
            return CadeiaEsgotada(
                "Nenhum provedor da cadeia pôde ser chamado: todos os candidatos "
                "estão sem a chave declarada em configs/ai.yml no ambiente."
            )
        # Para a pessoa vale o `detalhe`, que é a frase do provedor com o
        # conserto dentro ("abra o Ollama", "confira a variável X"). O `motivo`
        # canônico é o que fica no banco.
        return CadeiaEsgotada(
            f"A IA não respondeu depois de {quantas} tentativa{plural}. "
            f"Motivo da última: {ultima.detalhe}"
        )

    @staticmethod
    def _ms(comeco: float) -> int:
        return int((time.monotonic() - comeco) * 1000)

    # --- a gravação, em transação curta e própria -------------------------

    def _gravar(self) -> None:
        """Grava a cadeia inteira num `add_all` e fecha a transação na hora.

        Chamado só depois de o stream fechar. É a mitigação do risco 1 do plano:
        com o SQLite admitindo um escritor por vez, uma transação aberta durante
        os minutos de uma resposta local trava toda escrita do painel — e o
        `database is locked` aparece em outro botão, longe da causa
        (`fbabea1`).

        Falhar aqui não pode derrubar a resposta: ela já chegou à pessoa. O
        registro que se perde vira aviso no log, não erro na tela.
        """
        if not self.tentativas:
            return
        try:
            RunRepository(self.runner.session).add_all(
                tentativa.para_linha(self.correlation_id, self.task_type, self.decisao.modo)
                for tentativa in self.tentativas
            )
            self.runner.session.commit()
        except SQLAlchemyError as erro:
            self.runner.session.rollback()
            logger.warning(
                "não consegui gravar as tentativas desta execução",
                extra={
                    "extra_fields": {
                        "correlation_id": self.correlation_id,
                        "erro": str(erro)[:200],
                    }
                },
            )
