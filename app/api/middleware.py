"""Middlewares de segurança — defesas D5 e D10 (`docs/07-security-model.md`).

Ordem importa: `Host` é validado antes de qualquer roteamento, e vale também
para `GET` e para endpoints SSE.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import ALLOWED_HTTP_HOSTS, Settings
from app.core.logging import new_correlation_id, set_autoria, set_correlation_id
from app.services.ai.propostas import REGISTRO

logger = logging.getLogger(__name__)

CLIENT_HEADER = "x-devcockpit-client"
PROPOSAL_HEADER = "x-devcockpit-proposal"
CLIENT_HEADER_VALUE = "web"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _deny(code: str, message: str) -> JSONResponse:
    correlation = set_correlation_id(None)
    logger.warning(
        "request denied",
        extra={"extra_fields": {"code": code, "message": message}},
    )
    return JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": message, "correlation_id": correlation}},
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation = set_correlation_id(new_correlation_id())
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation
        return response


class HostGuardMiddleware(BaseHTTPMiddleware):
    """Defesa D10 — fecha DNS rebinding.

    No rebinding o browser continua enviando `Host: evil.com`, porque é o nome
    que ele resolveu. O servidor não sabe que o IP foi reamarrado, mas sabe que
    ninguém legítimo o alcança por esse nome.
    """

    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_host = request.headers.get("host", "")
        hostname = self._hostname(raw_host)

        if hostname not in ALLOWED_HTTP_HOSTS:
            return _deny(
                "ACTION_NOT_ALLOWED",
                "Esta aplicação só aceita requisições por localhost.",
            )
        return await call_next(request)

    @staticmethod
    def _hostname(raw: str) -> str:
        value = raw.strip()
        if value.startswith("["):  # IPv6 literal, ex: [::1]:8765
            closing = value.find("]")
            return value[: closing + 1] if closing != -1 else value
        return value.rsplit(":", 1)[0] if ":" in value else value


class AutoriaMiddleware(BaseHTTPMiddleware):
    """Marca a requisição como vinda da IA — quando o servidor a reconhece.

    O cliente manda um bilhete, não uma afirmação: ele diz *qual* proposta está
    confirmando, e quem decide se aquilo é autoria de IA é o registro do
    servidor, conferindo método e rota. Bilhete inventado, vencido, já usado ou
    apontando para outra rota simplesmente não marca nada — a ação segue e é
    gravada como o que ela é, ação da pessoa.

    Não é uma defesa de segurança: a execução já estava contida pelo registro
    fechado de ações (D-A3). É uma defesa da **verdade do log**.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        set_autoria(None)

        bilhete = request.headers.get(PROPOSAL_HEADER, "")
        if bilhete:
            proposta = REGISTRO.resgatar(
                bilhete, method=request.method, path=request.url.path
            )
            if proposta is not None:
                set_autoria((proposta.action, proposta.reason, proposta.origem))

        return await call_next(request)


class OriginGuardMiddleware(BaseHTTPMiddleware):
    """Defesa D5 — bloqueia página maliciosa operando a ferramenta.

    `Origin` é obrigatório nas requisições de escrita: tolerar a ausência é o
    que a variante de rebinding explora.
    """

    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in WRITE_METHODS:
            return await call_next(request)

        if request.headers.get(CLIENT_HEADER, "").lower() != CLIENT_HEADER_VALUE:
            return _deny(
                "ACTION_NOT_ALLOWED",
                f"Cabeçalho {CLIENT_HEADER} ausente ou inválido.",
            )

        origin = request.headers.get("origin")
        if not origin:
            return _deny("ACTION_NOT_ALLOWED", "Cabeçalho Origin ausente.")
        if origin not in self.settings.self_origins:
            return _deny("ACTION_NOT_ALLOWED", "Origin não autorizado.")

        return await call_next(request)
