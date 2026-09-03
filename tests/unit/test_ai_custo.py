"""Custo estimado a partir da tabela de preço datada (REQ-11).

O que precisa ser verdade ao mesmo tempo: a conta bate com tokens × preço, o
número sai acompanhado da data da tabela, e — o ponto do REQ — "custou zero" e
"ninguém mediu" continuam sendo duas coisas diferentes até a última asserção
(**P-02**).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.services.ai.custo import NAO_MEDIDO, estimar
from app.services.ai.registry import AiConfig

pytestmark = pytest.mark.unit


#: Três modelos que cobrem os três estados possíveis de preço: declarado com
#: valor, declarado zerado e ausente da tabela. Os identificadores são de teste;
#: os reais entram na T-14, com o usuário, a partir do painel do fornecedor.
REGISTRO = textwrap.dedent(
    """
    providers:
      - id: nuvem
        enabled: true
        type: cloud
        base_url: http://127.0.0.1:9
        api_key_env: DEVCOCKPIT_AI_KEY_TESTE
      - id: local
        enabled: true
        type: local
        base_url: http://127.0.0.1:11434

    modelos:
      - id: com-preco
        model: modelo-com-preco
        capabilities: [coding]
        providers: [nuvem]
        cost_tier: low
        context_window: 64000
      - id: sem-preco
        model: modelo-sem-preco
        capabilities: [coding]
        providers: [nuvem]
        cost_tier: high
        context_window: 128000
      - id: caseiro
        model: modelo-caseiro
        capabilities: [coding]
        providers: [local]
        cost_tier: free
        context_window: 32000

    precos:
      com-preco:
        input_por_milhao: 0.27
        output_por_milhao: 1.10
        anotado_em: "2026-09-03"
      caseiro:
        input_por_milhao: 0.0
        output_por_milhao: 0.0
        anotado_em: "2026-09-01"
    """
)


@pytest.fixture
def registro(tmp_path: Path) -> AiConfig:
    caminho = tmp_path / "ai.yml"
    caminho.write_text(REGISTRO, encoding="utf-8")
    return AiConfig.load(caminho)


# --- modelo com preço: valor coerente e data junto ------------------------


def test_custo_bate_com_tokens_vezes_preco(registro: AiConfig) -> None:
    custo = estimar("com-preco", 1_000_000, 500_000, config=registro)

    # 1M × 0.27 + 0.5M × 1.10, com o preço declarado por milhão.
    assert custo.valor == pytest.approx(0.82)
    assert custo.medido


def test_entrada_e_saida_usam_precos_diferentes(registro: AiConfig) -> None:
    """Um preço só para os dois lados erraria sempre, e sempre em silêncio."""
    so_entrada = estimar("com-preco", 1_000_000, 0, config=registro)
    so_saida = estimar("com-preco", 0, 1_000_000, config=registro)

    assert so_entrada.valor == pytest.approx(0.27)
    assert so_saida.valor == pytest.approx(1.10)


def test_custo_vem_com_a_data_da_tabela(registro: AiConfig) -> None:
    """Sem a data, o número na tela não diz de quando é o preço (REQ-11)."""
    custo = estimar("com-preco", 1_000, 1_000, config=registro)

    assert custo.price_date == "2026-09-03"


def test_centesimos_de_centavo_sobrevivem_ao_arredondamento(registro: AiConfig) -> None:
    """`Numeric(12, 6)` é o destino: a casa relevante não pode sumir na conta."""
    custo = estimar("com-preco", 1_000, 0, config=registro)

    assert custo.valor == pytest.approx(0.00027)
    assert custo.valor != 0.0


def test_pergunta_sem_tokens_consumidos_custa_zero_medido(registro: AiConfig) -> None:
    """Zero por consumo zero é medição, e por isso continua vindo com data."""
    custo = estimar("com-preco", 0, 0, config=registro)

    assert custo.valor == 0.0
    assert custo.price_date == "2026-09-03"
    assert custo.medido


# --- P-02: sem preço é null, nunca zero -----------------------------------


def test_modelo_sem_preco_declarado_devolve_none(registro: AiConfig) -> None:
    custo = estimar("sem-preco", 1_000_000, 1_000_000, config=registro)

    assert custo.valor is None
    assert custo.price_date is None
    assert not custo.medido


def test_modelo_desconhecido_devolve_none(registro: AiConfig) -> None:
    """Modelo que nem está no registro faz a mesma afirmação: não há preço."""
    assert estimar("modelo-que-nao-existe", 500, 500, config=registro) == NAO_MEDIDO


def test_registro_vazio_nao_inventa_custo() -> None:
    """Sem `configs/ai.yml` não há tabela — e ausência de tabela não é gratuidade."""
    assert estimar("com-preco", 1_000_000, 1_000_000, config=AiConfig()) == NAO_MEDIDO


def test_preco_zero_declarado_e_medicao_valida(registro: AiConfig) -> None:
    """O modelo local custa zero de verdade: alguém anotou isso, e datou."""
    custo = estimar("caseiro", 2_000_000, 3_000_000, config=registro)

    assert custo.valor == 0.0
    assert custo.price_date == "2026-09-01"
    assert custo.medido


def test_nenhum_caminho_produz_zero_por_ausencia_de_dado(registro: AiConfig) -> None:
    """Percorre os três estados de preço e separa "custou zero" de "não medido".

    Zero só pode sair de preço declarado; e todo valor devolvido chega com a data
    da tabela que o produziu, porque é ela que autoriza a tela a exibi-lo.
    """
    modelos = ["com-preco", "sem-preco", "caseiro", "modelo-que-nao-existe"]
    consumos = [(0, 0), (1, 1), (1_000, 250), (2_000_000, 1_000_000)]

    for modelo_id in modelos:
        tem_preco = registro.preco(modelo_id) is not None
        for tokens_in, tokens_out in consumos:
            custo = estimar(modelo_id, tokens_in, tokens_out, config=registro)

            assert custo.medido is tem_preco
            assert (custo.valor is None) == (custo.price_date is None)
            if not tem_preco:
                assert custo.valor is None, f"{modelo_id} sem preço não pode virar número"
            if custo.valor == 0.0:
                assert custo.price_date, f"{modelo_id} devolveu zero sem data de preço"
