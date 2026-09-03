"""O provedor falando de verdade — por HTTP, contra um servidor que imita a API.

Testar `_processar_linha` prova que sei ler o formato. Não prova que o cliente
monta a requisição certa, que o stream chega em pedaços, nem que o erro do
provedor vira mensagem acionável. Sem chave de API não dá para exercitar a API
real; dá para exercitar **o meu lado** dela.

O servidor daqui responde no formato de cada provedor. Se um deles mudar o
protocolo, este teste continua passando e o mundo real quebra — por isso ele
prova o cliente, não o contrato do fornecedor.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.services.ai import providers
from app.services.ai.providers import (
    AIRequest,
    AnthropicProvider,
    LocalProvider,
    Message,
    OpenAICompatibleProvider,
    OpenAIProvider,
    ProviderError,
)

pytestmark = pytest.mark.unit

RESPOSTA_ANTHROPIC = [
    '{"type":"message_start","message":{"usage":{"input_tokens":42}}}',
    '{"type":"content_block_delta","delta":{"text":"O painel "}}',
    '{"type":"content_block_delta","delta":{"text":"já sabe."}}',
    '{"type":"message_delta","usage":{"output_tokens":9}}',
]

RESPOSTA_OPENAI = [
    '{"choices":[{"delta":{"content":"O painel "}}]}',
    '{"choices":[{"delta":{"content":"já sabe."}}]}',
    '{"choices":[],"usage":{"prompt_tokens":42,"completion_tokens":9}}',
    "[DONE]",
]

#: DeepSeek: a contagem vem num evento final de `choices` vazio, com campos
#: extras de cache que o cliente não conhece e precisa ignorar sem tropeçar.
RESPOSTA_DEEPSEEK = [
    '{"choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}',
    '{"choices":[{"index":0,"delta":{"content":"O painel "}}]}',
    '{"choices":[{"index":0,"delta":{"content":"já sabe."}}]}',
    '{"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
    '{"choices":[],"usage":{"prompt_tokens":42,"completion_tokens":9,'
    '"prompt_cache_hit_tokens":30,"total_tokens":51}}',
    "[DONE]",
]

#: Kimi (Moonshot): mesma contagem, mas no mesmo evento que fecha a resposta —
#: variação de superfície que o cliente já atravessa, por ler `usage` do evento
#: e não da posição dele no stream.
RESPOSTA_KIMI = [
    '{"object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"}}]}',
    '{"object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"O painel "}}]}',
    '{"object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"já sabe."}}]}',
    '{"object":"chat.completion.chunk","choices":[{"index":0,"delta":{},'
    '"finish_reason":"stop"}],"usage":{"prompt_tokens":42,"completion_tokens":9,'
    '"total_tokens":51}}',
    "[DONE]",
]

SSE_POR_MODO = {
    "anthropic": RESPOSTA_ANTHROPIC,
    "openai": RESPOSTA_OPENAI,
    "deepseek": RESPOSTA_DEEPSEEK,
    "kimi": RESPOSTA_KIMI,
}

#: Nome que cada imitação devolve no campo `model`. Nada aqui é identificador
#: real de fornecedor: o nome do modelo vive no YAML, nunca no código.
MODELO_DA_IMITACAO = {"deepseek": "deepseek-imitacao", "kimi": "kimi-imitacao"}


class Imitacao(BaseHTTPRequestHandler):
    """Servidor que devolve o formato pedido pela rota chamada."""

    recebido: dict = {}
    modo: str = "anthropic"
    status: int = 200

    def log_message(self, *_args) -> None:  # silêncio na suíte
        pass

    def do_GET(self) -> None:  # noqa: N802 - assinatura da biblioteca
        """`/api/tags` do Ollama: o que está instalado na máquina."""
        self._json({"models": [{"name": "llama3.2:1b"}, {"name": "llama3.2:3b"}]})

    def do_POST(self) -> None:  # noqa: N802 - assinatura da biblioteca
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        Imitacao.recebido = {"corpo": corpo, "headers": dict(self.headers), "path": self.path}

        if Imitacao.status >= 400:
            self.send_response(Imitacao.status)
            self.end_headers()
            self.wfile.write(b'{"error":"nao autorizado"}')
            return

        if Imitacao.modo == "local":
            self._responder_local(corpo.get("stream", False))
            return

        linhas = SSE_POR_MODO[Imitacao.modo]
        if corpo.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for linha in linhas:
                self.wfile.write(f"data: {linha}\n\n".encode())
                self.wfile.flush()
            return

        self._json(self._corpo_completo())

    def _responder_local(self, stream: bool) -> None:
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for pedaco in ("O painel ", "já sabe."):
                self.wfile.write(
                    (json.dumps({"message": {"content": pedaco}}) + "\n").encode()
                )
            fim = {"done": True, "prompt_eval_count": 42, "eval_count": 9}
            self.wfile.write((json.dumps(fim) + "\n").encode())
            return
        self._json(
            {
                "message": {"content": "O painel já sabe."},
                "prompt_eval_count": 42,
                "eval_count": 9,
            }
        )

    def _corpo_completo(self) -> dict:
        if Imitacao.modo == "anthropic":
            return {
                "content": [{"type": "text", "text": "O painel já sabe."}],
                "usage": {"input_tokens": 42, "output_tokens": 9},
                "model": "imitacao",
            }
        return {
            "choices": [{"message": {"content": "O painel já sabe."}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 9},
            "model": MODELO_DA_IMITACAO.get(Imitacao.modo, "imitacao"),
        }

    def _json(self, dados: dict) -> None:
        bruto = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)


@pytest.fixture
def servidor():  # type: ignore[no-untyped-def]
    httpd = HTTPServer(("127.0.0.1", 0), Imitacao)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    Imitacao.status = 200
    Imitacao.recebido = {}
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def pedido() -> AIRequest:
    return AIRequest(
        messages=[Message(role="user", content="como está o projeto?")],
        system="instrução do sistema",
        max_output_tokens=500,
    )


def test_anthropic_ponta_a_ponta(servidor: str) -> None:
    Imitacao.modo = "anthropic"
    provedor = AnthropicProvider(api_key="chave-de-teste", model="claude-x", base_url=servidor)

    pedacos = list(provedor.stream(pedido()))

    assert "".join(pedacos) == "O painel já sabe."
    assert len(pedacos) == 2, "chega em pedaços, não de uma vez"
    assert provedor.last_usage.tokens_in == 42
    assert provedor.last_usage.tokens_out == 9

    enviado = Imitacao.recebido
    assert enviado["headers"]["x-api-key"] == "chave-de-teste"
    assert enviado["headers"]["anthropic-version"] == "2023-06-01"
    assert enviado["corpo"]["system"] == "instrução do sistema"
    assert enviado["corpo"]["max_tokens"] == 500


def test_openai_ponta_a_ponta(servidor: str) -> None:
    Imitacao.modo = "openai"
    provedor = OpenAIProvider(api_key="chave-de-teste", model="gpt-x", base_url=servidor)

    pedacos = list(provedor.stream(pedido()))

    assert "".join(pedacos) == "O painel já sabe."
    assert provedor.last_usage.tokens_out == 9

    enviado = Imitacao.recebido
    assert enviado["headers"]["Authorization"] == "Bearer chave-de-teste"
    # Sem isto o stream do OpenAI não devolve contagem, e o custo some da tela.
    assert enviado["corpo"]["stream_options"] == {"include_usage": True}
    assert enviado["corpo"]["messages"][0]["role"] == "system"


def test_local_ponta_a_ponta(servidor: str) -> None:
    Imitacao.modo = "local"
    provedor = LocalProvider(api_key="", model="llama", base_url=servidor)

    pedacos = list(provedor.stream(pedido()))

    assert "".join(pedacos) == "O painel já sabe."
    assert provedor.last_usage.tokens_in == 42
    assert "Authorization" not in Imitacao.recebido["headers"], "local não usa chave"


def test_resposta_sem_stream(servidor: str) -> None:
    Imitacao.modo = "anthropic"
    provedor = AnthropicProvider(api_key="k", model="m", base_url=servidor)

    resposta = provedor.complete(pedido())

    assert resposta.text == "O painel já sabe."
    assert resposta.usage.tokens_in == 42
    assert Imitacao.recebido["corpo"]["stream"] is False


def test_chave_recusada_vira_instrucao(servidor: str) -> None:
    Imitacao.modo = "anthropic"
    Imitacao.status = 401
    provedor = AnthropicProvider(api_key="errada", model="m", base_url=servidor)

    with pytest.raises(ProviderError, match="DEVCOCKPIT_AI_API_KEY"):
        list(provedor.stream(pedido()))


def test_provedor_fora_do_ar_nao_derruba_o_painel() -> None:
    """Endereço morto: erro de domínio com mensagem, não traceback."""
    provedor = AnthropicProvider(api_key="k", model="m", base_url="http://127.0.0.1:1")

    with pytest.raises(ProviderError, match="Falha ao falar com anthropic"):
        list(provedor.stream(pedido()))


# --- provedor local: erro que diz o que fazer ------------------------------


def test_modelo_ausente_no_ollama_lista_os_instalados(servidor: str) -> None:
    """404 do Ollama quase sempre é modelo não baixado.

    A mensagem genérica manda conferir a variável de ambiente, o que não ajuda
    quem não sabe o que existe na máquina. O provedor local sabe perguntar.
    """
    Imitacao.modo = "local"
    Imitacao.status = 404
    provedor = LocalProvider(api_key="", model="llama3.1", base_url=servidor)

    with pytest.raises(ProviderError) as erro:
        provedor.complete(pedido())

    mensagem = str(erro.value)
    assert "llama3.1" in mensagem
    assert "llama3.2:1b" in mensagem and "llama3.2:3b" in mensagem
    assert "ollama pull" in mensagem


def test_ollama_desligado_vira_instrucao_e_nao_erro_de_socket() -> None:
    """NFR-060: dependência externa ausente não vira erro cru de biblioteca.

    O endereço aponta para uma porta fechada de propósito — é exatamente o que
    acontece com o Ollama fechado, que é o caso mais comum de todos.
    """
    provedor = LocalProvider(
        api_key="", model="llama3.2:3b", base_url="http://127.0.0.1:1", timeout_s=2
    )

    with pytest.raises(ProviderError) as erro:
        provedor.complete(pedido())

    mensagem = str(erro.value)
    assert "Ollama" in mensagem
    assert "ollama serve" in mensagem
    assert "Errno" not in mensagem


# --- um cliente só para DeepSeek e para Kimi (REQ-05) ----------------------


def compativel(base_url: str, nome: str) -> OpenAICompatibleProvider:
    """O provedor genérico montado como o registry vai montá-lo: por dado."""
    return OpenAICompatibleProvider(
        api_key=f"chave-{nome}", model=f"modelo-{nome}", base_url=base_url, name=nome
    )


@pytest.mark.parametrize("fornecedor", ["deepseek", "kimi"])
def test_compativel_com_openai_faz_stream_dos_dois(servidor: str, fornecedor: str) -> None:
    """Mesmo cliente, dois formatos de contagem: um em evento próprio, outro
    junto do `finish_reason`. Os dois precisam chegar com texto e tokens."""
    Imitacao.modo = fornecedor
    provedor = compativel(servidor, fornecedor)

    pedacos = list(provedor.stream(pedido()))

    assert "".join(pedacos) == "O painel já sabe."
    assert len(pedacos) == 2, "chega em pedaços, não de uma vez"
    assert provedor.last_usage.tokens_in == 42
    assert provedor.last_usage.tokens_out == 9

    enviado = Imitacao.recebido
    assert enviado["path"] == "/v1/chat/completions"
    assert enviado["headers"]["Authorization"] == f"Bearer chave-{fornecedor}"
    # Sem isto nenhum dos dois devolve contagem no stream, e o custo some da tela.
    assert enviado["corpo"]["stream_options"] == {"include_usage": True}
    assert enviado["corpo"]["model"] == f"modelo-{fornecedor}"
    assert enviado["corpo"]["messages"][0]["role"] == "system"


@pytest.mark.parametrize("fornecedor", ["deepseek", "kimi"])
def test_compativel_com_openai_completa_sem_stream(servidor: str, fornecedor: str) -> None:
    Imitacao.modo = fornecedor
    provedor = compativel(servidor, fornecedor)

    resposta = provedor.complete(pedido())

    assert resposta.text == "O painel já sabe."
    assert resposta.usage.tokens_in == 42
    assert resposta.usage.tokens_out == 9
    assert resposta.model == f"{fornecedor}-imitacao"
    assert Imitacao.recebido["corpo"]["stream"] is False


def test_deepseek_e_kimi_sao_o_mesmo_cliente() -> None:
    """A diferença entre os dois é configuração, não código.

    O REQ-05 recusa uma classe por fornecedor: seriam cópias do mesmo cliente
    divergindo com o tempo. Este teste falha no dia em que alguém criar
    `DeepSeekProvider` para resolver uma diferença de uma linha.
    """
    deepseek = compativel("http://a.invalido", "deepseek")
    kimi = compativel("http://b.invalido", "kimi")

    assert type(deepseek) is type(kimi) is OpenAICompatibleProvider
    assert (deepseek.name, kimi.name) == ("deepseek", "kimi")
    assert deepseek.base_url != kimi.base_url

    corpo_deepseek = deepseek._body(pedido(), stream=True)
    corpo_kimi = kimi._body(pedido(), stream=True)
    assert corpo_deepseek.pop("model") != corpo_kimi.pop("model")
    assert corpo_deepseek == corpo_kimi, "só o modelo distingue as duas requisições"

    por_fornecedor = [n for n in dir(providers) if n.endswith("Provider")]
    assert not {"DeepSeekProvider", "KimiProvider", "MoonshotProvider"} & set(por_fornecedor)


def test_nome_e_de_instancia_com_padrao_de_classe() -> None:
    """Sem isto, DeepSeek e Kimi se registrariam os dois como `openai`."""
    padrao = OpenAIProvider(api_key="k", model="m", base_url="http://x")
    renomeado = OpenAIProvider(api_key="k", model="m", base_url="http://x", name="deepseek")

    assert padrao.name == "openai"
    assert renomeado.name == "deepseek"
    assert OpenAIProvider.name == "openai", "nome de instância não contamina a classe"
    assert LocalProvider(api_key="", model="m", base_url="http://x").name == "local"


def test_erro_do_generico_diz_qual_fornecedor_falhou() -> None:
    """"Falha ao falar com openai" seria mentira quando o que caiu foi o Kimi."""
    provedor = OpenAICompatibleProvider(
        api_key="k", model="m", base_url="http://127.0.0.1:1", name="kimi", timeout_s=2
    )

    with pytest.raises(ProviderError, match="Falha ao falar com kimi"):
        provedor.complete(pedido())
