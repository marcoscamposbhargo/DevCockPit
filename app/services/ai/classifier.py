"""O que a pergunta é, quanto ela pesa e se ela pode sair desta máquina.

Roda **antes** do roteamento de modelo (REQ-06) e produz os quatro campos que o
`model_router` consome: `task_type`, `complexity`, `privacy` e
`tools_required`.

Só regra. Nenhuma chamada a modelo, e isso não é preferência de estilo: a Fase 3
mediu de 3 a 26 segundos para classificar uma frase curta no provedor local
desta máquina — mais que a própria resposta em muitos casos. Foi por isso que o
modelo saiu do desempate do orquestrador (`orchestrator.propose`), e é o mesmo
motivo pelo qual ele não entra aqui. O teto do REQ-06 é 50 ms; a regra responde
em microssegundos.

O que veio pronto de `orchestrator.py`:

- `normalizar`, para "ALTERAÇÃO" casar com "alteracao";
- `REGRAS`, o vocabulário de verbo de painel ("sobe", "desliga", "log",
  "portas"). Ele já é, palavra por palavra, a definição de `tools_required`:
  ferramenta aqui é o catálogo fechado de ações (**P-01**), então "a frase pede
  uma ferramenta" e "a frase casa com uma regra do orquestrador" são a mesma
  pergunta. Copiar esses verbos para cá deixaria as duas listas divergindo na
  primeira vez que o orquestrador ganhasse um verbo novo.

O vocabulário de `especialistas.py` **não** serve como gatilho: ele separa em
três chapéus (DevOps, Full Stack, QA) e aqui são nove tipos. O gatilho do
especialista QA junta "teste", "bug" e "erro" num regex só, porque três chapéus
só precisam de três baldes; aqui essas palavras têm de cair em `testing`,
`debugging` e `qa` separados, que roteiam para modelos diferentes.

O **significado** de `qa`, porém, é o mesmo do especialista `QA`
(`especialistas.py:104`) e o do PRD §24: quality assurance — requisito, critério
de aceite, caso de borda, regressão, risco, cobertura. Não é "pergunta e
resposta". O token já tinha dono neste serviço, e dois sentidos para a mesma
palavra dentro do mesmo diretório é exatamente o defeito que este projeto já
pagou caro em outra frente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.ai.orchestrator import REGRAS, normalizar

TaskType = Literal[
    "simple_task",
    "coding",
    "debugging",
    "architecture",
    "documentation",
    "testing",
    "qa",
    "planning",
    "refactoring",
]

Privacy = Literal["local", "internal"]

#: Os nove do REQ-06, para o teste conferir que a tabela de casos cobre todos.
TIPOS: tuple[TaskType, ...] = (
    "simple_task",
    "coding",
    "debugging",
    "architecture",
    "documentation",
    "testing",
    "qa",
    "planning",
    "refactoring",
)

#: As regras do orquestrador, compiladas uma vez. A lista é dele; só a forma é
#: nossa, porque `re.search` com padrão em texto paga o cache do módulo `re` a
#: cada chamada e o orçamento aqui é de 50 ms.
ACOES_DO_PAINEL: tuple[re.Pattern[str], ...] = tuple(
    re.compile(padrao) for padrao, _chave in REGRAS
)

#: Gatilhos por tipo, **em ordem de decisão**: o primeiro que casar vence. A
#: ordem é o que resolve a frase que mistura assuntos, e vai do sinal mais
#: específico para o mais genérico.
#:
#: A fronteira entre os três tipos vizinhos, que é onde a ordem trabalha:
#:
#: - `qa` **avalia** — requisito, critério de aceite, caso de borda, regressão,
#:   risco, cobertura, "o que pode quebrar", "faltou testar";
#: - `testing` **escreve** teste — pytest, fixture, mock, tdd, "escreve um teste";
#: - `debugging` **conserta** defeito que já apareceu — bug, traceback, "quebrou",
#:   "não funciona".
#:
#: `qa` vem antes dos dois porque seus gatilhos são frases inteiras ("o que pode
#: quebrar", "faltou testar") que emolduram a pergunta como avaliação, e elas
#: contêm por dentro as palavras soltas de `debugging` e `testing`. Na ordem
#: inversa nenhuma pergunta de QA sobreviveria. `debugging` vem antes de
#: `testing` pelo mesmo motivo em escala menor: "o pytest quebrou com traceback"
#: é conserto, não escrita de teste.
#:
#: `refactoring` fica na frente de todos porque seu gatilho é ordem de trabalho
#: explícita: "refatora sem causar regressão" pede o refactor, não a avaliação.
#:
#: Português como a pessoa digita, sem acento — `normalizar` já tirou.
GATILHOS: tuple[tuple[TaskType, re.Pattern[str]], ...] = (
    (
        "refactoring",
        re.compile(
            r"\b(refator\w*|simplific\w*|reorganiz\w*|reescrev\w*|reescrit\w*|"
            r"extrair|renome\w*|deduplic\w*|duplicad\w*|divida tecnica|"
            r"codigo repetido|limpar o codigo|limpa o codigo)\b"
        ),
    ),
    (
        "qa",
        re.compile(
            r"\b(requisito|requisitos|criterios? de aceit\w*|edge cases?|"
            r"casos? de borda|regress\w*|risco|riscos|arriscad\w*|cobertura|"
            r"qualidade|(pode|podem|poderia|vai|iria) quebr\w*|quebraria|"
            r"(faltou|falta|faltam) testar|ficou sem teste|esta coberto|"
            r"esta testado|nao foi testado|nao esta coberto)\b"
        ),
    ),
    (
        "debugging",
        re.compile(
            r"\b(bug|bugs|erro|erros|falha|falhou|falhando|quebr\w*|traceback|"
            r"stacktrace|stack trace|excecao|exception|debug\w*|depur\w*|"
            r"corrig\w*|consert\w*|arrum\w*|investig\w*|"
            r"nao funciona|nao esta funcionando|parou de funcionar|nao sobe|"
            r"nao abre|nao roda|nao conecta)\b"
        ),
    ),
    (
        "testing",
        re.compile(
            r"\b(teste|testes|testar|testando|testa|pytest|unittest|jest|vitest|"
            r"mock|mocks|fixture|fixtures|tdd|assercao|assert)\b"
        ),
    ),
    (
        "architecture",
        re.compile(
            r"\b(arquitetur\w*|design|desenho|estrutur\w*|modelag\w*|modelar|"
            r"tradeoff|trade-off|acopl\w*|camada|camadas|monolito|"
            r"microservic\w*|microsservic\w*|escalab\w*|escalar|adr|"
            r"padrao de projeto|design pattern|decisao tecnica|"
            r"decisao arquitetural|separacao de responsabilidade)\b"
        ),
    ),
    (
        "documentation",
        re.compile(
            r"\b(document\w*|readme|docstring|changelog|comentari\w*|manual|"
            r"guia|tutorial)\b"
        ),
    ),
    (
        "planning",
        re.compile(
            r"\b(planej\w*|plano|planos|roadmap|prioriz\w*|prioridade|cronograma|"
            r"estimativa|estimar|prazo|backlog|sprint|milestone|escopo|"
            r"especificacao|proximo passo|proximos passos|por onde comec\w*|"
            r"o que fazer primeiro)\b"
        ),
    ),
    (
        "coding",
        re.compile(
            r"\b(implement\w*|cria\w*|crie|adicion\w*|escrev\w*|gera|gerar|codigo|"
            r"funcao|funcoes|metodo|metodos|classe|endpoint|rota|rotas|api|"
            r"componente|script|query|migration|migracao)\b"
        ),
    ),
)

#: Fronteira entre a frase de uma linha e o texto que traz problema junto. Só
#: pesa na complexidade; não decide tipo.
FRASE_CURTA = 80

#: Ponto de partida da complexidade por tipo. É o custo típico da tarefa, não a
#: dificuldade da frase — a frase entra depois, nos ajustes.
#:
#: `simple_task` começa baixo porque é o padrão de quem não deu sinal nenhum, e
#: o padrão não pode inflar o roteamento sozinho. Quem cai aqui com texto longo
#: sobe pela escada de tamanho em `_complexidade`, que é o ajuste feito para
#: isso.
BASE_POR_TIPO: dict[TaskType, int] = {
    "simple_task": 5,
    "documentation": 30,
    "testing": 40,
    "coding": 50,
    "qa": 55,
    "refactoring": 55,
    "debugging": 60,
    "planning": 60,
    "architecture": 75,
}

#: Caminho de arquivo na frase. Serve à complexidade (pergunta ancorada em
#: arquivo real custa mais contexto) e **não** à privacidade — ver `_privacidade`.
CAMINHO = re.compile(
    r"([\w.-]+[/\\])+[\w.-]+"
    r"|\b[\w-]+\.(py|js|mjs|ts|tsx|jsx|md|ya?ml|json|toml|html|css|sql|txt|"
    r"ini|cfg|sh|ps1)\b"
    r"|\b[a-z]:[/\\]"
)

#: Sinal de que a frase carrega trecho de código ou saída de erro colada.
CODIGO_COLADO = re.compile(r"```|traceback|file \"|\bat line \d|^\s{4}\S", re.MULTILINE)

#: Marca explícita de que a pergunta não sai da máquina. É a lista fechada que
#: alimenta o REQ-07 item 1: `privacy: local` manda o roteamento para um modelo
#: local e, não havendo, recusa a pergunta em vez de promovê-la para a nuvem.
MARCA_PRIVACIDADE = re.compile(
    r"#local\b|\[local\]|\bprivad\w*|\bconfidencia\w*|\bsigilos\w*|\bsem nuvem\b|"
    r"\bso local\b|\bsomente local\b|\blocal only\b|\boffline\b|"
    r"\bnao (envie|envia|mande|manda|mostre|compartilh\w*)\b|"
    r"\bnao pode sair (daqui|da maquina|do meu computador)\b"
)

#: Vocabulário de segredo. Deliberadamente largo: "chave" em português é chave
#: primária, chave de dicionário e chave de API, e as três caem aqui. Marcar
#: `local` à toa custa uma resposta lenta; marcar `internal` à toa manda para
#: fora o que não podia sair. Os dois erros não valem o mesmo, então o sinal
#: ambíguo desempata sempre para `local` (**P-05**).
SEGREDO = re.compile(
    r"\bsenha\w*|\bpassword\b|\btoken\b|\bapi[_ -]?key\b|\bchave\w*|\bsecret\w*|"
    r"\bcredencia\w*|\.env\b|\bid_rsa\b|\bsecrets?\.(ya?ml|json)\b|\bcpf\b|\bcnpj\b|"
    r"\bcartao de credito\b|\bdados pessoais\b|\bdado sensivel\b|\bdados sensiveis\b"
)


@dataclass(frozen=True)
class Classificacao:
    """O que o `model_router` precisa saber antes de escolher um modelo."""

    task_type: TaskType
    #: 0 a 100. Sempre dentro da faixa — o router compara com limiares vindos do
    #: YAML, e um valor fora da escala viraria escolha silenciosamente errada.
    complexity: int
    privacy: Privacy
    #: A frase pede uma ação do catálogo fechado (`orchestrator.REGRAS`).
    tools_required: bool

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "complexity": self.complexity,
            "privacy": self.privacy,
            "tools_required": self.tools_required,
        }


def _marca_no_estado(estado: dict | None) -> bool:
    """Marca de privacidade vinda de quem chamou, e só ela.

    O `estado` que o chat passa é a foto da máquina (servidores de pé, portas,
    git) e o Context Engine já o consome inteiro. Inferir privacidade dali seria
    palpite com cara de medição (**P-02**), então aqui só se lê o que foi dito
    com todas as letras.
    """
    if not isinstance(estado, dict):
        return False
    if str(estado.get("privacy") or "").strip().lower() == "local":
        return True
    return bool(estado.get("privado"))


def _privacidade(texto: str, estado: dict | None) -> Privacy:
    """`local` quando há gatilho explícito; `internal` no resto.

    Caminho de arquivo **sozinho** não marca `local`: quase toda pergunta de
    código cita um arquivo, e marcar todas mandaria o trabalho inteiro para o
    provedor local — 24 a 32 tok/s nesta máquina, ou seja, minutos por resposta.
    O que marca é o arquivo que costuma guardar segredo (`.env`, `id_rsa`,
    `secrets.yml`), e esse está em `SEGREDO`.
    """
    if _marca_no_estado(estado):
        return "local"
    if MARCA_PRIVACIDADE.search(texto) or SEGREDO.search(texto):
        return "local"
    return "internal"


def _complexidade(tipo: TaskType, pergunta: str, texto: str, assuntos: int) -> int:
    """Base do tipo mais o que a própria frase acrescenta, presa em 0–100."""
    valor = BASE_POR_TIPO[tipo]

    tamanho = len(pergunta)
    if tamanho > 600:
        valor += 22
    elif tamanho > 240:
        valor += 16
    elif tamanho > FRASE_CURTA:
        valor += 8

    if CAMINHO.search(texto):
        valor += 8
    if CODIGO_COLADO.search(texto):
        valor += 10

    # Frase que casa com vários assuntos ao mesmo tempo ("refatora e cobre com
    # teste") custa mais que a que casa com um só, mesmo sendo curta. Teto baixo
    # porque o sinal é fraco.
    valor += min(max(assuntos - 1, 0) * 5, 10)

    return max(0, min(100, valor))


def classificar(pergunta: str, *, estado: dict | None = None) -> Classificacao:
    """Classifica a pergunta por regra determinística, sem tocar em modelo.

    `estado` é o mesmo dicionário que `chat_service.ask` já repassa ao Context
    Engine; aqui só a marca explícita de privacidade é lida.
    """
    original = pergunta or ""
    texto = normalizar(original)
    tools_required = any(padrao.search(texto) for padrao in ACOES_DO_PAINEL)

    casados = [tipo for tipo, padrao in GATILHOS if padrao.search(texto)]
    if casados:
        tipo: TaskType = casados[0]
    else:
        # `simple_task` é o padrão: nenhum gatilho casou, então a frase não pediu
        # trabalho de nenhum dos oito tipos. Cabem aqui a ordem de painel ("sobe
        # o zapcrm") e a dúvida solta ("qual a diferença entre uvicorn e
        # gunicorn?") — as duas são baratas e as duas vão para o modelo mais
        # barato, que é o mesmo destino.
        #
        # O padrão **não** é `qa`: `qa` aqui é quality assurance, o mesmo
        # sentido do especialista `QA` (`especialistas.py:104`). Se fosse o
        # padrão, toda pergunta genérica seria roteada como avaliação de teste —
        # o contrário do que ela é.
        tipo = "simple_task"

    return Classificacao(
        task_type=tipo,
        complexity=_complexidade(tipo, original, texto, len(casados)),
        privacy=_privacidade(texto, estado),
        tools_required=tools_required,
    )
