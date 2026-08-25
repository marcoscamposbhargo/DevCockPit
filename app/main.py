"""Ponto de entrada da aplicação.

Monta rotas, middlewares de segurança e o frontend estático. O bind loopback é
validado em `Settings` (NFR-001) e a allowlist de ações é conferida no startup.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.docker.adapter import DockerAdapter
from app.adapters.system.ports import build_port_scanner
from app.api.middleware import (
    CorrelationIdMiddleware,
    HostGuardMiddleware,
    OriginGuardMiddleware,
)
from app.api.routes import (
    activity,
    ai,
    analytics,
    dashboard,
    dev_server,
    discovery,
    docker,
    environment,
    git,
    health,
    jobs,
    manifest,
    metrics,
    projects,
    services,
)
from app.core.cache import TTLCache
from app.core.config import PROJECT_ROOT, RootsConfig, Settings, get_roots_config, get_settings
from app.core.errors import DomainError
from app.core.logging import configure_logging, get_correlation_id
from app.jobs.job_manager import JobManager
from app.models.base import Base, create_session_factory
from app.runner.allowlist import assert_registry_is_safe
from app.runner.command_runner import SubprocessCommandRunner
from app.services.container_ports_service import ContainerPortsService
from app.services.health_history_service import HealthHistoryService
from app.services.health_poller import HealthPoller
from app.services.health_service import HealthService
from app.services.port_discovery_service import PortDiscoveryService
from app.services.retention_service import RetentionService

logger = logging.getLogger(__name__)

FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app(
    settings: Settings | None = None,
    roots: RootsConfig | None = None,
    *,
    create_tables: bool = False,
    start_poller: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    roots = roots or get_roots_config()

    configure_logging(
        level=settings.log_level,
        log_file=settings.resolve(settings.log_file),
        fmt=settings.log_format,
    )
    assert_registry_is_safe()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if start_poller:
            app.state.health_poller.start()
        try:
            yield
        finally:
            # Job em andamento é cancelado no encerramento: o estado é volátil
            # por decisão (D-07), mas deixar processo órfão nunca é aceitável.
            await app.state.health_poller.stop()
            await app.state.job_manager.shutdown()

    app = FastAPI(
        title="DevCockpit",
        version=settings.version,
        description="Central local de gerenciamento dos projetos de desenvolvimento.",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.roots = roots
    app.state.session_factory = _build_session_factory(settings, create_tables=create_tables)
    app.state.cache = TTLCache(ttl_seconds=settings.cache_ttl_seconds)
    app.state.command_runner = SubprocessCommandRunner()
    app.state.job_manager = JobManager(
        output_limit=settings.job_output_limit,
        retention_s=settings.job_retention,
    )
    app.state.health_service = HealthService(
        cache=app.state.cache,
        timeout_s=settings.health_timeout,
        # Dado mais velho que três ciclos do poller é marcado STALE.
        stale_after_s=settings.health_poll_interval * 3,
    )
    app.state.port_discovery = PortDiscoveryService(
        scanner=build_port_scanner(),
        cache=app.state.cache,
        # Os mesmos roots que limitam onde um projeto pode ser cadastrado
        # limitam o que a tela oferece encerrar (defesa D4, reusada).
        allowed_roots=roots.allowed_roots,
    )
    app.state.health_history = HealthHistoryService(
        session_factory=app.state.session_factory,
        min_interval_s=settings.health_snapshot_interval,
    )
    app.state.retention = RetentionService(
        session_factory=app.state.session_factory,
        activity_days=settings.activity_retention_days,
        health_days=settings.health_snapshot_retention_days,
        interval_s=settings.retention_interval,
    )
    app.state.container_ports = ContainerPortsService(
        adapter=DockerAdapter(
            runner=app.state.command_runner,
            docker_bin=settings.docker_bin,
            read_timeout_s=settings.timeout_docker_read,
        ),
        runner=app.state.command_runner,
        cwd=PROJECT_ROOT,
    )
    app.state.health_poller = HealthPoller(
        session_factory=app.state.session_factory,
        health=app.state.health_service,
        interval_s=settings.health_poll_interval,
        recent_days=settings.health_history_days,
        ports=app.state.port_discovery,
        history=app.state.health_history,
        retention=app.state.retention,
        containers=app.state.container_ports,
    )

    # Ordem de execução: o último adicionado roda primeiro.
    # Host precisa ser validado antes de tudo (defesa D10).
    app.add_middleware(OriginGuardMiddleware, settings=settings)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(HostGuardMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(settings.self_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["content-type", "x-devcockpit-client"],
    )

    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(git.router)
    app.include_router(manifest.router)
    app.include_router(docker.router)
    app.include_router(discovery.router)
    app.include_router(jobs.router)
    app.include_router(services.router)
    app.include_router(services.global_router)
    app.include_router(dashboard.router)
    app.include_router(activity.router)
    app.include_router(analytics.router)
    app.include_router(ai.router)
    app.include_router(ai.global_router)
    app.include_router(dev_server.router)
    app.include_router(dev_server.global_router)
    app.include_router(environment.router)
    app.include_router(metrics.router)

    _register_error_handlers(app)
    _mount_frontend(app)

    logger.info(
        "devcockpit iniciado",
        extra={
            "extra_fields": {
                "host": settings.host,
                "port": settings.port,
                "allowed_roots": [r.as_posix() for r in roots.allowed_roots],
            }
        },
    )
    return app


def _build_session_factory(settings: Settings, *, create_tables: bool):  # type: ignore[no-untyped-def]
    database_url = settings.database_url
    if database_url.startswith("sqlite:///./"):
        relative = database_url.removeprefix("sqlite:///./")
        absolute = settings.resolve(Path(relative))
        absolute.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{absolute}"

    factory = create_session_factory(database_url)
    if create_tables:
        Base.metadata.create_all(factory.kw["bind"])
    return factory


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", [])[1:]) or "payload"
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"{field}: {first.get('msg', 'dados inválidos')}",
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        correlation = get_correlation_id()
        logger.exception("erro não tratado", extra={"extra_fields": {"error": str(exc)}})
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Erro interno. Consulte o log com o correlation_id.",
                    "correlation_id": correlation,
                }
            },
        )


class RevalidatingStaticFiles(StaticFiles):
    """Arquivos estáticos que o browser sempre revalida.

    Sem `Cache-Control` o navegador aplica cache heurístico: guarda o CSS e o
    JS por um tempo que ele mesmo estima e **não pergunta ao servidor** se
    mudou. Num painel local, onde os arquivos mudam no disco embaixo da aba
    aberta, isso aparece como "a alteração não surtiu efeito" — com o servidor
    servindo o arquivo novo o tempo todo.

    `no-cache` não é "não guarde": é "guarde, mas confirme antes de usar". Com
    o ETag que o StaticFiles já emite, a confirmação vira um 304 sem corpo, que
    em loopback custa menos de um milissegundo.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _mount_frontend(app: FastAPI) -> None:
    if not FRONTEND_DIR.exists():
        return

    app.mount("/css", RevalidatingStaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", RevalidatingStaticFiles(directory=FRONTEND_DIR / "js"), name="js")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        # O `index.html` é o que amarra tudo: se ele vier do cache, referências
        # novas a arquivos novos nunca chegam a ser pedidas.
        return FileResponse(
            FRONTEND_DIR / "index.html",
            headers={"Cache-Control": "no-cache"},
        )


#: `app` construído só quando alguém pede, e não no import (PEP 562).
#:
#: `app = create_app()` no corpo do módulo fazia **importar** `app.main` ter o
#: efeito colateral de subir a aplicação inteira com as configurações de
#: produção: `configure_logging` apontando para `logs/devcockpit.log`, os roots
#: reais de `configs/roots.yml`, e o engine do banco de produção aberto.
#:
#: O sintoma era a suíte de testes escrevendo no log de produção — inclusive os
#: tracebacks que ela provoca de propósito, como o `RuntimeError("banco caiu")`
#: do teste do poller. Quem fosse investigar um problema de verdade nesse
#: arquivo encontraria erros encenados misturados aos reais, com o mesmo
#: formato e sem nada dizendo quais eram quais.
#:
#: `uvicorn app.main:app` continua funcionando sem alteração: o uvicorn faz
#: `getattr` no módulo, e é esse `getattr` que constrói. Quem importa
#: `create_app` — a suíte inteira — não toca em `app` e não constrói nada.
def __getattr__(name: str) -> object:
    if name == "app":
        aplicacao = create_app()
        globals()["app"] = aplicacao
        return aplicacao
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
