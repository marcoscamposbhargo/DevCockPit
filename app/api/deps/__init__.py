"""Injeção de dependência das rotas.

Serviços recebem colaboradores por aqui, o que permite substituí-los por
implementação fake nos testes (NFR-023).
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.adapters.docker.adapter import DockerAdapter
from app.adapters.git.adapter import GitAdapter
from app.adapters.system.adapter import build_os_adapter
from app.core.cache import TTLCache
from app.core.config import PROJECT_ROOT, RootsConfig, Settings
from app.jobs.job_manager import JobManager
from app.services.activity_service import ActivityService
from app.services.analytics_service import AnalyticsService
from app.services.briefing_service import BriefingService
from app.services.dashboard_service import DashboardService
from app.services.detection_service import DetectionService
from app.services.dev_server_service import DevServerService
from app.services.discovery_service import DiscoveryService
from app.services.docker_service import DockerService
from app.services.environment_service import EnvironmentService
from app.services.git_service import GitService
from app.services.health_service import HealthService
from app.services.manifest_service import ManifestService
from app.services.memory_service import MemoryService
from app.services.metrics_service import MetricsService
from app.services.port_discovery_service import PortDiscoveryService
from app.services.project_service import ProjectService
from app.services.session_service import SessionService
from app.services.system_action_service import SystemActionService
from app.services.task_service import TaskService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_roots_dep(request: Request) -> RootsConfig:
    return request.app.state.roots


def get_cache(request: Request) -> TTLCache:
    return request.app.state.cache


def get_command_runner(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.command_runner


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_activity_service(session: Session = Depends(get_session)) -> ActivityService:
    return ActivityService(session)


def get_detection_service(
    session: Session = Depends(get_session),
    activity: ActivityService = Depends(get_activity_service),
) -> DetectionService:
    return DetectionService(session, activity=activity)


def get_project_service(
    session: Session = Depends(get_session),
    roots: RootsConfig = Depends(get_roots_dep),
    activity: ActivityService = Depends(get_activity_service),
    detection: DetectionService = Depends(get_detection_service),
) -> ProjectService:
    return ProjectService(
        session=session,
        allowed_roots=roots.allowed_roots,
        activity=activity,
        detection=detection,
    )


def get_manifest_service(
    session: Session = Depends(get_session),
    activity: ActivityService = Depends(get_activity_service),
) -> ManifestService:
    return ManifestService(session=session, activity=activity)


def get_git_service(
    settings: Settings = Depends(get_settings_dep),
    cache: TTLCache = Depends(get_cache),
    runner=Depends(get_command_runner),  # noqa: B008
) -> GitService:
    adapter = GitAdapter(
        runner=runner,
        git_bin=settings.git_bin,
        timeout_s=settings.timeout_git,
    )
    return GitService(adapter=adapter, cache=cache)


def get_docker_service(
    settings: Settings = Depends(get_settings_dep),
    cache: TTLCache = Depends(get_cache),
    runner=Depends(get_command_runner),  # noqa: B008
    jobs: JobManager = Depends(get_job_manager),
    session: Session = Depends(get_session),
) -> DockerService:
    adapter = DockerAdapter(
        runner=runner,
        docker_bin=settings.docker_bin,
        read_timeout_s=settings.timeout_docker_read,
    )
    return DockerService(
        adapter=adapter,
        cache=cache,
        jobs=jobs,
        timeouts={
            "up": settings.timeout_compose_up,
            "down": settings.timeout_compose_control,
            "start": settings.timeout_compose_control,
            "stop": settings.timeout_compose_control,
            "restart": settings.timeout_compose_control,
            "default": settings.timeout_compose_control,
        },
        # Sem a sessão o serviço não enxerga `docker_config` e o `compose_file`
        # declarado no manifesto ficaria sem efeito.
        session=session,
    )


def get_health_service(request: Request) -> HealthService:
    """Instância única: o cache de health é compartilhado com o poller."""
    return request.app.state.health_service


def get_port_discovery(request: Request) -> PortDiscoveryService:
    """Instância única, pelo mesmo motivo: quem varre é o poller, a API lê."""
    return request.app.state.port_discovery


def get_system_service(
    settings: Settings = Depends(get_settings_dep),
    runner=Depends(get_command_runner),  # noqa: B008
    activity: ActivityService = Depends(get_activity_service),
) -> SystemActionService:
    adapter = build_os_adapter(
        code_bin=settings.code_bin,
        timeout_s=settings.timeout_system_action,
    )
    return SystemActionService(adapter=adapter, runner=runner, activity=activity)


def get_dashboard_service(
    session: Session = Depends(get_session),
    cache: TTLCache = Depends(get_cache),
    health: HealthService = Depends(get_health_service),
    ports: PortDiscoveryService = Depends(get_port_discovery),
) -> DashboardService:
    return DashboardService(session=session, cache=cache, health=health, ports=ports)


def get_analytics_service(
    session: Session = Depends(get_session),
    cache: TTLCache = Depends(get_cache),
    settings: Settings = Depends(get_settings_dep),
) -> AnalyticsService:
    """Análise histórica.

    O teto de cobertura por amostra vem do intervalo de gravação do histórico:
    o que passa dele é buraco, não disponibilidade (ver `AnalyticsService`).
    """
    return AnalyticsService(
        session=session,
        cache=cache,
        max_gap_s=settings.health_snapshot_interval * 2,
    )


def get_session_service(
    session: Session = Depends(get_session),
    git: GitService = Depends(get_git_service),
) -> SessionService:
    """Sessão de trabalho.

    O Git entra para marcar começo e fim: sem ele o resumo continua saindo, só
    que sem commits — ausência de dependência externa nunca vira erro de tela.
    """
    return SessionService(session=session, git=git)


def get_memory_service(session: Session = Depends(get_session)) -> MemoryService:
    return MemoryService(session)


def get_task_service(session: Session = Depends(get_session)) -> TaskService:
    return TaskService(session)


def get_briefing_service(
    session: Session = Depends(get_session),
    cache: TTLCache = Depends(get_cache),
    health: HealthService = Depends(get_health_service),
) -> BriefingService:
    """Briefing do dia: só lê o que o poller e as consultas já apuraram."""
    return BriefingService(session=session, cache=cache, health=health)


def get_discovery_service(
    session: Session = Depends(get_session),
    roots: RootsConfig = Depends(get_roots_dep),
) -> DiscoveryService:
    return DiscoveryService(session=session, roots=roots)


def get_dev_server_service(
    request: Request,
    session: Session = Depends(get_session),
    activity: ActivityService = Depends(get_activity_service),
) -> DevServerService:
    settings: Settings = request.app.state.settings
    # O log de cada servidor vive ao lado do log da aplicação. Caminho de
    # arquivo é configuração, e configuração mora em `Settings` (NFR-022).
    return DevServerService(
        session=session,
        logs_dir=settings.resolve(settings.log_file).parent,
        activity=activity,
    )


def get_environment_service(request: Request) -> EnvironmentService:
    """Orquestra Docker e aplicação.

    Recebe a **fábrica** de sessão, não uma sessão: a sequência roda dentro de
    um job, depois que a requisição já acabou e a sessão dela foi fechada.
    """
    settings: Settings = request.app.state.settings
    return EnvironmentService(
        session_factory=request.app.state.session_factory,
        adapter=DockerAdapter(
            runner=request.app.state.command_runner,
            docker_bin=settings.docker_bin,
            read_timeout_s=settings.timeout_docker_read,
        ),
        health=request.app.state.health_service,
        logs_dir=settings.resolve(settings.log_file).parent,
        compose_timeout_s=settings.timeout_compose_up,
        # Para dizer **quem** está com a porta quando o Compose falha por
        # "port is already allocated" — a falha mais comum e a mais inútil
        # como o Docker a entrega.
        discovery=request.app.state.port_discovery,
    )


def get_metrics_service(request: Request) -> MetricsService:
    """Instância única: o cache de temperatura e as amostras de processador só
    fazem sentido acumulando entre requisições. Uma instância nova por chamada
    devolveria 0% de CPU para sempre, porque `psutil` mede entre duas leituras.
    """
    if not hasattr(request.app.state, "metrics_service"):
        request.app.state.metrics_service = MetricsService(
            runner=request.app.state.command_runner,
            project_root=PROJECT_ROOT,
        )
    return request.app.state.metrics_service
