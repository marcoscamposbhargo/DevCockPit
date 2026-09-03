"""O registro declarativo de providers e modelos (REQ-01 a REQ-04).

Três coisas precisam ser verdade ao mesmo tempo, e é fácil quebrar uma
consertando outra: o arquivo é opcional (a instalação de ontem continua
abrindo), ele nunca guarda chave (P-05), e um erro dentro dele não pode
derrubar a inicialização do painel (P-06).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.services.ai.registry import (
    AiConfig,
    AiConfigInvalida,
    get_ai_config,
)

pytestmark = pytest.mark.unit


REGISTRO = textwrap.dedent(
    """
    providers:
      - id: nuvem-a
        enabled: true
        type: cloud
        base_url: http://127.0.0.1:9
        api_key_env: DEVCOCKPIT_AI_KEY_TESTE
      - id: nuvem-b
        enabled: false
        type: cloud
        base_url: http://127.0.0.1:9
        api_key_env: DEVCOCKPIT_AI_KEY_DESLIGADA
      - id: local
        enabled: true
        type: local
        base_url: http://127.0.0.1:11434

    modelos:
      - id: barato
        model: modelo-barato
        capabilities: [coding, qa]
        providers: [nuvem-a, local]
        cost_tier: low
        context_window: 64000
      - id: desligado
        model: modelo-desligado
        capabilities: [coding]
        providers: [nuvem-b]
        cost_tier: high
        context_window: 128000
      - id: caseiro
        model: modelo-caseiro
        capabilities: [coding, debugging]
        providers: [local]
        cost_tier: free
        context_window: 32000

    precos:
      barato:
        input_por_milhao: 0.27
        output_por_milhao: 1.1
        anotado_em: "2026-09-03"

    fallback:
      - barato
      - desligado
      - caseiro

    roteamento:
      limiar_complexidade: 40
      modelo_padrao: barato
    """
)


def _escrever(tmp_path: Path, conteudo: str) -> Path:
    caminho = tmp_path / "ai.yml"
    caminho.write_text(textwrap.dedent(conteudo), encoding="utf-8")
    return caminho


@pytest.fixture
def registro(tmp_path: Path) -> AiConfig:
    return AiConfig.load(_escrever(tmp_path, REGISTRO))


@pytest.fixture
def cache_limpo():  # type: ignore[no-untyped-def]
    """`get_settings` e `get_ai_config` são `lru_cache`: sujam entre testes."""
    get_settings.cache_clear()
    get_ai_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_ai_config.cache_clear()


# --- REQ-04: o arquivo é opcional ----------------------------------------


def test_arquivo_ausente_devolve_registro_vazio(tmp_path: Path) -> None:
    config = AiConfig.load(tmp_path / "nao-existe.yml")

    assert not config.ativo
    assert config.erro == ""
    assert config.providers_habilitados() == ()
    assert config.modelos_por_capacidade("coding") == ()
    assert config.cadeia_fallback() == ()
    assert config.preco("qualquer") is None


def test_settings_tem_o_caminho_e_o_teto_de_tentativas() -> None:
    settings = Settings()

    assert settings.ai_config_file == Path("./configs/ai.yml")
    assert settings.ai_max_attempts == 3


def test_fabrica_com_arquivo_ausente_nao_levanta(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch, cache_limpo
) -> None:
    monkeypatch.setenv("DEVCOCKPIT_AI_CONFIG_FILE", str(tmp_path / "nao-existe.yml"))

    assert not get_ai_config().ativo


def test_yaml_malformado_nao_derruba_a_inicializacao(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch, cache_limpo
) -> None:
    """O painel abre; a IA reporta o motivo. Nunca o contrário (P-06)."""
    caminho = _escrever(tmp_path, "providers: [\n  - id: quebrado\n")
    monkeypatch.setenv("DEVCOCKPIT_AI_CONFIG_FILE", str(caminho))

    config = get_ai_config()

    assert not config.ativo
    assert "ai.yml" in config.erro


def test_load_de_yaml_malformado_levanta_nomeando_o_arquivo(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, "providers: [\n  - id: quebrado\n")

    with pytest.raises(AiConfigInvalida, match="ai.yml"):
        AiConfig.load(caminho)


# --- REQ-01: provider desabilitado sai de tudo ----------------------------


def test_apenas_o_provider_habilitado_aparece(registro: AiConfig) -> None:
    assert [item.id for item in registro.providers_habilitados()] == ["nuvem-a", "local"]
    assert registro.ativo


def test_provider_desabilitado_sai_das_decisoes_de_roteamento(registro: AiConfig) -> None:
    """O modelo servido só por ele some da capacidade e da cadeia de fallback."""
    assert registro.modelo("desligado") is not None
    assert registro.providers_do_modelo("desligado") == ()
    assert "desligado" not in [m.id for m in registro.modelos_por_capacidade("coding")]
    assert "desligado" not in [m.id for m in registro.cadeia_fallback()]


# --- REQ-02: o registro de modelos ---------------------------------------


def test_consulta_por_capacidade_devolve_na_ordem_declarada(registro: AiConfig) -> None:
    assert [m.id for m in registro.modelos_por_capacidade("coding")] == ["barato", "caseiro"]
    assert [m.id for m in registro.modelos_por_capacidade("debugging")] == ["caseiro"]
    assert registro.modelos_por_capacidade("astrologia") == ()


def test_providers_do_modelo_respeitam_a_ordem_declarada(registro: AiConfig) -> None:
    assert [p.id for p in registro.providers_do_modelo("barato")] == ["nuvem-a", "local"]


def test_o_nome_real_do_modelo_vive_so_no_arquivo(registro: AiConfig) -> None:
    modelo = registro.modelo("caseiro")
    assert modelo is not None
    assert modelo.model == "modelo-caseiro"
    assert modelo.cost_tier == "free"
    assert modelo.context_window == 32000


def test_cadeia_de_fallback_sai_na_ordem_declarada(registro: AiConfig) -> None:
    assert [m.id for m in registro.cadeia_fallback()] == ["barato", "caseiro"]


def test_limiares_do_router_saem_do_arquivo(registro: AiConfig) -> None:
    assert registro.roteamento.limiar_complexidade == 40
    assert registro.roteamento.modelo_padrao == "barato"


def test_preco_ausente_e_none_e_nunca_zero(registro: AiConfig) -> None:
    """P-02: modelo sem preço declarado é 'não medido', não custo zero."""
    preco = registro.preco("barato")
    assert preco is not None
    assert preco.input_por_milhao == 0.27
    assert preco.anotado_em == "2026-09-03"
    assert registro.preco("caseiro") is None


def test_o_exemplo_versionado_carrega() -> None:
    """Se o exemplo não carrega, ele documenta um formato que não existe."""
    config = AiConfig.load(PROJECT_ROOT / "configs" / "ai.example.yml")

    assert config.ativo
    assert [p.id for p in config.providers_habilitados()] == ["deepseek", "moonshot", "local"]
    assert config.roteamento.limiar_complexidade == 40


# --- REQ-03: nenhuma chave dentro do arquivo ------------------------------


@pytest.mark.parametrize("campo", ["api_key", "apiKey", "token", "secret", "password", "chave"])
def test_campo_de_segredo_levanta_nomeando_o_arquivo(tmp_path: Path, campo: str) -> None:
    caminho = _escrever(
        tmp_path,
        f"""
        providers:
          - id: nuvem
            enabled: true
            type: cloud
            base_url: http://127.0.0.1:9
            {campo}: valor-qualquer
        """,
    )

    with pytest.raises(AiConfigInvalida, match="ai.yml") as erro:
        AiConfig.load(caminho)

    assert "api_key_env" in erro.value.message


def test_valor_com_cara_de_chave_levanta(tmp_path: Path) -> None:
    caminho = _escrever(
        tmp_path,
        """
        providers:
          - id: nuvem
            enabled: true
            type: cloud
            base_url: sk-abcdef0123456789
            api_key_env: DEVCOCKPIT_AI_KEY_TESTE
        """,
    )

    with pytest.raises(AiConfigInvalida, match="ai.yml"):
        AiConfig.load(caminho)


def test_o_erro_nao_ecoa_o_valor_da_chave(tmp_path: Path) -> None:
    """O erro vira linha de log; ecoar a chave a vazaria onde não podia estar."""
    caminho = _escrever(
        tmp_path,
        """
        providers:
          - id: nuvem
            enabled: true
            type: cloud
            base_url: http://127.0.0.1:9
            api_key: sk-segredoquenaopodevazar
        """,
    )

    with pytest.raises(AiConfigInvalida) as erro:
        AiConfig.load(caminho)

    assert "sk-segredoquenaopodevazar" not in erro.value.message


def test_api_key_env_e_aceito_porque_e_so_o_nome_da_variavel(registro: AiConfig) -> None:
    provider = registro.provider("nuvem-a")
    assert provider is not None
    assert provider.api_key_env == "DEVCOCKPIT_AI_KEY_TESTE"


# --- arquivo declarado errado: erro nomeia o arquivo, e nada mais quebra ---


@pytest.mark.parametrize(
    "conteudo",
    [
        # provider sem type válido
        "providers:\n  - id: nuvem\n    type: hibrido\n    base_url: x\n",
        # modelo apontando para provider que não existe
        (
            "providers:\n  - id: nuvem\n    type: cloud\n    base_url: x\n"
            "modelos:\n  - id: m\n    model: n\n    providers: [fantasma]\n    cost_tier: low\n"
        ),
        # cadeia de fallback citando modelo não declarado
        (
            "providers:\n  - id: nuvem\n    type: cloud\n    base_url: x\n"
            "fallback:\n  - fantasma\n"
        ),
        # modelo_padrao não declarado
        (
            "providers:\n  - id: nuvem\n    type: cloud\n    base_url: x\n"
            "roteamento:\n  modelo_padrao: fantasma\n"
        ),
    ],
)
def test_declaracao_incoerente_levanta_nomeando_o_arquivo(tmp_path: Path, conteudo: str) -> None:
    with pytest.raises(AiConfigInvalida, match="ai.yml"):
        AiConfig.load(_escrever(tmp_path, conteudo))
