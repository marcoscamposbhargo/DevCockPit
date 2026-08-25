"""Health check de serviços locais (FR-060 a FR-064).

Duas decisões que sustentam o requisito de dashboard abaixo de 500 ms:

1. as verificações são **concorrentes**, com timeout individual curto;
2. a API **nunca** verifica sob demanda no caminho da requisição — ela lê
   cache, e quem preenche o cache é o poller de background.

Sem isso, 30 projetos × 3 serviços seriam 90 conexões TCP a cada carga de tela.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import httpx

from app.core.cache import TTLCache
from app.models.base import utcnow

logger = logging.getLogger(__name__)


class HealthState(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    ERROR = "ERROR"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ServiceTarget:
    project_id: str
    key: str
    label: str
    host: str
    port: int | None
    url: str | None
    health_url: str | None
    health_kind: str


@dataclass
class HealthResult:
    project_id: str
    key: str
    state: HealthState
    latency_ms: int | None = None
    detail: str | None = None
    checked_at: datetime | None = None

    @property
    def age_seconds(self) -> float | None:
        if self.checked_at is None:
            return None
        return (utcnow() - self.checked_at).total_seconds()


OK_STATUS = frozenset({200, 201, 202, 204, 301, 302, 303, 304, 307, 308})


class HealthService:
    def __init__(
        self,
        cache: TTLCache,
        timeout_s: float = 2.0,
        stale_after_s: float = 90.0,
        max_concurrency: int = 8,
    ) -> None:
        self.cache = cache
        self.timeout_s = timeout_s
        self.stale_after_s = stale_after_s
        #: Quantas verificações correm ao mesmo tempo.
        #:
        #: Sem teto, `check_many` disparava tudo de uma vez. Com 25 projetos
        #: isso vira ~40 conexões simultâneas — cada uma com duas famílias de
        #: endereço —, o event loop satura, e o `wait_for` de 2 s estoura em
        #: porta que responde em 0 ms. O histórico registrou a prova: latência
        #: de 3 a 6 segundos num teto de 2, que é impossível a menos que o
        #: tempo tenha sido gasto **na fila**, não na conexão.
        #:
        #: O sintoma para quem usa era o pior possível: serviço no ar aparecendo
        #: como desligado, de forma intermitente, sem nada errado no projeto.
        self.max_concurrency = max(1, int(max_concurrency))
        #: Cliente HTTP único, criado na primeira verificação HTTP.
        #:
        #: Antes era um `AsyncClient` por verificação. O construtor monta um
        #: contexto SSL e, no Windows, isso custa ~225 ms **síncronos, em cima
        #: do event loop** — medido. Num ciclo com vinte serviços, o loop
        #: ficava bloqueado segundos, e o `wait_for` de 2 s só era atendido
        #: depois: era assim que uma verificação com teto de 2 s registrava
        #: latência de 6 s e um serviço no ar era marcado OFFLINE.
        #:
        #: Um cliente só também reaproveita conexão, que é o motivo pelo qual
        #: `AsyncClient` existe.
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    # --- verificação ---

    async def check(self, target: ServiceTarget) -> HealthResult:
        kind = (target.health_kind or "TCP").upper()

        if kind == "NONE":
            return self._store(
                HealthResult(
                    project_id=target.project_id,
                    key=target.key,
                    state=HealthState.UNKNOWN,
                    detail="Serviço marcado como não monitorado.",
                    checked_at=utcnow(),
                )
            )

        if kind == "HTTP" and (target.health_url or target.url):
            return self._store(await self._check_http(target))

        if target.port:
            return self._store(await self._check_tcp(target))

        return self._store(
            HealthResult(
                project_id=target.project_id,
                key=target.key,
                state=HealthState.UNKNOWN,
                detail="Sem porta nem URL para verificar.",
                checked_at=utcnow(),
            )
        )

    async def check_many(self, targets: list[ServiceTarget]) -> list[HealthResult]:
        """Verifica em lote, com teto de concorrência.

        O teto é o que faz o timeout voltar a medir o serviço em vez da fila.
        """
        if not targets:
            return []

        limite = asyncio.Semaphore(self.max_concurrency)

        async def com_limite(target: ServiceTarget) -> HealthResult:
            async with limite:
                return await self.check(target)

        return list(await asyncio.gather(*(com_limite(target) for target in targets)))

    async def _http_client(self) -> httpx.AsyncClient:
        """O cliente compartilhado, construído uma vez só.

        O lock evita que duas verificações simultâneas paguem o custo de
        construção em paralelo na primeira vez.
        """
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(
                        timeout=self.timeout_s, follow_redirects=False
                    )
        return self._client

    async def aclose(self) -> None:
        """Fecha o cliente compartilhado no desligamento da aplicação."""
        cliente, self._client = self._client, None
        if cliente is not None:
            with contextlib.suppress(Exception):
                await cliente.aclose()

    async def _check_http(self, target: ServiceTarget) -> HealthResult:
        url = target.health_url or target.url or ""
        client = await self._http_client()
        started = asyncio.get_running_loop().time()

        try:
            response = await client.get(url)
        except httpx.ConnectError:
            return self._result(target, HealthState.OFFLINE, started, "Conexão recusada.")
        except httpx.ConnectTimeout:
            # Estourou o tempo **antes de conectar**. No Windows, tentar uma
            # porta sem ninguém escutando costuma pendurar em vez de recusar na
            # hora, então este é o caminho normal de um serviço que
            # simplesmente não foi ligado — não é erro, é desligado. Marcar
            # ERROR aqui pintava a tela de vermelho para o caso mais banal que
            # existe, e vermelho que aparece sempre para de significar algo.
            return self._result(
                target,
                HealthState.OFFLINE,
                started,
                f"Sem resposta em {self.timeout_s:g}s.",
            )
        except (httpx.TimeoutException, TimeoutError):
            # Conectou e não respondeu a tempo: aí sim há algo de pé e travado,
            # que é exatamente o que ERROR deve significar.
            return self._result(target, HealthState.ERROR, started, "Conectou, mas não respondeu.")
        except httpx.HTTPError as exc:
            return self._result(target, HealthState.ERROR, started, str(exc)[:200])

        if response.status_code in OK_STATUS:
            return self._result(target, HealthState.ONLINE, started)

        # 5xx num serviço que responde geralmente é aplicação subindo.
        if 500 <= response.status_code < 600:
            return self._result(
                target, HealthState.STARTING, started, f"HTTP {response.status_code}"
            )

        return self._result(target, HealthState.ERROR, started, f"HTTP {response.status_code}")

    async def _check_tcp(self, target: ServiceTarget) -> HealthResult:
        started = asyncio.get_running_loop().time()
        host = target.host or "localhost"

        try:
            # `happy_eyeballs_delay` existe por um bug real: no Windows,
            # `localhost` resolve para `::1` antes de `127.0.0.1`, e um serviço
            # que só ouve em IPv4 fazia a tentativa IPv6 pendurar até estourar
            # o timeout — o serviço aparecia OFFLINE estando no ar. Com o
            # atraso, as duas famílias são tentadas quase juntas e a primeira
            # que responder vence.
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, target.port, happy_eyeballs_delay=0.25),
                timeout=self.timeout_s,
            )
        except TimeoutError:
            # Este ramo precisa vir **antes** de `OSError`: desde o Python 3.10
            # `TimeoutError` é subclasse de `OSError` e, na ordem inversa, era
            # código morto — nenhum estouro de tempo chegava aqui.
            #
            # O estado continua OFFLINE, e isso é deliberado: no Windows a
            # tentativa contra porta fechada frequentemente **pendura** até o
            # timeout em vez de ser recusada na hora, então promover isso a
            # ERROR marcaria de vermelho o caso mais comum e mais banal. O que
            # muda é o texto, que agora diz o que de fato aconteceu.
            return self._result(
                target,
                HealthState.OFFLINE,
                started,
                f"Sem resposta em {self.timeout_s:g}s.",
            )
        except (ConnectionRefusedError, socket.gaierror, OSError):
            return self._result(target, HealthState.OFFLINE, started, "Porta fechada.")

        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()

        return self._result(target, HealthState.ONLINE, started)

    def _result(
        self,
        target: ServiceTarget,
        state: HealthState,
        started: float,
        detail: str | None = None,
    ) -> HealthResult:
        elapsed = asyncio.get_running_loop().time() - started
        return HealthResult(
            project_id=target.project_id,
            key=target.key,
            state=state,
            latency_ms=int(elapsed * 1000),
            detail=detail,
            checked_at=utcnow(),
        )

    # --- cache ---

    def _key(self, project_id: str, key: str) -> str:
        return f"health:{project_id}:{key}"

    def _store(self, result: HealthResult) -> HealthResult:
        self.cache.set(self._key(result.project_id, result.key), result)
        return result

    def last_known(self, project_id: str, key: str) -> HealthResult:
        """Último estado conhecido, marcando `STALE` quando o dado envelheceu.

        Nunca verifica aqui: a API lê, o poller escreve. Dado velho apresentado
        como tempo real é o que destrói a confiança na ferramenta (D-18).
        """
        entry = self.cache.get_with_age(self._key(project_id, key))
        if entry is None:
            return HealthResult(
                project_id=project_id,
                key=key,
                state=HealthState.UNKNOWN,
                detail="Ainda não verificado.",
            )

        result, _age = entry
        idade = result.age_seconds
        if idade is not None and idade > self.stale_after_s and result.state != HealthState.STALE:
            return HealthResult(
                project_id=result.project_id,
                key=result.key,
                state=HealthState.STALE,
                latency_ms=result.latency_ms,
                detail=f"Última verificação há {int(idade)}s.",
                checked_at=result.checked_at,
            )
        return result

    def invalidate(self, project_id: str) -> None:
        self.cache.invalidate_prefix(f"health:{project_id}:")


def targets_from_project(project) -> list[ServiceTarget]:  # type: ignore[no-untyped-def]
    return [
        ServiceTarget(
            project_id=project.id,
            key=service.key,
            label=service.label,
            host=service.host or "localhost",
            port=service.port,
            url=service.url,
            health_url=service.health_url,
            health_kind=service.health_kind,
        )
        for service in project.services
    ]


def should_poll(project, recent_days: int) -> bool:  # type: ignore[no-untyped-def]
    """Quais projetos o poller acompanha (questão Q-02).

    Verificar 36 projetos a cada 30 s é caro e inútil: a maioria está parada há
    semanas. A política é **fixados + acessados recentemente**, que é onde o
    dado fresco tem valor. Qualquer projeto pode ser verificado sob demanda.
    """
    if project.is_pinned:
        return True
    if project.last_accessed_at is None:
        return False
    return project.last_accessed_at >= utcnow() - timedelta(days=recent_days)
