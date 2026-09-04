"""Qual modelo atende esta pergunta, e em que ordem tentar (REQ-07, REQ-08).

Entra uma `Classificacao` (do `classifier`), sai uma lista ordenada de
candidatos — pares modelo × provider — que o runner consome de cima para baixo.
A lista existe no lugar de um nome único porque o mesmo modelo costuma ter mais
de um provider capaz de servi-lo, e porque a segunda opção precisa estar
decidida antes de a primeira cair, não depois.

**A política inteira mora em `escolher`.** Ela é curta de propósito: roteamento
espalhado em `if` por três módulos é como se manda para a nuvem, sem querer, o
que estava marcado para não sair da máquina. Quem lê aquela função lê a decisão
completa, na ordem em que ela acontece:

1. `privacy == local` vai para modelo local, **sempre**, sem consultar
   complexidade. Não havendo modelo local habilitado, a pergunta é **recusada** —
   nunca promovida para a nuvem. Este é o item que não admite exceção: errar aqui
   significa mandar para fora o que não podia sair.
2. Senão, a complexidade decide entre os modelos de nuvem habilitados que tenham
   a capacidade pedida: até o limiar, o mais barato; acima dele, o de maior
   janela.
3. Sem candidato com a capacidade pedida, cai no modelo padrão configurado em
   vez de falhar.

A escolha manual da pessoa (REQ-08) vence o roteamento automático e marca a
decisão como `manual`; AUTO é o padrão. Ela vence o *roteamento*, que é o item 2
— não a marca de privacidade do item 1. Pedir na tela um modelo de nuvem para
uma pergunta marcada como local é pedir exatamente o que a marca proíbe, então
o pedido é ignorado e a resposta continua vindo de dentro da máquina.

Os limiares vêm de `configs/ai.yml` (bloco `roteamento`), não de constante
daqui: eles mudam quando muda o modelo disponível, e mudar modelo não pode
exigir editar código (REQ-07). Registro ausente é estado normal, não erro: sem
`configs/ai.yml` a lista sai vazia e o Cockpit AI segue pelo provider do `.env`,
como antes desta mudança (REQ-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.ai.classifier import TIPOS, Classificacao
from app.services.ai.registry import (
    AiConfig,
    ModeloDeclarado,
    ProviderDeclarado,
    get_ai_config,
)

Modo = Literal["auto", "manual"]

#: `task_type` (do classificador) -> capacidade exigida do modelo (do registro).
#: Os dois vocabulários foram escritos iguais de propósito — os nove tipos do
#: REQ-06 são os nove valores de `capabilities` do REQ-02 —, então o mapeamento
#: é a identidade. Ele existe como tabela mesmo assim porque os dois lados
#: pertencem a donos diferentes: o tipo é do classificador, a capacidade é do
#: YAML que a pessoa edita. No dia em que um ganhar um nome que o outro não tem,
#: a tradução muda aqui e em nenhum outro lugar.
CAPACIDADE_POR_TIPO: dict[str, str] = {tipo: tipo for tipo in TIPOS}

#: "O mais barato" precisa de uma ordem, e `cost_tier` é rótulo, não número.
#: Modelo com nível desconhecido vai para o fim: preço que ninguém classificou
#: não pode ganhar a disputa do mais barato por omissão (**P-02**).
ORDEM_DE_CUSTO: dict[str, int] = {"free": 0, "low": 1, "high": 2}
CUSTO_DESCONHECIDO = 9


@dataclass(frozen=True)
class Candidato:
    """Um par modelo × provider, pronto para virar uma tentativa do runner."""

    modelo: ModeloDeclarado
    provider: ProviderDeclarado

    @property
    def modelo_id(self) -> str:
        """O id lógico nosso, que indexa a tabela de preço e a cadeia."""
        return self.modelo.id

    @property
    def provider_id(self) -> str:
        return self.provider.id

    @property
    def local(self) -> bool:
        return self.provider.local

    def __str__(self) -> str:
        return f"{self.modelo.id}@{self.provider.id}"


@dataclass(frozen=True)
class EscolhaManual:
    """O que a tela pediu com todas as letras. Vazio é o modo AUTO (REQ-08).

    `modelo` é o id lógico declarado no registro, nunca o nome do modelo no
    fornecedor: **P-06** diz que o nome real sai da configuração do servidor, e
    id desconhecido aqui não vira nome cru mandado para a API.
    """

    modelo: str = ""
    provider: str = ""

    @property
    def pedida(self) -> bool:
        return bool(self.modelo or self.provider)


@dataclass(frozen=True)
class Decisao:
    """A lista ordenada, quem a decidiu e por quê.

    `motivo` é frase curta para log e tela: sem ela, "por que este modelo?" só
    se responde relendo o registro inteiro.
    """

    candidatos: tuple[Candidato, ...]
    #: Quem decidiu a lista. `manual` só quando o pedido da tela foi honrado.
    modo: Modo
    motivo: str
    #: Preenchido só na recusa do REQ-07 item 1. Texto para a pessoa ler.
    recusa: str = ""

    def __post_init__(self) -> None:
        # Rede de segurança, não validação de entrada: recusa acompanhada de
        # candidato é exatamente o vazamento que o item 1 do REQ-07 proíbe, e
        # ele apareceria como uma resposta normal vinda da nuvem.
        if self.recusa and self.candidatos:
            raise ValueError("Decisão recusada não pode carregar candidato.")

    @property
    def recusada(self) -> bool:
        return bool(self.recusa)

    @property
    def escolhido(self) -> Candidato | None:
        """O primeiro da fila, ou `None` quando não há para onde ir."""
        return self.candidatos[0] if self.candidatos else None


def capacidade_exigida(task_type: str) -> str:
    """A capacidade que o modelo precisa declarar para atender este tipo."""
    return CAPACIDADE_POR_TIPO.get(task_type, task_type)


def escolher(
    classificacao: Classificacao,
    manual: EscolhaManual | None = None,
    config: AiConfig | None = None,
) -> Decisao:
    """A política do REQ-07 inteira, de cima para baixo, num lugar só.

    `config` existe para o teste (e para o runner que já tem o registro em mãos)
    injetar um registro; sem ele, vale o desta instalação.
    """
    registro = config if config is not None else get_ai_config()
    pedido = manual or EscolhaManual()
    capacidade = capacidade_exigida(classificacao.task_type)

    # --- 1. privacidade, antes de qualquer outra coisa (REQ-07, item 1) ----
    # Sem consultar complexidade e sem admitir exceção manual. É o único ponto
    # do router em que "não achei" vira recusa em vez de degradação.
    if classificacao.privacy == "local":
        return _decidir_local(registro, capacidade, pedido)

    # --- 2. a escolha manual vence o roteamento automático (REQ-08) -------
    if pedido.modelo:
        candidatos = _pares(registro, _modelo_pedido(registro, pedido.modelo), pedido.provider)
        if candidatos:
            return Decisao(candidatos, "manual", f"modelo {pedido.modelo!r} pedido na tela")
        # Id que o registro não conhece, ou cujo provider está desligado, não
        # pode virar nome cru enviado ao fornecedor (**P-06**): segue o
        # automático, dizendo na frase por que o pedido não valeu.
        nota = f"o modelo {pedido.modelo!r} pedido na tela não está disponível; "
    else:
        nota = ""

    # --- 3. a complexidade decide entre os de nuvem (REQ-07, item 2) ------
    limiar = registro.roteamento.limiar_complexidade
    disponiveis = _modelos_de_nuvem(registro, capacidade)
    if disponiveis:
        if classificacao.complexity <= limiar:
            ordenados = sorted(disponiveis, key=_mais_barato)
            criterio = (
                f"complexidade {classificacao.complexity} até o limiar {limiar}: "
                "o mais barato"
            )
        else:
            ordenados = sorted(disponiveis, key=_maior_janela)
            criterio = (
                f"complexidade {classificacao.complexity} acima do limiar {limiar}: "
                "o de maior janela"
            )
        candidatos = _pares(registro, ordenados, pedido.provider)
        if candidatos:
            # O local entra no FIM da fila, depois de todo candidato de nuvem
            # — nunca disputa "o mais barato" nem "a maior janela" (é por
            # isso que _modelos_de_nuvem o exclui acima), mas continua sendo
            # a rede de segurança quando a nuvem inteira falhar (achado da
            # verificação ao vivo da T-14, 2026-09-04: as duas contas cloud
            # ficaram sem saldo, o Qwen local estava de pé e saudável, e a
            # pergunta falhou sem nunca oferecê-lo como candidato — o
            # comentário de `configs/ai.yml` sobre "último elo sem internet"
            # não correspondia ao que o router fazia).
            # Restrição manual de provider é a pessoa dizendo "só este
            # endereço" — não estender ao local por baixo dela seria ignorar
            # um pedido explícito. Sem restrição, o local entra como último
            # recurso de qualquer forma.
            if not pedido.provider:
                locais_com_capacidade = [
                    modelo
                    for modelo in _modelos_locais(registro)
                    if capacidade in modelo.capabilities
                ]
                # `so_local=True`: um modelo servido tanto por nuvem quanto
                # por Ollama não pode duplicar aqui o candidato de nuvem que
                # já está em `candidatos` — só o lado local dele entra.
                candidatos = candidatos + _pares(
                    registro, locais_com_capacidade, so_local=True
                )
            modo: Modo = "manual" if pedido.provider else "auto"
            return Decisao(candidatos, modo, f"{nota}{criterio} entre os que fazem {capacidade}")

    # --- 4. sem candidato com a capacidade, o padrão (REQ-07, item 3) -----
    # Capacidade que nenhum modelo declara é buraco do registro, não pergunta
    # inválida: cair no padrão responde, enquanto falhar só deixaria a pessoa
    # sem resposta por causa de uma linha que faltou no YAML.
    padrao = registro.roteamento.modelo_padrao
    candidatos = _pares(registro, _modelo_pedido(registro, padrao), pedido.provider)
    if candidatos:
        modo = "manual" if pedido.provider else "auto"
        return Decisao(
            candidatos,
            modo,
            f"{nota}nenhum modelo habilitado declara {capacidade}: vale o padrão {padrao!r}",
        )

    # Registro vazio, ou padrão indisponível: lista vazia e nenhum erro. Sem
    # `configs/ai.yml` o Cockpit AI segue pelo provider do `.env` (REQ-04), e
    # levantar aqui quebraria a instalação que nunca teve o arquivo.
    return Decisao((), "auto", f"{nota}o registro não oferece modelo para esta pergunta")


# --- item 1: o caminho que não pode sair da máquina -----------------------


def _decidir_local(registro: AiConfig, capacidade: str, pedido: EscolhaManual) -> Decisao:
    """Modelo local, ou recusa. Nunca a nuvem (REQ-07, item 1)."""
    locais = _capacidade_primeiro(_modelos_locais(registro), capacidade)
    if not locais:
        return Decisao(
            candidatos=(),
            modo="auto",
            motivo="pergunta marcada como local e nenhum modelo local habilitado",
            recusa=(
                "Esta pergunta está marcada para não sair desta máquina e não há "
                "modelo local habilitado no registro. Ligue o provider local em "
                "configs/ai.yml (e confira se o Ollama está de pé) e pergunte de "
                "novo: ela não vai para a nuvem."
            ),
        )

    # Provider pedido na tela só vale se ele mesmo for local. Pedido apontando
    # para fora é descartado aqui, não filtrado adiante: filtrar deixaria a
    # lista vazia e uma lista vazia, neste ramo, tem cara de recusa.
    provider = pedido.provider if _e_local(registro, pedido.provider) else ""

    if pedido.modelo:
        escolhido = [modelo for modelo in locais if modelo.id == pedido.modelo]
        candidatos = _pares(registro, escolhido, provider, so_local=True)
        if candidatos:
            return Decisao(
                candidatos,
                "manual",
                f"pergunta local; modelo local {pedido.modelo!r} pedido na tela",
            )

    # Ordem declarada, sem consultar complexidade: aqui o critério é o destino,
    # não o tamanho da tarefa. Modelo local sem a capacidade pedida fica no fim
    # da fila em vez de sumir — é o equivalente local do item 3, e responder
    # devagar continua sendo melhor que recusar quem só marcou privacidade.
    candidatos = _pares(registro, locais, provider, so_local=True)
    if not candidatos:
        # O provider pedido não serve nenhum modelo local. A pergunta ainda tem
        # para onde ir dentro da máquina, e isso não vira recusa.
        candidatos = _pares(registro, locais, "", so_local=True)
    return Decisao(
        candidatos,
        "auto",
        "pergunta marcada como local: só modelo local, sem consultar complexidade",
    )


# --- consultas ao registro ------------------------------------------------


def _pares(
    registro: AiConfig,
    modelos: list[ModeloDeclarado],
    provider: str = "",
    *,
    so_local: bool = False,
) -> tuple[Candidato, ...]:
    """Expande cada modelo nos providers que sabem servi-lo, na ordem declarada.

    A expansão é o que transforma a escolha em fila de tentativas: modelo
    servido por dois providers rende dois candidatos, e o segundo só é usado se
    o primeiro cair (REQ-09).

    `so_local` recorta o modelo pelo lado local — um modelo declarado na nuvem
    **e** no Ollama entra pela porta local e só por ela.
    """
    candidatos: list[Candidato] = []
    for modelo in modelos:
        for declarado in registro.providers_do_modelo(modelo.id):
            if so_local and not declarado.local:
                continue
            if provider and declarado.id != provider:
                continue
            candidatos.append(Candidato(modelo=modelo, provider=declarado))
    return tuple(candidatos)


def _modelo_pedido(registro: AiConfig, modelo_id: str) -> list[ModeloDeclarado]:
    """O modelo com esse id, ou lista vazia. Id desconhecido não levanta."""
    modelo = registro.modelo(modelo_id) if modelo_id else None
    return [modelo] if modelo is not None else []


def _modelos_locais(registro: AiConfig) -> list[ModeloDeclarado]:
    """Modelos com pelo menos um provider local habilitado."""
    return [
        modelo
        for modelo in registro.modelos
        if any(declarado.local for declarado in registro.providers_do_modelo(modelo.id))
    ]


def _modelos_de_nuvem(registro: AiConfig, capacidade: str) -> list[ModeloDeclarado]:
    """Modelos com a capacidade pedida e ao menos um provider de nuvem de pé.

    O modelo servido só pelo Ollama fica de fora desta disputa de propósito.
    Ele é `cost_tier: free` e venceria "o mais barato" em toda pergunta abaixo
    do limiar — mandando o trabalho inteiro para 24-32 tok/s nesta máquina, que
    é justamente a premissa que a spec derruba na nota do REQ-07. O local está
    na cadeia por privacidade (item 1) e como último elo sem internet, não por
    economia.
    """
    return [
        modelo
        for modelo in registro.modelos_por_capacidade(capacidade)
        if any(not declarado.local for declarado in registro.providers_do_modelo(modelo.id))
    ]


def _e_local(registro: AiConfig, provider_id: str) -> bool:
    declarado = registro.provider(provider_id) if provider_id else None
    return declarado is not None and declarado.enabled and declarado.local


def _capacidade_primeiro(
    modelos: list[ModeloDeclarado], capacidade: str
) -> list[ModeloDeclarado]:
    """Quem declara a capacidade na frente; o resto atrás, na ordem declarada."""
    com = [modelo for modelo in modelos if capacidade in modelo.capabilities]
    sem = [modelo for modelo in modelos if capacidade not in modelo.capabilities]
    return com + sem


# --- os dois critérios de ordenação do item 2 -----------------------------
#
# `sorted` é estável, então empate nos dois critérios mantém a ordem declarada
# no YAML — que é a preferência de quem escreveu o arquivo, e é o desempate
# certo quando o router não tem opinião.


def _mais_barato(modelo: ModeloDeclarado) -> tuple[int, int]:
    """Nível de custo; empate desempata pela janela maior."""
    return (ORDEM_DE_CUSTO.get(modelo.cost_tier, CUSTO_DESCONHECIDO), -modelo.context_window)


def _maior_janela(modelo: ModeloDeclarado) -> tuple[int, int]:
    """Janela de contexto; empate desempata pelo mais barato."""
    return (-modelo.context_window, ORDEM_DE_CUSTO.get(modelo.cost_tier, CUSTO_DESCONHECIDO))
