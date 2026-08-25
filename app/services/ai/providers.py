"""Provedores de IA, atrás de uma interface só.

O DevCockpit não se acopla a um fornecedor. A troca é de configuração, não de
código, e existe um provedor **local** de propósito: para quem não pode mandar
código para fora, ele é a única forma de usar o Cockpit AI.

Três implementações reais (Anthropic, OpenAI e Ollama) e uma dublê. Todas
falam o mesmo protocolo interno; a diferença entre elas mora só na montagem do
corpo e na leitura do stream.

Nenhuma delas guarda chave: a chave vem de `Settings`, que vem de variável de
ambiente. Nunca do banco, nunca de uma resposta HTTP (defesa D-A5).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.errors import DomainError

logger = logging.getLogger(__name__)


class ProviderError(DomainError):
    code = "AI_PROVIDER_ERROR"
    status_code = 502
    default_message = "O provedor de IA não respondeu."


class ProviderNotConfigured(DomainError):
    code = "AI_NOT_CONFIGURED"
    status_code = 409
    default_message = "Nenhum provedor de IA configurado."


@dataclass
class Message:
    role: str  # user | assistant
    content: str


@dataclass
class AIRequest:
    messages: list[Message]
    system: str = ""
    max_output_tokens: int = 2000
    temperature: float = 0.2


@dataclass
class AIUsage:
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class AIResponse:
    text: str = ""
    usage: AIUsage = field(default_factory=AIUsage)
    model: str = ""


class AIProvider(Protocol):
    name: str
    model: str

    def stream(self, request: AIRequest) -> Iterator[str]:
        """Emite pedaços de texto conforme chegam."""
        ...

    def complete(self, request: AIRequest) -> AIResponse: ...


class _HttpProvider:
    """O que Anthropic, OpenAI e Ollama têm em comum: um POST e um SSE.

    A parte específica de cada um fica em três métodos pequenos — corpo,
    cabeçalho e leitura do pedaço. O resto (timeout, erro, acumulação) é igual
    e vive aqui.
    """

    name = "http"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_s: float = 120.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.last_usage = AIUsage()

    # --- a implementar por provedor ---

    def _url(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _body(self, request: AIRequest, stream: bool) -> dict:
        raise NotImplementedError

    def _read_chunk(self, evento: dict) -> str:
        raise NotImplementedError

    def _read_usage(self, evento: dict) -> AIUsage | None:
        return None

    def _read_complete(self, dados: dict) -> AIResponse:
        raise NotImplementedError

    # --- comum ---

    def complete(self, request: AIRequest) -> AIResponse:
        try:
            with httpx.Client(timeout=self.timeout_s) as cliente:
                resposta = cliente.post(
                    self._url(), headers=self._headers(), json=self._body(request, stream=False)
                )
        except httpx.HTTPError as erro:
            raise ProviderError(f"Falha ao falar com {self.name}: {erro}") from erro

        if resposta.status_code >= 400:
            raise ProviderError(self._explicar(resposta))

        return self._read_complete(resposta.json())

    def stream(self, request: AIRequest) -> Iterator[str]:
        self.last_usage = AIUsage()
        try:
            with httpx.Client(timeout=self.timeout_s) as cliente:  # noqa: SIM117
                with cliente.stream(
                    "POST",
                    self._url(),
                    headers=self._headers(),
                    json=self._body(request, stream=True),
                ) as resposta:
                    if resposta.status_code >= 400:
                        resposta.read()
                        raise ProviderError(self._explicar(resposta))

                    for linha in resposta.iter_lines():
                        yield from self._processar_linha(linha)
        except httpx.HTTPError as erro:
            raise ProviderError(f"Falha ao falar com {self.name}: {erro}") from erro

    def _processar_linha(self, linha: str) -> Iterator[str]:
        linha = (linha or "").strip()
        if not linha:
            return
        if linha.startswith("data:"):
            linha = linha[5:].strip()
        # Fim de stream do formato OpenAI. Anthropic usa evento próprio.
        if linha == "[DONE]":
            return
        if not linha.startswith("{"):
            return

        try:
            evento = json.loads(linha)
        except json.JSONDecodeError:
            # Linha ilegível não invalida o resto: o texto já entregue continua
            # válido, e o modelo costuma repetir o que importa no fim.
            logger.debug("linha de stream ilegível", extra={"extra_fields": {"linha": linha[:80]}})
            return

        uso = self._read_usage(evento)
        if uso is not None:
            self.last_usage = AIUsage(
                tokens_in=uso.tokens_in or self.last_usage.tokens_in,
                tokens_out=uso.tokens_out or self.last_usage.tokens_out,
            )

        pedaco = self._read_chunk(evento)
        if pedaco:
            yield pedaco

    @staticmethod
    def _explicar(resposta: httpx.Response) -> str:
        """Mensagem que diz o que fazer, não só o que houve."""
        codigo = resposta.status_code
        if codigo in (401, 403):
            return (
                "O provedor recusou a chave de API. Confira "
                "`DEVCOCKPIT_AI_API_KEY` no seu `.env`."
            )
        if codigo == 404:
            return "Modelo não encontrado no provedor. Confira `DEVCOCKPIT_AI_MODEL`."
        if codigo == 429:
            return "O provedor recusou por excesso de requisições. Tente daqui a pouco."
        detalhe = (resposta.text or "")[:200]
        return f"O provedor respondeu {codigo}. {detalhe}"


class AnthropicProvider(_HttpProvider):
    name = "anthropic"

    def _url(self) -> str:
        return f"{self.base_url}/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _body(self, request: AIRequest, stream: bool) -> dict:
        return {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "system": request.system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": stream,
        }

    def _read_chunk(self, evento: dict) -> str:
        if evento.get("type") == "content_block_delta":
            return str(evento.get("delta", {}).get("text") or "")
        return ""

    def _read_usage(self, evento: dict) -> AIUsage | None:
        uso = evento.get("usage") or evento.get("message", {}).get("usage")
        if not uso:
            return None
        return AIUsage(
            tokens_in=int(uso.get("input_tokens") or 0),
            tokens_out=int(uso.get("output_tokens") or 0),
        )

    def _read_complete(self, dados: dict) -> AIResponse:
        partes = [
            bloco.get("text", "")
            for bloco in dados.get("content", [])
            if bloco.get("type") == "text"
        ]
        uso = dados.get("usage") or {}
        return AIResponse(
            text="".join(partes),
            usage=AIUsage(
                tokens_in=int(uso.get("input_tokens") or 0),
                tokens_out=int(uso.get("output_tokens") or 0),
            ),
            model=str(dados.get("model") or self.model),
        )


class OpenAIProvider(_HttpProvider):
    name = "openai"

    def _url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def _body(self, request: AIRequest, stream: bool) -> dict:
        mensagens = [{"role": "system", "content": request.system}] if request.system else []
        mensagens += [{"role": m.role, "content": m.content} for m in request.messages]
        corpo = {
            "model": self.model,
            "messages": mensagens,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": stream,
        }
        if stream:
            # Sem isto o stream do OpenAI não devolve contagem nenhuma, e o
            # painel não teria como mostrar o custo — que é meio ponto da tela.
            corpo["stream_options"] = {"include_usage": True}
        return corpo

    def _read_chunk(self, evento: dict) -> str:
        escolhas = evento.get("choices") or []
        if not escolhas:
            return ""
        return str(escolhas[0].get("delta", {}).get("content") or "")

    def _read_usage(self, evento: dict) -> AIUsage | None:
        uso = evento.get("usage")
        if not uso:
            return None
        return AIUsage(
            tokens_in=int(uso.get("prompt_tokens") or 0),
            tokens_out=int(uso.get("completion_tokens") or 0),
        )

    def _read_complete(self, dados: dict) -> AIResponse:
        escolhas = dados.get("choices") or [{}]
        uso = dados.get("usage") or {}
        return AIResponse(
            text=str(escolhas[0].get("message", {}).get("content") or ""),
            usage=AIUsage(
                tokens_in=int(uso.get("prompt_tokens") or 0),
                tokens_out=int(uso.get("completion_tokens") or 0),
            ),
            model=str(dados.get("model") or self.model),
        )


class LocalProvider(_HttpProvider):
    """Ollama ou compatível, na própria máquina.

    Existe por segurança antes de economia: para quem não pode mandar código
    para fora, este é o único caminho. Não usa chave.
    """

    name = "local"

    def _url(self) -> str:
        return f"{self.base_url}/api/chat"

    def _headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    def _body(self, request: AIRequest, stream: bool) -> dict:
        mensagens = [{"role": "system", "content": request.system}] if request.system else []
        mensagens += [{"role": m.role, "content": m.content} for m in request.messages]
        return {
            "model": self.model,
            "messages": mensagens,
            "stream": stream,
            "options": {"temperature": request.temperature},
        }

    def _read_chunk(self, evento: dict) -> str:
        return str(evento.get("message", {}).get("content") or "")

    def _read_usage(self, evento: dict) -> AIUsage | None:
        if not evento.get("done"):
            return None
        return AIUsage(
            tokens_in=int(evento.get("prompt_eval_count") or 0),
            tokens_out=int(evento.get("eval_count") or 0),
        )

    def _read_complete(self, dados: dict) -> AIResponse:
        return AIResponse(
            text=str(dados.get("message", {}).get("content") or ""),
            usage=AIUsage(
                tokens_in=int(dados.get("prompt_eval_count") or 0),
                tokens_out=int(dados.get("eval_count") or 0),
            ),
            model=str(dados.get("model") or self.model),
        )


class FakeProvider:
    """Provedor dublê: devolve o que mandarem, sem rede.

    Serve à suíte e ao desenvolvimento sem chave. Guarda o último pedido, que é
    como os testes conferem **o que teria sido enviado** — inclusive que
    segredo nenhum passou pela redação.
    """

    name = "fake"

    def __init__(self, model: str = "fake-1", resposta: str = "resposta de teste") -> None:
        self.model = model
        self.resposta = resposta
        self.last_request: AIRequest | None = None
        self.last_usage = AIUsage(tokens_in=10, tokens_out=5)

    def stream(self, request: AIRequest) -> Iterator[str]:
        self.last_request = request
        for pedaco in self.resposta.split(" "):
            yield pedaco + " "

    def complete(self, request: AIRequest) -> AIResponse:
        self.last_request = request
        return AIResponse(text=self.resposta, usage=self.last_usage, model=self.model)


#: Endereço padrão de cada provedor. Configurável para permitir proxy, gateway
#: corporativo e — o caso que importa aos testes — um servidor que imita a API.
BASE_URL_PADRAO = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "local": "http://127.0.0.1:11434",
}

MODELO_PADRAO = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
    "local": "llama3.1",
}


def build_provider(settings) -> AIProvider:  # type: ignore[no-untyped-def]
    """Monta o provedor a partir da configuração. Levanta se faltar peça."""
    nome = (settings.ai_provider or "none").lower()

    if nome in ("none", ""):
        raise ProviderNotConfigured(
            "A IA está desligada. Defina DEVCOCKPIT_AI_PROVIDER no .env "
            "(anthropic, openai ou local)."
        )

    if nome == "fake":
        return FakeProvider()

    classes = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "local": LocalProvider,
    }
    if nome not in classes:
        raise ProviderNotConfigured(f"Provedor desconhecido: {nome!r}.")

    chave = settings.ai_api_key
    if nome != "local" and not chave:
        raise ProviderNotConfigured(
            f"O provedor {nome} exige DEVCOCKPIT_AI_API_KEY no .env. "
            "A chave nunca é guardada no banco nem editável pela tela."
        )

    return classes[nome](
        api_key=chave,
        model=settings.ai_model or MODELO_PADRAO[nome],
        base_url=settings.ai_base_url or BASE_URL_PADRAO[nome],
        timeout_s=settings.ai_timeout,
    )
