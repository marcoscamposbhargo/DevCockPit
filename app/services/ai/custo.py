"""Custo estimado de uma tentativa, a partir da tabela de preço datada (REQ-11).

O preço não é medido pelo provedor a cada chamada: ele é **declarado** em
`configs/ai.yml`, por milhão de tokens, com a data em que alguém o anotou. Este
módulo faz a única conta que existe entre a contagem de tokens e as duas colunas
que `ai_run` guarda — `estimated_cost` e `price_date` — e devolve as duas juntas,
porque custo sem data envelhece sem avisar: o preço do fornecedor muda e o número
na tela continua com cara de fato.

A regra que manda aqui é **P-02**: modelo sem preço declarado devolve `None`,
nunca `0`. A distinção não é preciosismo. `0` é uma afirmação — quer dizer "esta
chamada não custou nada", o que é verdade para o modelo que roda nesta máquina e
mentira para um provedor de nuvem cujo preço ninguém anotou ainda. Quem lê a tela
age em cima do número; um zero inventado convence mais que um espaço vazio.

Por isso `Preco(input_por_milhao=0.0, ...)` declarado no YAML devolve `0.0` com
data, e modelo ausente da tabela devolve `NAO_MEDIDO`. São estados diferentes, e
o tipo de retorno os mantém diferentes até a tela.

A conta roda em `Decimal` de propósito. O destino é `Numeric(12, 6)`, e custo de
chamada curta vive na casa dos centésimos de centavo: somar float por float até
lá acumula erro binário justamente nas casas que sobrevivem à coluna.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.services.ai.registry import AiConfig, get_ai_config

#: O preço é declarado por milhão de tokens (REQ-11), não por token: é assim que
#: os fornecedores publicam, e converter na hora de anotar convidaria ao erro de
#: casa decimal onde ele seria mais caro de perceber.
TOKENS_POR_UNIDADE_DE_PRECO = Decimal(1_000_000)

#: Seis casas porque é o que `ai_run.estimated_cost` guarda (`Numeric(12, 6)`).
#: Arredondar aqui, e não no banco, deixa o valor gravado igual ao conferido no
#: teste.
CASAS_DECIMAIS = Decimal("0.000001")


@dataclass(frozen=True)
class CustoEstimado:
    """O par que a linha de `ai_run` grava: o valor e a data da tabela usada.

    Os dois andam juntos ou nenhum anda. Valor sem data seria um número que não
    se pode datar na tela (REQ-11); data sem valor não afirma nada.
    """

    valor: float | None
    price_date: str | None

    @property
    def medido(self) -> bool:
        """Houve preço declarado?

        `False` significa "ninguém anotou o preço deste modelo", que não é a
        mesma coisa que `valor == 0.0` — esse é o custo de quem declarou zero.
        """
        return self.valor is not None


#: O que se grava quando ninguém anotou o preço do modelo: nulo nas duas
#: colunas, para a tela dizer "não medido" em vez de mostrar zero (**P-02**).
NAO_MEDIDO = CustoEstimado(valor=None, price_date=None)


def estimar(
    modelo_id: str,
    tokens_in: int,
    tokens_out: int,
    config: AiConfig | None = None,
) -> CustoEstimado:
    """Estima o custo da tentativa e devolve a data do preço que a produziu.

    `modelo_id` é o identificador lógico nosso (o `id` do bloco `modelos`), não o
    nome do modelo no fornecedor: é por ele que a tabela de preço indexa, e
    trocar o nome real do fornecedor não pode invalidar a tabela.

    Entrada e saída são cobradas por valores diferentes, então a conta é feita em
    duas parcelas — usar um preço só faria a estimativa errar sempre para o mesmo
    lado, e de um jeito que passa despercebido.

    `config` existe para o teste (e para o runner que já tem o registro em mãos)
    injetar um registro; sem ele, vale o desta instalação.
    """
    registro = config if config is not None else get_ai_config()
    preco = registro.preco(modelo_id)
    if preco is None:
        # Modelo fora da tabela — inclusive modelo que nem existe no registro.
        # Os dois casos são a mesma afirmação: não há preço para dizer.
        return NAO_MEDIDO

    entrada = _por_milhao(preco.input_por_milhao) * _tokens(tokens_in)
    saida = _por_milhao(preco.output_por_milhao) * _tokens(tokens_out)
    total = (entrada + saida) / TOKENS_POR_UNIDADE_DE_PRECO

    return CustoEstimado(
        valor=float(total.quantize(CASAS_DECIMAIS, rounding=ROUND_HALF_UP)),
        price_date=preco.anotado_em,
    )


def _por_milhao(valor: float) -> Decimal:
    """Converte via `str` para não herdar o erro binário do float do YAML.

    `Decimal(0.27)` guarda 0.2700000000000000177...; `Decimal("0.27")` guarda
    0.27, que é o que estava escrito no arquivo.
    """
    return Decimal(str(valor))


def _tokens(quantidade: int) -> Decimal:
    """Contagem de tokens, nunca negativa.

    Provedor que reporta contagem estranha em erro ou stream interrompido não
    pode virar crédito no custo do período.
    """
    return Decimal(max(0, int(quantidade)))
