"""Provedores de IA, atrás de uma interface só.

O DevCockpit não se acopla a um fornecedor. A troca é de configuração, não de
código, e existe um provedor **local** de propósito: para quem não pode mandar
código para fora, ele é a única forma de usar o Cockpit AI.

Três formatos reais (Anthropic, `/v1/chat/completions` e Ollama) e uma dublê.
Todos falam o mesmo protocolo interno; a diferença entre eles mora só na
montagem do corpo e na leitura do stream.

Formato não é fornecedor: `/v1/chat/completions` virou padrão de fato, e um
mesmo cliente atende OpenAI, DeepSeek e Kimi — o que muda é `base_url`, chave e
`name`, tudo vindo da configuração. Por isso `name` é atributo de instância com
padrão de classe: dois provedores da mesma classe precisam aparecer com
identidade própria no registro de execuções e na mensagem de erro.

Nenhum deles guarda chave: a chave vem de `Settings`, que vem de variável de
ambiente. Nunca do banco, nunca de uma resposta HTTP (defesa D-A5).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import httpx

from app.core.errors import DomainError

if TYPE_CHECKING:
    from app.services.ai.model_router import Candidato

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

    #: Padrão de classe. `name` de verdade é o de instância, montado abaixo.
    name = "http"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_s: float = 120.0,
        name: str = "",
    ):
        # Identidade é dado, não classe: o mesmo cliente serve dois fornecedores
        # com o mesmo formato de API, e cada um precisa se registrar com o
        # próprio nome. Sem `name`, vale o padrão da classe — nada muda para
        # quem já construía o provedor sem passar nada (REQ-05).
        self.name = name or type(self).name
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
            raise ProviderError(self._explicar_falha_de_rede(erro)) from erro

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
            raise ProviderError(self._explicar_falha_de_rede(erro)) from erro

    def _explicar_falha_de_rede(self, erro: Exception) -> str:
        """Sobrescrito pelo provedor local, que sabe o que costuma faltar."""
        return f"Falha ao falar com {self.name}: {erro}"

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


class OpenAICompatibleProvider(_HttpProvider):
    """Qualquer API que fale `/v1/chat/completions`.

    OpenAI, DeepSeek e Kimi (Moonshot) expõem o mesmo formato: mesmo caminho,
    mesma autenticação por `Bearer`, mesmo SSE de `choices[].delta.content`,
    mesma contagem em `usage.prompt_tokens`/`completion_tokens` e o mesmo
    `stream_options.include_usage` para receber a contagem no stream. Servir
    cada um é questão de `base_url`, chave e `name` — nunca de classe nova, que
    seriam três cópias do mesmo código divergindo com o tempo.

    Se algum fornecedor divergir em um ponto (a leitura do uso, o campo de
    erro), a divergência vira subclasse pequena sobrescrevendo só o método em
    questão, como `OpenAIProvider` faz com o nome.
    """

    name = "openai-compatible"

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


class OpenAIProvider(OpenAICompatibleProvider):
    """A OpenAI é um caso do formato compatível, não o contrário.

    Existe como classe própria porque o `.env` de hoje nomeia `openai` e os
    testes a importam por nome — e porque o registro da execução precisa dizer
    `openai`, não `openai-compatible`.
    """

    name = "openai"


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

    def _explicar(self, resposta: httpx.Response) -> str:  # type: ignore[override]
        """No provedor local, "modelo não encontrado" tem conserto na hora.

        A mensagem genérica manda conferir a variável de ambiente — o que não
        ajuda quem não sabe o que existe na máquina. Aqui dá para perguntar, e
        um erro que lista as opções vale por uma ida à documentação.
        """
        if resposta.status_code == 404:
            disponiveis = self._modelos_instalados()
            if disponiveis:
                return (
                    f"O modelo {self.model!r} não está instalado no Ollama. "
                    f"Instalados: {', '.join(disponiveis)}. "
                    "Escolha um em `DEVCOCKPIT_AI_MODEL`, ou baixe o que falta "
                    f"com `ollama pull {self.model}`."
                )
            return (
                f"O modelo {self.model!r} não está instalado no Ollama, e não há "
                f"nenhum outro. Baixe um com `ollama pull {self.model}`."
            )
        return super()._explicar(resposta)

    def _explicar_falha_de_rede(self, erro: Exception) -> str:
        """Ollama desligado é o caso comum, e tem uma linha de conserto.

        "Falha ao falar com local: [Errno 10061]" não diz a ninguém que basta
        abrir o Ollama. Este é o caminho da NFR-060: dependência externa
        ausente vira instrução, não erro cru de biblioteca.
        """
        # `ConnectTimeout` vem **antes** de `TimeoutException`, e a ordem é o
        # que faz o texto certo aparecer: no Windows, conectar numa porta sem
        # ninguém escutando pendura até o timeout em vez de ser recusado na
        # hora (a mesma peculiaridade que o health check documenta). Sem esta
        # ordem, o Ollama fechado — o caso mais comum de todos — receberia o
        # conselho de aumentar o timeout, que não conserta nada.
        if isinstance(erro, httpx.ConnectError | httpx.ConnectTimeout):
            return (
                f"O Ollama não respondeu em {self.base_url}. Abra o aplicativo "
                "Ollama, ou rode `ollama serve` num terminal."
            )
        if isinstance(erro, httpx.TimeoutException):
            return (
                f"O Ollama conectou mas não respondeu a tempo ({self.timeout_s:g}s). "
                "Modelo grande demora para carregar na memória na primeira "
                "pergunta; aumente `DEVCOCKPIT_AI_TIMEOUT` ou escolha um modelo menor."
            )
        return super()._explicar_falha_de_rede(erro)

    def _modelos_instalados(self) -> list[str]:
        """Best-effort: se a consulta falhar, a mensagem só fica mais pobre."""
        try:
            with httpx.Client(timeout=5.0) as cliente:
                dados = cliente.get(f"{self.base_url}/api/tags").json()
            return sorted(str(m.get("name")) for m in dados.get("models", []) if m.get("name"))
        except (httpx.HTTPError, ValueError, KeyError):
            return []


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

#: Último recurso, quando nem `configs/ai.yml` nem `DEVCOCKPIT_AI_MODEL` dizem
#: qual modelo usar. É o padrão do PROJETO, não o desta máquina: o local aqui
#: é deliberadamente pequeno, porque quem clona o repositório pode não ter RAM
#: para um modelo grande, e "modelo não encontrado" na primeira pergunta é uma
#: recepção ruim. Quem quer outro declara no registro.
MODELO_PADRAO = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
    "local": "llama3.2:3b",
}


def build_provider(settings, model: str = "") -> AIProvider:  # type: ignore[no-untyped-def]
    """Monta o provedor a partir da configuração. Levanta se faltar peça.

    `model` sobrescreve `DEVCOCKPIT_AI_MODEL` — é como o segundo modelo entra
    sem duplicar o resto da configuração (endereço, chave, timeout são os
    mesmos). Quem escolhe o nome é sempre o servidor, a partir das settings:
    nada aqui aceita nome de modelo vindo do cliente.
    """
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
        model=model or settings.ai_model or MODELO_PADRAO[nome],
        base_url=settings.ai_base_url or BASE_URL_PADRAO[nome],
        timeout_s=settings.ai_timeout,
    )


# --- a construção do provedor a partir do registro (`configs/ai.yml`) -----
#
# Vive ao lado de `build_provider` porque é a mesma responsabilidade — candidato
# ou configuração vira cliente `AIProvider` — só que a partir do registro
# declarativo (T-01) em vez do `.env`. Nasceu em `runner.py` (T-09), porque a
# T-02 fechou antes de o registro existir; move para cá depois, sem mudar
# comportamento, para as duas montagens do provedor morarem juntas.
#
# `Candidato` só entra como type hint (`TYPE_CHECKING`): não há import circular
# hoje entre `providers.py` e `model_router.py`/`registry.py`, mas este módulo é
# a camada mais baixa da árvore de IA, e não há motivo para ele carregar em
# runtime o registro declarativo só para um nome de tipo.

#: Formato de wire por id de provider declarado. Quem não estiver aqui fala
#: `/v1/chat/completions` (nuvem) ou o formato do Ollama (local) — que é o que
#: DeepSeek e Kimi usam, e a razão de `OpenAICompatibleProvider` existir.
FORMATOS_POR_PROVIDER: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def construir_provider(candidato: Candidato, settings) -> AIProvider:  # type: ignore[no-untyped-def]
    """Monta o cliente do candidato. Levanta quando falta peça.

    A chave sai do ambiente pelo nome declarado em `api_key_env`, e de lugar
    nenhum mais: o registro nomeia a variável, nunca guarda o valor (**P-05**).
    """
    declarado = candidato.provider
    modelo = candidato.modelo.model

    if declarado.local:
        return LocalProvider(
            api_key="",
            model=modelo,
            base_url=declarado.base_url or BASE_URL_PADRAO["local"],
            timeout_s=settings.ai_timeout,
            name=declarado.id,
        )

    if not declarado.base_url:
        raise ProviderNotConfigured(
            f"O provider {declarado.id!r} não declara 'base_url' em configs/ai.yml."
        )

    chave = os.environ.get(declarado.api_key_env, "").strip() if declarado.api_key_env else ""
    if not chave:
        raise ProviderNotConfigured(
            f"O provider {declarado.id!r} precisa da variável "
            f"{declarado.api_key_env or 'declarada em api_key_env'} no ambiente. "
            "A chave nunca é guardada no banco nem editável pela tela."
        )

    classe = FORMATOS_POR_PROVIDER.get(declarado.id, OpenAICompatibleProvider)
    return classe(
        api_key=chave,
        model=modelo,
        base_url=declarado.base_url,
        timeout_s=settings.ai_timeout,
        name=declarado.id,
    )
