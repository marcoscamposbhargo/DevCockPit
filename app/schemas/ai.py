"""Contratos de sessão, memória e briefing do dia."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GitMarkOut(BaseModel):
    branch: str | None = None
    head_sha: str | None = None
    dirty_count: int | None = None
    is_repo: bool = False


class SessionFactsOut(BaseModel):
    """O que o painel observou — e só isso.

    Nada aqui é redigido: são commits, ações e quedas lidos de quem registrou.
    """

    git_start: GitMarkOut = Field(default_factory=GitMarkOut)
    git_end: GitMarkOut | None = None
    commits: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    services_down: list[dict] = Field(default_factory=list)
    duration_minutes: int | None = None


class SessionOut(BaseModel):
    id: str
    project_id: str
    started_at: datetime
    ended_at: datetime | None = None
    objective: str | None = None
    summary: str | None = None
    next_steps: str | None = None
    is_open: bool
    facts: SessionFactsOut = Field(default_factory=SessionFactsOut)


class SessionStart(BaseModel):
    #: Opcional de propósito: obrigar a declarar objetivo antes de começar
    #: transformaria o gesto de abrir numa burocracia, e o registro morreria.
    objective: str | None = Field(default=None, max_length=500)


class SessionEnd(BaseModel):
    #: Vazio faz o painel montar o resumo dos fatos. Preenchido, vale o texto
    #: de quem viveu a sessão — que sabe coisas que nenhum log registra.
    summary: str | None = Field(default=None, max_length=4000)
    next_steps: str | None = Field(default=None, max_length=2000)


class SessionList(BaseModel):
    items: list[SessionOut] = Field(default_factory=list)
    current: SessionOut | None = None
    previous: SessionOut | None = None


class MemoryOut(BaseModel):
    id: int
    project_id: str | None = None
    kind: str
    title: str
    body: str
    #: `observed` | `human` | `ai_suggested` — o que separa registro de palpite.
    source: str
    confirmed: bool
    session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    kind: str = Field(max_length=20)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=8000)
    session_id: str | None = None


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=8000)


class MemoryList(BaseModel):
    items: list[MemoryOut] = Field(default_factory=list)


class TaskOut(BaseModel):
    id: int
    project_id: str
    title: str
    detail: str | None = None
    status: str
    priority: int
    source: str
    session_id: str | None = None
    created_at: datetime
    done_at: datetime | None = None
    is_open: bool


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=4000)
    #: 1 alta, 2 média, 3 baixa.
    priority: int = Field(default=2, ge=1, le=3)
    session_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    detail: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=10)
    priority: int | None = Field(default=None, ge=1, le=3)


class TaskList(BaseModel):
    items: list[TaskOut] = Field(default_factory=list)
    open_count: int = 0


class DayItemOut(BaseModel):
    project_id: str
    name: str
    #: Por que este projeto está nesta posição. A tela explica em vez de só
    #: ordenar: ranking sem motivo é adivinhação com aparência de método.
    reason: str
    next_step: str | None = None
    last_session_at: datetime | None = None
    last_summary: str | None = None
    open_session: bool = False
    dirty_count: int | None = None
    services_online: int = 0
    #: A próxima tarefa aberta deste projeto, quando existir. É o que faz a
    #: tela do dia falar de trabalho concreto, e não só do que a última sessão
    #: deixou escrito.
    next_task: TaskOut | None = None
    open_tasks: int = 0


class BriefingOut(BaseModel):
    generated_at: datetime
    total_projects: int
    open_sessions: list[str] = Field(default_factory=list)
    items: list[DayItemOut] = Field(default_factory=list)
    suggestion: str | None = None


# --- chat -----------------------------------------------------------------


class ModeloEscolhivelOut(BaseModel):
    """Um modelo que a pessoa pode fixar na tela, pelo id lógico do registro."""

    id: str
    #: Nome do modelo no fornecedor. Só para a tela mostrar; nunca volta.
    model: str
    provider: str
    local: bool = False


class AiStatusOut(BaseModel):
    """O que a tela precisa saber antes de oferecer o chat.

    Nunca inclui a chave, nem parte dela: a chave não sai do processo por
    nenhuma rota (defesa D-A5).
    """

    enabled: bool
    configured: bool
    #: Quando não configurado, o que fazer para configurar.
    reason: str | None = None
    provider: str
    model: str
    #: Segundo modelo configurado, ou vazio. A tela só mostra o seletor quando
    #: existe — oferecer escolha entre uma coisa só é ruído.
    model_alt: str = ""
    tokens_today: int = 0
    daily_budget: int = 0
    calls_today: int = 0
    #: Custo estimado do dia em US$, somado de `ai_run`. Só o que passou pelo
    #: registro; o caminho antigo do `.env` não tem preço.
    cost_today: float = 0.0
    #: Teto em US$ por dia. Zero = sem teto em dinheiro.
    daily_cost_budget: float = 0.0
    #: Modelos do registro (`configs/ai.yml`) que a tela pode fixar (REQ-08).
    #: Vazio sem registro — aí vale o seletor antigo de `model`/`model_alt`.
    modelos: list[ModeloEscolhivelOut] = Field(default_factory=list)


class ChatAsk(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    #: Qual dos dois modelos configurados responde: `"default"` (o rápido) ou
    #: `"alt"` (o caprichado). É uma escolha de conjunto fechado, e nunca o
    #: nome de um modelo — o cliente escolhe entre opções que o servidor
    #: definiu, do mesmo jeito que `OpenBrowserRequest` recebe a chave do
    #: serviço e jamais a URL (decisão D-13).
    model: Literal["default", "alt"] = "default"
    #: Id lógico de um modelo do registro (`claude-principal`), ou vazio para o
    #: roteamento automático (REQ-08). Nunca o nome no fornecedor (**P-06**): id
    #: que o registro não conhece cai no automático, sem virar nome cru na API.
    modelo: str = Field(default="", max_length=64, pattern=r"^[a-z0-9._-]*$")
    #: Fixa o especialista. Vazio, a regra escolhe. Como o `model`, é conjunto
    #: fechado: chave de perfil que o servidor conhece, nunca prompt do cliente
    #: — quem manda instrução para o modelo é o servidor (defesa D-A4).
    agent: Literal["devops", "fullstack", "qa"] | None = None


class EspecialistaOut(BaseModel):
    key: str
    label: str
    descricao: str
    #: Ações do registro fechado que a tela mostra como botão para este perfil.
    #: Nada de capacidade nova: são os botões que já existem, reunidos onde a
    #: conversa acontece (defesa D-A3).
    atalhos: list[ProposalOut] = Field(default_factory=list)


class EspecialistaList(BaseModel):
    items: list[EspecialistaOut]
    #: Quem atende quando nada casa e nada foi fixado.
    padrao: str
    #: Versão dos prompts em uso. Vai gravada em cada resposta.
    versao_dos_prompts: str


class ProposeAsk(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    model: Literal["default", "alt"] = "default"


class ProposalOut(BaseModel):
    """Uma ação que a IA propõe — e que só acontece se a pessoa confirmar.

    `path` e `method` apontam para a **mesma rota que o botão usa**. É o que
    materializa a defesa D-A3: a IA não ganha caminho de execução próprio, ela
    aponta para um caminho que já existia.
    """

    #: Bilhete emitido pelo servidor. A tela devolve no cabeçalho ao executar,
    #: e é isso que faz a auditoria registrar a ação como proposta pela IA.
    id: str = ""
    action: str
    label: str
    #: Texto pronto para a tela, na segunda pessoa e no futuro: é uma promessa
    #: do que vai acontecer, não a descrição de algo já feito.
    describe: str
    #: READ | SAFE_WRITE | SENSITIVE_WRITE | DESTRUCTIVE
    classe: str
    #: Tudo que não é READ para e pergunta antes.
    needs_confirmation: bool
    method: str
    path: str
    project_id: str | None = None
    project_name: str | None = None
    reason: str = ""
    #: "regra" ou "modelo". A tela não mostra; a auditoria sim, e é o que
    #: permite medir depois quanto do sistema depende do modelo.
    origem: str = "regra"


class ProposeOut(BaseModel):
    #: `None` quando nada do registro serve — que é o caso mais comum, porque
    #: a maior parte do que se digita é dúvida, não ordem.
    proposal: ProposalOut | None = None
    #: Por que não houve proposta, em texto para a tela.
    message: str = ""


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    #: Qual chapéu respondeu, quando houve um.
    agent: str | None = None
    #: Que camadas de contexto entraram — proveniência, não o conteúdo.
    context_summary: str | None = None
    context_tokens: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: datetime


class ChatHistoryOut(BaseModel):
    items: list[ChatMessageOut] = Field(default_factory=list)


# --- registro de providers e modelos (REQ-13) -----------------------------
#
# Nada nesta seção devolve o valor de uma chave, nem parte dele. O máximo que
# sai daqui é o **nome** da variável de ambiente que a carrega: o valor vive no
# ambiente e não atravessa rota nenhuma (P-05, defesa D-A5).


#: Vocabulário fechado do estado de um provider, que a tela de configurações
#: exibe como está (REQ-14). Estado fora desta lista é engano de código, e o
#: `Literal` faz o erro aparecer aqui em vez de na tela.
EstadoDoProvider = Literal["conectado", "nao_configurado", "desligado", "indisponivel"]


class AiProviderOut(BaseModel):
    """Um provider declarado e o estado em que ele está.

    `desligado` é `enabled: false` no arquivo; `nao_configurado` é a variável
    de `api_key_env` ausente do ambiente; `indisponivel` é habilitado e
    configurado, mas sem resposta na sondagem.
    """

    id: str
    #: local | cloud
    type: str
    enabled: bool
    base_url: str = ""
    #: O NOME da variável de ambiente. Nunca o valor.
    api_key_env: str = ""
    estado: EstadoDoProvider
    #: Por que não está conectado, em texto para a tela. `None` quando está.
    motivo: str | None = None
    #: Ids dos modelos que o registro declara para este provider, na ordem do
    #: arquivo.
    modelos: list[str] = Field(default_factory=list)


class AiProviderList(BaseModel):
    items: list[AiProviderOut] = Field(default_factory=list)
    #: Há registro utilizável? Sem `configs/ai.yml` a lista vem vazia e isto vem
    #: `false` — arquivo ausente é estado normal, não erro (REQ-04).
    ativo: bool = False
    #: Erro de carga do registro, quando houve. A tela diz *por que* está sem
    #: registro em vez de só dizer que está.
    erro: str | None = None


class AiModelOut(BaseModel):
    """Um modelo declarado: identificador nosso, nome real e para que serve."""

    id: str
    model: str
    capabilities: list[str] = Field(default_factory=list)
    #: Quem sabe servi-lo, na ordem de preferência declarada no arquivo.
    providers: list[str] = Field(default_factory=list)
    #: free | low | high
    cost_tier: str
    context_window: int = 0


class AiModelList(BaseModel):
    items: list[AiModelOut] = Field(default_factory=list)
    ativo: bool = False
    erro: str | None = None


class AiProviderHealthOut(BaseModel):
    """Se o provider respondeu agora, e o que ele disse que serve."""

    id: str
    type: str
    disponivel: bool
    #: Por que não respondeu. `None` quando respondeu.
    motivo: str | None = None
    #: Ida e volta medida, em milissegundos. `None` quando não respondeu — não
    #: existe latência de quem não respondeu, e zero seria mentira (P-02).
    latencia_ms: int | None = None
    #: Os modelos que o **próprio provider** listou. Vazio quando ele não
    #: respondeu ou não devolveu lista legível.
    modelos: list[str] = Field(default_factory=list)


class AiHealthOut(BaseModel):
    """Saúde dos providers habilitados. Sempre 200: um fora do ar é dado.

    Provider indisponível é relatado como indisponível, com motivo, e os demais
    seguem normais — derrubar a resposta inteira impediria o painel de abrir por
    causa de um serviço que ele nem precisa (REQ-13, P-06).
    """

    checked_at: datetime
    #: Teto de espera de cada sondagem, para a tela poder explicar o "não
    #: respondeu".
    timeout_s: float
    items: list[AiProviderHealthOut] = Field(default_factory=list)


# --- consumo do período (REQ-12) ------------------------------------------
#
# Toda a seção existe para não afirmar o que ninguém mediu (**P-02**). Por isso
# os indicadores moram num objeto separado, e **todos** são anuláveis: período
# sem nenhuma execução registrada devolve o bloco inteiro em `null`, com
# `medido: false` e o motivo em texto. Zero seria uma afirmação — "custou nada",
# "não falhou nada" —, e ninguém mediu isso.


class AiUsageIndicadores(BaseModel):
    """Os números do período. `None` em qualquer campo é "não medido".

    Campo anulável aqui não é descuido de tipagem: é o contrato que permite à
    tela pintar o indicador em cinza em vez de estampar um zero que a pessoa
    leria como medição.
    """

    #: Tentativas de execução — uma pergunta com fallback conta mais de uma.
    chamadas: int | None = None
    #: Perguntas distintas: `correlation_id` diferentes no período.
    perguntas: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None

    #: Local × nuvem sai do registro declarativo (`type: local` em
    #: `configs/ai.yml`), não de coluna do banco — um provedor pode mudar de
    #: lado sem que o histórico mude de significado.
    chamadas_local: int | None = None
    tokens_local: int | None = None
    chamadas_cloud: int | None = None
    tokens_cloud: int | None = None

    #: Soma do que foi possível calcular. `None` quando nenhuma tentativa do
    #: período tinha preço declarado (REQ-11).
    custo_estimado: float | None = None
    #: A data em que o preço usado foi anotado. Vai junto do custo aonde ele
    #: aparecer: custo sem data envelhece sem avisar.
    price_date: str | None = None
    #: Quantas tentativas entraram na conta sem custo conhecido. Maior que zero
    #: significa que `custo_estimado` é **parcial**, e a tela diz isso em vez de
    #: apresentar o total como se fosse tudo.
    chamadas_sem_custo: int | None = None

    #: Média só das tentativas executadas. `skipped` fica de fora: candidato que
    #: a cadeia nem chegou a tentar não tem latência, e contá-lo como 0 puxaria
    #: a média para baixo inventando velocidade.
    latencia_media_ms: float | None = None
    #: `timeout` e `error`. `skipped` não é falha.
    falhas: int | None = None
    #: Perguntas que precisaram de mais de uma tentativa — é esta a definição de
    #: "fallback acionado" desta rota, e é o que o número na tela conta. Uma
    #: pergunta que passou por três provedores conta **uma** vez: o que se mede
    #: é quantas vezes a cadeia precisou existir, não o tamanho dela.
    fallbacks: int | None = None


class AiUsageOut(BaseModel):
    """O consumo de IA de um período (REQ-12).

    `medido: false` com todos os indicadores em `null` é resposta legítima, e a
    mais comum numa instalação nova: significa que não há execução registrada na
    janela, não que a IA rodou de graça e sem erro.
    """

    since: datetime
    until: datetime
    #: O tamanho da janela pedida, para a tela rotular o que está mostrando.
    days: int
    #: Houve alguma execução registrada no período?
    medido: bool
    #: O que falta para haver medição. `None` quando há (**P-02**).
    motivo: str | None = None
    indicadores: AiUsageIndicadores = Field(default_factory=AiUsageIndicadores)
