"""As rotas de IA: providers, modelos, saúde e consumo (REQ-12, REQ-13, REQ-14).

Aqui há socket de verdade, e é de propósito: o que estas rotas prometem é
sobreviver a um provider fora do ar, e provider fora do ar é uma conexão
recusada — não um dublê devolvendo exceção. Um servidor de imitação sobe em
`127.0.0.1`, e a porta "caída" é uma porta livre que ninguém está escutando.

O outro compromisso é o da constituição: **nenhuma das três rotas devolve o
valor de uma chave, nem parcialmente mascarado** (P-05). Por isso uma chave de
teste é plantada no ambiente e a resposta inteira é varrida atrás dela.

A seção de consumo, no fim do arquivo, não usa socket nenhum: ela lê o banco de
teste e cobra da rota o **P-02** — período sem execução registrada não pode
virar uma tela de zeros.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.ai_run import AiRun, RunStatus
from app.models.base import utcnow
from app.services.ai.registry import get_ai_config

pytestmark = pytest.mark.integration

#: Plantada no ambiente com a cara de uma chave real. Se qualquer rota a
#: devolver, inteira ou em pedaço, a varredura abaixo falha.
CHAVE_DE_TESTE = "sk-plantada-para-nunca-vazar-123456"
CHAVE_ENV = "DEVCOCKPIT_AI_KEY_TESTE"

#: Nada aqui é identificador real de fornecedor: nome de modelo vive no YAML da
#: instalação, e este YAML é de mentira.
REGISTRO = """
providers:
  - id: no-ar
    enabled: true
    type: cloud
    base_url: "{servidor}"
    api_key_env: {chave_env}

  - id: fora-do-ar
    enabled: true
    type: cloud
    base_url: "http://127.0.0.1:{porta_fechada}"
    api_key_env: {chave_env}

  - id: sem-chave
    enabled: true
    type: cloud
    base_url: "{servidor}"
    api_key_env: DEVCOCKPIT_AI_KEY_QUE_NINGUEM_DEFINIU

  - id: dormindo
    enabled: false
    type: local
    base_url: "http://127.0.0.1:11434"

modelos:
  - id: modelo-de-imitacao
    model: imitacao-rapida
    capabilities: [coding, testing]
    providers: [no-ar, fora-do-ar]
    cost_tier: low
    context_window: 8192

  - id: modelo-desligado
    model: imitacao-parada
    capabilities: [coding]
    providers: [dormindo]
    cost_tier: free
    context_window: 4096
"""


class Imitacao(BaseHTTPRequestHandler):
    """Servidor que lista modelos como uma API compatível com OpenAI.

    `demora_s` existe para provar o timeout curto da sondagem: um provider que
    aceita a conexão e some é pior que um que recusa, porque prende quem chamou.
    """

    demora_s: float = 0.0
    recebido: dict = {}

    def log_message(self, *_args) -> None:  # silêncio na suíte
        pass

    def do_GET(self) -> None:  # noqa: N802 - assinatura da biblioteca
        Imitacao.recebido = {"path": self.path, "headers": dict(self.headers)}
        if Imitacao.demora_s:
            time.sleep(Imitacao.demora_s)
        bruto = json.dumps({"data": [{"id": "imitacao-rapida"}, {"id": "imitacao-lenta"}]})
        corpo = bruto.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def servidor():  # type: ignore[no-untyped-def]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Imitacao)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    Imitacao.demora_s = 0.0
    Imitacao.recebido = {}
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def porta_fechada() -> int:
    """Uma porta livre — o sistema a dá e ninguém passa a escutar nela."""
    with socket.socket() as tomada:
        tomada.bind(("127.0.0.1", 0))
        return int(tomada.getsockname()[1])


@pytest.fixture
def cache_limpo():  # type: ignore[no-untyped-def]
    """`get_settings` e `get_ai_config` são `lru_cache`: sujam entre testes."""
    get_settings.cache_clear()
    get_ai_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_ai_config.cache_clear()


@pytest.fixture
def registro(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch, servidor: str, porta_fechada: int, cache_limpo
) -> Path:
    caminho = tmp_path / "ai.yml"
    caminho.write_text(
        REGISTRO.format(servidor=servidor, porta_fechada=porta_fechada, chave_env=CHAVE_ENV),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVCOCKPIT_AI_CONFIG_FILE", str(caminho))
    monkeypatch.setenv(CHAVE_ENV, CHAVE_DE_TESTE)
    # Conexão recusada no loopback custa ~2,3 s nesta plataforma (medido): o
    # Windows reenvia o SYN antes de desistir. É exatamente o que justifica o
    # timeout curto da sondagem — e é caro demais para a suíte pagar em cada
    # teste, por isso aqui ele é ainda menor.
    monkeypatch.setattr("app.api.routes.ai.TIMEOUT_HEALTH_S", 0.5)
    get_settings.cache_clear()
    get_ai_config.cache_clear()
    return caminho


@pytest.fixture
def sem_registro(tmp_path: Path, monkeypatch, cache_limpo) -> None:  # type: ignore[no-untyped-def]
    """Instalação sem `configs/ai.yml` no disco — o caso do REQ-04."""
    monkeypatch.setenv("DEVCOCKPIT_AI_CONFIG_FILE", str(tmp_path / "nao-existe.yml"))
    get_settings.cache_clear()
    get_ai_config.cache_clear()


def por_id(itens: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in itens}


# --- REQ-13: saúde ---------------------------------------------------------


def test_health_marca_um_disponivel_e_o_outro_indisponivel_com_motivo(
    registro: Path, client: TestClient
) -> None:
    """O critério de aceite do REQ-13, ao pé da letra.

    Um provider apontando para porta fechada não derruba a rota: ela devolve
    200, marca aquele como indisponível **com motivo**, e o que respondeu
    continua normal, com os modelos que ele mesmo listou.
    """
    resposta = client.get("/api/ai/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    itens = por_id(corpo["items"])

    assert itens["no-ar"]["disponivel"] is True
    assert itens["no-ar"]["motivo"] is None
    assert itens["no-ar"]["modelos"] == ["imitacao-rapida", "imitacao-lenta"]
    assert itens["no-ar"]["latencia_ms"] is not None

    assert itens["fora-do-ar"]["disponivel"] is False
    assert itens["fora-do-ar"]["motivo"], "indisponível sem motivo não explica nada"
    # P-02: não existe latência de quem não respondeu, e zero seria afirmação.
    assert itens["fora-do-ar"]["latencia_ms"] is None
    assert itens["fora-do-ar"]["modelos"] == []


def test_health_so_olha_provider_habilitado(registro: Path, client: TestClient) -> None:
    """`enabled: false` está fora de toda decisão — inclusive da sondagem."""
    itens = por_id(client.get("/api/ai/health").json()["items"])

    assert "dormindo" not in itens
    assert set(itens) == {"no-ar", "fora-do-ar", "sem-chave"}


def test_health_nao_espera_o_provider_que_nao_responde(
    registro: Path, client: TestClient, monkeypatch
) -> None:
    """Timeout curto: provider que aceita a conexão e some não segura a rota.

    Conversa espera 120 s porque modelo pensa devagar. Aqui quem espera é a tela
    de configurações abrindo, e o teto é medido — não declarado.
    """
    monkeypatch.setattr("app.api.routes.ai.TIMEOUT_HEALTH_S", 0.2)
    Imitacao.demora_s = 2.0

    inicio = time.perf_counter()
    resposta = client.get("/api/ai/health")
    decorrido = time.perf_counter() - inicio

    assert resposta.status_code == 200
    assert decorrido < 1.5, f"a sondagem segurou a rota por {decorrido:.1f}s"
    assert por_id(resposta.json()["items"])["no-ar"]["disponivel"] is False


def test_provider_sem_chave_no_ambiente_nao_e_sondado(
    registro: Path, client: TestClient
) -> None:
    """Sem a variável definida não há o que perguntar: a falta é a resposta."""
    item = por_id(client.get("/api/ai/health").json()["items"])["sem-chave"]

    assert item["disponivel"] is False
    assert "DEVCOCKPIT_AI_KEY_QUE_NINGUEM_DEFINIU" in item["motivo"]


# --- REQ-14: os quatro estados --------------------------------------------


def test_providers_traz_os_quatro_estados(registro: Path, client: TestClient) -> None:
    resposta = client.get("/api/ai/providers")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ativo"] is True
    assert corpo["erro"] is None

    itens = por_id(corpo["items"])
    assert itens["no-ar"]["estado"] == "conectado"
    assert itens["fora-do-ar"]["estado"] == "indisponivel"
    assert itens["sem-chave"]["estado"] == "nao_configurado"
    assert itens["dormindo"]["estado"] == "desligado"
    # Provider desligado continua listado: a tela precisa mostrar que ele
    # existe e está desligado, e não fingir que nunca foi declarado.
    assert itens["dormindo"]["enabled"] is False
    assert itens["no-ar"]["modelos"] == ["modelo-de-imitacao"]


def test_providers_devolve_o_nome_da_variavel_e_nada_mais(
    registro: Path, client: TestClient
) -> None:
    itens = por_id(client.get("/api/ai/providers").json()["items"])

    assert itens["no-ar"]["api_key_env"] == CHAVE_ENV


# --- REQ-02 na rota: o registro de modelos --------------------------------


def test_models_devolve_capacidades_providers_em_ordem_e_custo(
    registro: Path, client: TestClient
) -> None:
    resposta = client.get("/api/ai/models")

    assert resposta.status_code == 200
    itens = por_id(resposta.json()["items"])
    modelo = itens["modelo-de-imitacao"]

    assert modelo["capabilities"] == ["coding", "testing"]
    # A ordem é a preferência declarada no arquivo, e o runner consome de cima
    # para baixo: inverter aqui inverteria a cadeia inteira.
    assert modelo["providers"] == ["no-ar", "fora-do-ar"]
    assert modelo["cost_tier"] == "low"
    assert modelo["context_window"] == 8192


# --- P-05: a chave não sai por rota nenhuma -------------------------------


@pytest.mark.parametrize("rota", ["/api/ai/providers", "/api/ai/models", "/api/ai/health"])
def test_nenhuma_rota_devolve_a_chave_nem_um_pedaco_dela(
    registro: Path, client: TestClient, rota: str
) -> None:
    """Varredura da resposta inteira atrás da chave plantada (P-05).

    Procura o valor inteiro e também qualquer pedaço grande dele, que é o que
    um mascaramento parcial ("sk-plan…3456") deixaria escapar. O que pode
    aparecer é o **nome** da variável de ambiente.
    """
    resposta = client.get(rota)

    assert resposta.status_code == 200
    bruto = resposta.text
    assert CHAVE_DE_TESTE not in bruto
    pedacos = [CHAVE_DE_TESTE[:8], CHAVE_DE_TESTE[-8:], CHAVE_DE_TESTE[10:22]]
    for pedaco in pedacos:
        assert pedaco not in bruto, f"a rota {rota} devolveu um pedaço da chave: {pedaco}"


def test_a_chave_chega_ao_provider_mas_nao_volta_para_a_tela(
    registro: Path, client: TestClient
) -> None:
    """A sondagem se autentica de verdade — e é só ali que a chave aparece."""
    client.get("/api/ai/health")

    assert Imitacao.recebido["headers"].get("Authorization") == f"Bearer {CHAVE_DE_TESTE}"
    assert CHAVE_DE_TESTE not in client.get("/api/ai/health").text


# --- REQ-04: sem o arquivo no disco ---------------------------------------


@pytest.mark.parametrize("rota", ["/api/ai/providers", "/api/ai/models", "/api/ai/health"])
def test_sem_arquivo_de_registro_as_rotas_respondem_vazio(
    sem_registro: None, client: TestClient, rota: str
) -> None:
    """Arquivo ausente é estado normal: lista vazia, 200, e o painel abre."""
    resposta = client.get(rota)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["items"] == []
    if rota != "/api/ai/health":
        assert corpo["ativo"] is False
        assert corpo["erro"] is None


# --- REQ-12: consumo do período -------------------------------------------
#
# O compromisso desta seção é o **P-02**: banco vazio não vira tela de zeros.
# Um período sem execução registrada não é um período de graça, sem erro e sem
# fallback — é um período que ninguém mediu, e a rota precisa dizer isso.

#: Registro só para os testes de consumo: o de cima não declara nenhum provider
#: local, e local × nuvem é justamente o que aqui precisa ser exercitado. O
#: `local-aposentado` está desligado de propósito — desligar o Ollama hoje não
#: pode transformar em nuvem o que ele processou ontem.
REGISTRO_DE_CONSUMO = """
providers:
  - id: local-de-imitacao
    enabled: true
    type: local
    base_url: "http://127.0.0.1:11434"

  - id: local-aposentado
    enabled: false
    type: local
    base_url: "http://127.0.0.1:11435"

  - id: nuvem-de-imitacao
    enabled: true
    type: cloud
    base_url: "http://127.0.0.1:9"

modelos:
  - id: modelo-de-imitacao
    model: imitacao-rapida
    capabilities: [coding]
    providers: [local-de-imitacao, nuvem-de-imitacao]
    cost_tier: low
    context_window: 8192
"""


@pytest.fixture
def registro_de_consumo(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch, cache_limpo
) -> Path:
    caminho = tmp_path / "ai-consumo.yml"
    caminho.write_text(REGISTRO_DE_CONSUMO, encoding="utf-8")
    monkeypatch.setenv("DEVCOCKPIT_AI_CONFIG_FILE", str(caminho))
    get_settings.cache_clear()
    get_ai_config.cache_clear()
    return caminho


def execucao(**campos) -> AiRun:  # type: ignore[no-untyped-def]
    base = {
        "correlation_id": "c-1",
        "attempt": 1,
        "provider": "local-de-imitacao",
        "model": "imitacao-rapida",
        "task_type": "code_review",
        "tokens_in": 100,
        "tokens_out": 50,
        "latency_ms": 900,
        "status": RunStatus.OK.value,
    }
    base.update(campos)
    return AiRun(**base)


def gravar(client: TestClient, *linhas: AiRun) -> None:
    """Grava direto no banco do app de teste — a gravação é da T-09."""
    sessao = client.app.state.session_factory()
    try:
        sessao.add_all(list(linhas))
        sessao.commit()
    finally:
        sessao.close()


def cadeia_de_exemplo() -> list[AiRun]:
    """Duas perguntas: a primeira caiu para a nuvem, a segunda foi local.

    Contém de propósito uma tentativa `skipped` — o candidato que a cadeia nem
    chegou a tentar — porque ela é a que mais facilmente vira zero indevido:
    não é falha e não tem latência para entrar em média nenhuma.
    """
    return [
        execucao(
            attempt=1,
            provider="local-de-imitacao",
            tokens_in=100,
            tokens_out=50,
            latency_ms=30_000,
            status=RunStatus.TIMEOUT.value,
            error="tempo esgotado",
        ),
        execucao(
            attempt=2,
            provider="nuvem-de-imitacao",
            tokens_in=200,
            tokens_out=300,
            latency_ms=1_000,
            estimated_cost=0.002,
            price_date="2026-09-01",
        ),
        execucao(
            attempt=3,
            provider="local-aposentado",
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            status=RunStatus.SKIPPED.value,
        ),
        execucao(
            correlation_id="c-2",
            provider="local-aposentado",
            tokens_in=10,
            tokens_out=20,
            latency_ms=500,
            estimated_cost=0.001,
            price_date="2026-09-03",
        ),
    ]


def numeros_do_corpo(valor: object, caminho: str = "") -> list[tuple[str, float]]:
    """Todo número do JSON, com o caminho onde ele estava.

    A varredura é recursiva e cega de propósito: ela pega campo que ainda nem
    existe. Listar os campos à mão faria o teste cobrir só os que alguém lembrou
    de listar, que é exatamente por onde um zero inventado entraria depois.

    `bool` fica de fora porque em Python `False == 0`, e `medido: false` é
    resposta legítima — não é indicador zerado.
    """
    if valor is None or isinstance(valor, bool):
        return []
    if isinstance(valor, int | float):
        return [(caminho or "<raiz>", float(valor))]
    if isinstance(valor, dict):
        return [
            achado
            for chave, item in valor.items()
            for achado in numeros_do_corpo(item, f"{caminho}.{chave}" if caminho else str(chave))
        ]
    if isinstance(valor, list):
        return [
            achado
            for indice, item in enumerate(valor)
            for achado in numeros_do_corpo(item, f"{caminho}[{indice}]")
        ]
    return []


def test_banco_vazio_nao_traz_zero_em_indicador_nenhum(
    registro_de_consumo: Path, client: TestClient
) -> None:
    """O teste que decide a task (**P-02**).

    Sem execução registrada, **nenhum** indicador pode vir preenchido: nem
    chamadas, nem tokens, nem custo, nem falhas, nem fallbacks. E a varredura
    não é só do bloco de indicadores — é do corpo inteiro, atrás de qualquer
    número zerado que tenha escapado para fora dele. O único número que pode
    aparecer é a janela pedida, que não é medição, é parâmetro.
    """
    resposta = client.get("/api/ai/usage")

    assert resposta.status_code == 200
    corpo = resposta.json()

    assert corpo["medido"] is False
    assert corpo["motivo"], "não medido sem motivo não diz o que falta para medir"

    indicadores = corpo["indicadores"]
    assert indicadores, "a resposta precisa trazer o bloco de indicadores"
    preenchidos = {nome: valor for nome, valor in indicadores.items() if valor is not None}
    assert preenchidos == {}, f"indicador afirmado sem dado: {preenchidos}"

    zerados = [caminho for caminho, valor in numeros_do_corpo(corpo) if valor == 0]
    assert zerados == [], f"o corpo trouxe zero por ausência de dado em: {zerados}"
    assert [caminho for caminho, _ in numeros_do_corpo(corpo)] == ["days"]


def test_sem_registro_o_motivo_diz_que_a_ia_nao_esta_configurada(
    sem_registro: None, client: TestClient
) -> None:
    """Sem `configs/ai.yml` a causa é outra, e a tela precisa da causa certa.

    "Nenhuma pergunta esta semana" e "a IA não tem como rodar" levam a ações
    diferentes de quem lê.
    """
    corpo = client.get("/api/ai/usage").json()

    assert corpo["medido"] is False
    assert "configs/ai.yml" in corpo["motivo"]


def test_periodo_com_dados_traz_todos_os_campos_do_req_12(
    registro_de_consumo: Path, client: TestClient
) -> None:
    """Com dados, nenhum campo fica em `None` — e as contas batem."""
    gravar(client, *cadeia_de_exemplo())

    corpo = client.get("/api/ai/usage").json()

    assert corpo["medido"] is True
    assert corpo["motivo"] is None
    indicadores = corpo["indicadores"]
    faltando = [nome for nome, valor in indicadores.items() if valor is None]
    assert faltando == [], f"campo do REQ-12 sem valor com dados no período: {faltando}"

    assert indicadores["chamadas"] == 4
    assert indicadores["perguntas"] == 2
    assert indicadores["tokens_in"] == 310
    assert indicadores["tokens_out"] == 370
    # `local-aposentado` está desligado no registro e continua contando como
    # local: o que se mede é onde o token foi processado.
    assert (indicadores["chamadas_local"], indicadores["tokens_local"]) == (3, 180)
    assert (indicadores["chamadas_cloud"], indicadores["tokens_cloud"]) == (1, 500)
    assert indicadores["custo_estimado"] == pytest.approx(0.003)
    # Custo nunca aparece sem a data da tabela que o produziu (REQ-11).
    assert indicadores["price_date"] == "2026-09-03"
    assert indicadores["chamadas_sem_custo"] == 2
    # Só as três executadas: (30000 + 1000 + 500) / 3. A `skipped` não tem
    # latência, e contá-la como 0 inventaria velocidade.
    assert indicadores["latencia_media_ms"] == pytest.approx(10_500)
    # `skipped` também não é falha: é candidato que a cadeia nem tentou.
    assert indicadores["falhas"] == 1
    assert indicadores["fallbacks"] == 1


def test_fallback_acionado_conta_pergunta_e_nao_tentativa(
    registro_de_consumo: Path, client: TestClient
) -> None:
    """A definição do número que vai para a tela, fixada em teste.

    "Fallback acionado" é **pergunta que precisou de mais de uma tentativa**.
    Uma pergunta que passou por três provedores conta uma vez: o que se mede é
    quantas vezes a cadeia precisou existir, não o tamanho dela.
    """
    gravar(
        client,
        execucao(correlation_id="c-longa", attempt=1, status=RunStatus.ERROR.value),
        execucao(correlation_id="c-longa", attempt=2, status=RunStatus.TIMEOUT.value),
        execucao(correlation_id="c-longa", attempt=3, provider="nuvem-de-imitacao"),
        execucao(correlation_id="c-direta", attempt=1),
    )

    indicadores = client.get("/api/ai/usage").json()["indicadores"]

    assert indicadores["chamadas"] == 4
    assert indicadores["perguntas"] == 2
    assert indicadores["fallbacks"] == 1
    assert indicadores["falhas"] == 2


def test_divisao_local_e_nuvem_vem_do_registro_e_nao_do_banco(
    registro: Path, client: TestClient
) -> None:
    """As mesmas linhas, outro registro: a classificação muda com o arquivo.

    A linha de `ai_run` não guarda se o provedor era local ou de nuvem — isso é
    declaração de `configs/ai.yml`. Sob um registro que não declara nenhum
    desses providers como local, tudo conta como nuvem, e nada some da conta.
    """
    gravar(client, *cadeia_de_exemplo())

    indicadores = client.get("/api/ai/usage").json()["indicadores"]

    assert (indicadores["chamadas_local"], indicadores["tokens_local"]) == (0, 0)
    assert (indicadores["chamadas_cloud"], indicadores["tokens_cloud"]) == (4, 680)


def test_nenhum_preco_declarado_deixa_o_custo_nulo_com_as_chamadas_contadas(
    registro_de_consumo: Path, client: TestClient
) -> None:
    """Modelo sem preço não vira gasto zero (**P-02**).

    As chamadas foram medidas e aparecem; o custo não foi, e vem `null` junto de
    quantas chamadas ficaram fora da conta.
    """
    gravar(client, execucao(), execucao(correlation_id="c-2"))

    indicadores = client.get("/api/ai/usage").json()["indicadores"]

    assert indicadores["chamadas"] == 2
    assert indicadores["custo_estimado"] is None
    assert indicadores["price_date"] is None
    assert indicadores["chamadas_sem_custo"] == 2


def test_a_janela_recorta_pelo_parametro_days(
    registro_de_consumo: Path, client: TestClient
) -> None:
    """Fora da janela não entra — e período vazio volta a ser "não medido"."""
    gravar(client, execucao(created_at=utcnow() - timedelta(days=10)))

    assert client.get("/api/ai/usage", params={"days": 1}).json()["medido"] is False

    corpo = client.get("/api/ai/usage", params={"days": 30}).json()
    assert corpo["medido"] is True
    assert corpo["days"] == 30
    assert corpo["indicadores"]["chamadas"] == 1
