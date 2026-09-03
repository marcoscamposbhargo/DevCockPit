"""O Model Router: quem responde a pergunta, e em que ordem tentar (REQ-07, REQ-08).

O teste que mais importa deste arquivo não é o que confere a faixa de
complexidade: é o que prova que uma pergunta marcada como local **não** cai em
provider `type: cloud`. Errar a faixa custa uma resposta mais cara; errar a
privacidade manda para fora o que não podia sair.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.services.ai.classifier import Classificacao, Privacy, TaskType
from app.services.ai.model_router import (
    Candidato,
    Decisao,
    EscolhaManual,
    escolher,
)
from app.services.ai.registry import AiConfig

pytestmark = pytest.mark.unit


REGISTRO = """
    providers:
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
      - id: nuvem-desligada
        enabled: false
        type: cloud
        base_url: http://127.0.0.1:9
        api_key_env: DEVCOCKPIT_AI_KEY_TESTE_C
      - id: caseiro
        enabled: true
        type: local
        base_url: http://127.0.0.1:11434

    modelos:
      - id: barato
        model: modelo-barato
        capabilities: [coding, qa]
        providers: [nuvem-a]
        cost_tier: low
        context_window: 64000
      - id: janelao
        model: modelo-janelao
        capabilities: [coding, qa, architecture]
        providers: [nuvem-b, nuvem-a]
        cost_tier: high
        context_window: 200000
      - id: desligado
        model: modelo-desligado
        capabilities: [coding, documentation]
        providers: [nuvem-desligada]
        cost_tier: free
        context_window: 500000
      - id: local-codigo
        model: modelo-caseiro
        capabilities: [coding, debugging]
        providers: [caseiro]
        cost_tier: free
        context_window: 32768

    fallback:
      - barato
      - janelao
      - local-codigo

    roteamento:
      limiar_complexidade: 40
      modelo_padrao: barato
"""

#: O mesmo registro sem nenhum provider local habilitado. É com ele que se prova
#: a recusa: a pergunta continua tendo modelo de nuvem disponível e à mão, e
#: mesmo assim não pode ir para lá.
SEM_LOCAL = REGISTRO.replace(
    """      - id: caseiro
        enabled: true
        type: local""",
    """      - id: caseiro
        enabled: false
        type: local""",
)


def _registro(tmp_path: Path, conteudo: str = REGISTRO) -> AiConfig:
    caminho = tmp_path / "ai.yml"
    caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")
    return AiConfig.load(caminho)


def _pergunta(
    complexity: int,
    *,
    task_type: TaskType = "coding",
    privacy: Privacy = "internal",
) -> Classificacao:
    """Classificação sintética: aqui se testa o router, não o classificador."""
    return Classificacao(
        task_type=task_type,
        complexity=complexity,
        privacy=privacy,
        tools_required=False,
    )


def _ids(decisao: Decisao) -> list[str]:
    return [str(candidato) for candidato in decisao.candidatos]


def _nenhum_na_nuvem(candidatos: tuple[Candidato, ...]) -> bool:
    return all(candidato.provider.type != "cloud" for candidato in candidatos)


@pytest.fixture
def registro(tmp_path: Path) -> AiConfig:
    return _registro(tmp_path)


# --- REQ-07, item 2: a complexidade decide -------------------------------


def test_complexidade_baixa_escolhe_o_mais_barato(registro: AiConfig) -> None:
    decisao = escolher(_pergunta(10), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "barato"
    assert decisao.modo == "auto"


def test_complexidade_no_limiar_ainda_escolhe_o_mais_barato(registro: AiConfig) -> None:
    """'Até o limiar' inclui o limiar — 40 é a última complexidade barata."""
    decisao = escolher(_pergunta(40), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "barato"


def test_complexidade_media_escolhe_a_maior_janela(registro: AiConfig) -> None:
    decisao = escolher(_pergunta(50), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "janelao"


def test_complexidade_alta_escolhe_a_maior_janela(registro: AiConfig) -> None:
    decisao = escolher(_pergunta(90), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "janelao"


def test_o_limiar_vem_do_yaml_e_nao_do_codigo(tmp_path: Path) -> None:
    """Mesma pergunta, outro arquivo, outra escolha — sem tocar em código."""
    outro = REGISTRO.replace("limiar_complexidade: 40", "limiar_complexidade: 80")
    registro = _registro(tmp_path, outro)

    decisao = escolher(_pergunta(50), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "barato"


def test_a_lista_e_ordenada_e_expande_provider(registro: AiConfig) -> None:
    """O runner consome de cima para baixo: o segundo já vem decidido."""
    decisao = escolher(_pergunta(90), config=registro)

    assert _ids(decisao) == ["janelao@nuvem-b", "janelao@nuvem-a", "barato@nuvem-a"]


def test_modelo_com_provider_desligado_fica_de_fora(registro: AiConfig) -> None:
    """`desligado` é free e tem a maior janela: venceria os dois critérios."""
    for complexidade in (10, 90):
        decisao = escolher(_pergunta(complexidade), config=registro)

        assert "desligado" not in [candidato.modelo_id for candidato in decisao.candidatos]


def test_modelo_so_local_nao_disputa_o_mais_barato(registro: AiConfig) -> None:
    """`local-codigo` é free, mas o local não entra por economia (nota do REQ-07)."""
    decisao = escolher(_pergunta(10), config=registro)

    assert "local-codigo" not in [candidato.modelo_id for candidato in decisao.candidatos]


# --- REQ-07, item 1: privacidade antes de tudo ---------------------------


def test_privacidade_local_vence_complexidade_alta(registro: AiConfig) -> None:
    decisao = escolher(_pergunta(95, privacy="local"), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "local-codigo"
    assert decisao.escolhido.provider.type == "local"
    assert _nenhum_na_nuvem(decisao.candidatos)
    assert not decisao.recusada


def test_sem_modelo_local_a_pergunta_e_recusada(tmp_path: Path) -> None:
    """O ponto que não admite exceção: recusar, nunca promover para a nuvem."""
    registro = _registro(tmp_path, SEM_LOCAL)

    decisao = escolher(_pergunta(95, privacy="local"), config=registro)

    assert decisao.recusada
    assert decisao.candidatos == ()
    assert _nenhum_na_nuvem(decisao.candidatos)
    assert "não vai para a nuvem" in decisao.recusa


def test_registro_vazio_com_privacidade_local_tambem_recusa() -> None:
    """Sem registro não se sabe quem é local, e o benefício da dúvida é recusar."""
    decisao = escolher(_pergunta(20, privacy="local"), config=AiConfig())

    assert decisao.recusada
    assert decisao.candidatos == ()


def test_escolha_manual_de_nuvem_nao_vence_a_marca_de_privacidade(registro: AiConfig) -> None:
    """Manual vence o roteamento (REQ-08), não o destino (REQ-07, item 1)."""
    decisao = escolher(
        _pergunta(20, privacy="local"),
        EscolhaManual(modelo="janelao", provider="nuvem-b"),
        config=registro,
    )

    assert _nenhum_na_nuvem(decisao.candidatos)
    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "local-codigo"
    assert decisao.modo == "auto"


def test_pergunta_local_de_tipo_sem_modelo_local_nao_recusa(registro: AiConfig) -> None:
    """Nenhum local faz `architecture`; responder devagar ainda é responder."""
    decisao = escolher(_pergunta(90, privacy="local", task_type="architecture"), config=registro)

    assert not decisao.recusada
    assert _nenhum_na_nuvem(decisao.candidatos)
    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "local-codigo"


# --- REQ-08: a escolha manual vence o roteamento automático --------------


def test_escolha_manual_vence_e_marca_manual(registro: AiConfig) -> None:
    """A regra apontaria `barato` nesta complexidade; a pessoa pediu outro."""
    decisao = escolher(_pergunta(10), EscolhaManual(modelo="janelao"), config=registro)

    assert decisao.modo == "manual"
    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "janelao"


def test_provider_manual_recorta_a_escolha_automatica(registro: AiConfig) -> None:
    decisao = escolher(_pergunta(90), EscolhaManual(provider="nuvem-a"), config=registro)

    assert decisao.modo == "manual"
    assert _ids(decisao) == ["janelao@nuvem-a", "barato@nuvem-a"]


def test_auto_e_o_padrao(registro: AiConfig) -> None:
    assert escolher(_pergunta(10), config=registro).modo == "auto"


def test_modelo_manual_desconhecido_cai_no_automatico(registro: AiConfig) -> None:
    """Nome vindo do cliente não vira nome cru no fornecedor (**P-06**)."""
    pedido = EscolhaManual(modelo="modelo-que-nao-existe")
    decisao = escolher(_pergunta(10), pedido, config=registro)

    assert decisao.modo == "auto"
    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "barato"
    assert "não está disponível" in decisao.motivo


# --- REQ-07, item 3: sem a capacidade, o padrão --------------------------


def test_capacidade_ausente_cai_no_padrao_sem_levantar(registro: AiConfig) -> None:
    """Nenhum modelo habilitado declara `planning`."""
    decisao = escolher(_pergunta(70, task_type="planning"), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "barato"
    assert not decisao.recusada
    assert "padrão" in decisao.motivo


def test_capacidade_de_modelo_desligado_nao_conta(registro: AiConfig) -> None:
    """`documentation` só existe em `desligado`, que não tem provider de pé."""
    decisao = escolher(_pergunta(70, task_type="documentation"), config=registro)

    assert decisao.escolhido is not None
    assert decisao.escolhido.modelo_id == "barato"


# --- REQ-04: sem `configs/ai.yml` nada explode ---------------------------


def test_registro_vazio_devolve_lista_vazia_sem_erro() -> None:
    decisao = escolher(_pergunta(50), config=AiConfig())

    assert decisao.candidatos == ()
    assert decisao.escolhido is None
    assert not decisao.recusada
    assert decisao.modo == "auto"


def test_registro_sem_padrao_declarado_nao_levanta(tmp_path: Path) -> None:
    registro = _registro(tmp_path, REGISTRO.replace("modelo_padrao: barato", "modelo_padrao: ''"))

    decisao = escolher(_pergunta(70, task_type="planning"), config=registro)

    assert decisao.candidatos == ()
    assert not decisao.recusada


def test_decisao_recusada_nunca_carrega_candidato(registro: AiConfig) -> None:
    """A rede de segurança do tipo, para o erro não passar por resposta normal."""
    candidato = escolher(_pergunta(10), config=registro).candidatos

    with pytest.raises(ValueError):
        Decisao(candidatos=candidato, modo="auto", motivo="teste", recusa="não pode")
