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

from app.services.ai.providers import (
    AIRequest,
    AnthropicProvider,
    LocalProvider,
    Message,
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
        Imitacao.recebido = {"corpo": corpo, "headers": dict(self.headers)}

        if Imitacao.status >= 400:
            self.send_response(Imitacao.status)
            self.end_headers()
            self.wfile.write(b'{"error":"nao autorizado"}')
            return

        if Imitacao.modo == "local":
            self._responder_local(corpo.get("stream", False))
            return

        linhas = RESPOSTA_ANTHROPIC if Imitacao.modo == "anthropic" else RESPOSTA_OPENAI
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
            "model": "imitacao",
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
