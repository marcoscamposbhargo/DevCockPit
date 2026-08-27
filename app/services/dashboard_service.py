"""Agregação do dashboard (FR-080 a FR-084).

Regra: **nada aqui toca disco, Git ou Docker**. Só banco e cache. Se um dado
não estiver no cache, aparece como desconhecido — não se paga o custo de
buscá-lo no caminho da requisição (NFR-010, NFR-011).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.models.base import utcnow
from app.models.project import Project, ProjectStatus
from app.repositories.project_repository import ProjectRepository
from app.services.health_service import HealthService, HealthState
from app.services.port_discovery_service import PortDiscoveryService


@dataclass
class PendingChange:
    project_id: str
    name: str
    branch: str | None
    dirty_count: int


@dataclass
class ActiveService:
    project_id: str
    project_name: str
    key: str
    label: str
    url: str | None
    port: int | None
    state: str
    #: O painel prova que quem responde nessa porta é deste projeto — porque
    #: foi ele quem subiu, porque o processo roda dentro do diretório do
    #: projeto, ou porque o Compose marcou o container.
    proven: bool = True
    #: Quando não há prova, o que se sabe de quem está na porta. É o que separa
    #: "seu projeto está no ar" de "alguém está nessa porta".
    owner_hint: str | None = None


@dataclass
class PortConflict:
    port: int
    projects: list[str]


@dataclass
class RecentProject:
    id: str
    name: str
    status: str
    last_accessed_at: datetime | None


@dataclass
class Dashboard:
    totals: dict[str, int] = field(default_factory=dict)
    pending_changes: list[PendingChange] = field(default_factory=list)
    active_services: list[ActiveService] = field(default_factory=list)
    port_conflicts: list[PortConflict] = field(default_factory=list)
    recent_projects: list[RecentProject] = field(default_factory=list)
    #: Projetos cujo estado de saúde o verificador já mediu ao menos uma vez.
    #: Sem esta lista, a tela não consegue separar "nenhum serviço respondeu"
    #: de "ninguém perguntou ainda" — e as duas coisas viravam "0 online".
    checked_project_ids: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=utcnow)
    from_cache: bool = False


CACHE_KEY = "dashboard"


def avaliar_dono(project: Project, dono) -> tuple[bool, str | None]:  # type: ignore[no-untyped-def]
    """Decide se dá para afirmar que quem responde na porta é deste projeto.

    A verificação de saúde abre um socket e pergunta "tem alguém aí?". Nunca
    soube perguntar "quem?", e as duas respostas divergem sempre que dois
    projetos declaram a mesma porta.

    Sem observação nenhuma — antes do primeiro ciclo do poller — o resultado é
    "provado". Não saber não é o mesmo que desconfiar, e marcar tudo como
    suspeito no primeiro minuto de uso seria pior que o defeito que isto
    conserta.

    Mora aqui, e não dentro do Dashboard, porque a listagem de projetos faz a
    mesma pergunta para colorir o grafo. Duas cópias da regra divergiriam, e o
    painel passaria a dar duas respostas para "este projeto está no ar?".
    """
    if dono is None:
        return True, None

    if dono.project_id == project.id:
        if dono.strong_evidence:
            return True, None
        return False, (
            f"Responde, mas o painel não prova que é deste projeto — "
            f"quem ocupa a porta é {dono.process_name or 'um processo'}."
        )

    if dono.project_id:
        return False, (
            f"Quem ocupa a porta é {dono.process_name or 'um processo'}, "
            f"do {dono.project_name}."
        )

    return False, (
        f"Responde, mas sem dono conhecido — "
        f"quem ocupa a porta é {dono.process_name or 'um processo'}."
    )


class DashboardService:
    def __init__(
        self,
        session: Session,
        cache: TTLCache,
        health: HealthService,
        ports: PortDiscoveryService | None = None,
    ) -> None:
        self.repo = ProjectRepository(session)
        self.cache = cache
        self.health = health
        #: Só leitura do que o poller já observou — nada de varrer aqui, que é
        #: caminho de requisição. Serve para responder "quem está nessa porta?",
        #: pergunta que a verificação de saúde nunca soube fazer.
        self.ports = ports

    def build(self) -> Dashboard:
        cached = self.cache.get(CACHE_KEY)
        if cached is not None:
            cached.from_cache = True
            return cached

        projects, total = self.repo.list(limit=500)

        active_services = self._active_services(projects)

        dashboard = Dashboard(
            checked_project_ids=self._medidos(projects),
            totals=self._totals(projects, total, active_services),
            pending_changes=self._pending_changes(projects),
            active_services=active_services,
            port_conflicts=self._port_conflicts(projects),
            recent_projects=self._recent(projects),
            from_cache=False,
        )
        self.cache.set(CACHE_KEY, dashboard)
        return dashboard

    def invalidate(self) -> None:
        self.cache.invalidate(CACHE_KEY)

    # --- blocos ---

    def _totals(
        self,
        projects: list[Project],
        total: int,
        active_services: list[ActiveService],
    ) -> dict[str, int]:
        """Contagens do topo do dashboard.

        "Rodando" vem do **health observado**, não da coluna `status`. O
        `status` do projeto nunca chega a `RUNNING` sozinho: ele descreve o
        registro, não o processo. Contar por ele mostrava "0 rodando" na mesma
        tela que listava quatro serviços online — a incoerência que faz o
        usuário parar de acreditar no painel.
        """
        by_status: dict[str, int] = defaultdict(int)
        for project in projects:
            by_status[project.status] += 1

        com_docker = sum(
            1
            for project in projects
            if any(tech.name in ("docker", "docker-compose") for tech in project.technologies)
        )

        # Só conta quem tem prova. Contar porta respondida faria "5 rodando"
        # numa máquina com dois projetos de pé e três coincidências de número.
        rodando = {service.project_id for service in active_services if service.proven}
        sem_diretorio = by_status.get(ProjectStatus.MISSING.value, 0)
        parados = max(total - len(rodando) - sem_diretorio, 0)

        return {
            "projects": total,
            "running": len(rodando),
            "stopped": parados,
            "missing": sem_diretorio,
            "with_docker": com_docker,
            "pinned": sum(1 for project in projects if project.is_pinned),
        }

    def _pending_changes(self, projects: list[Project]) -> list[PendingChange]:
        """Lê do cache de Git preenchido pelas consultas já feitas.

        Sem cache, o campo fica vazio em vez de disparar `git status` para cada
        projeto — o que é justamente o que travaria a tela.
        """
        pendentes: list[PendingChange] = []

        for project in projects:
            status = self.cache.get(f"git.status:{project.id}")
            if status is None or not getattr(status, "is_repo", False):
                continue
            if status.dirty_count > 0:
                pendentes.append(
                    PendingChange(
                        project_id=project.id,
                        name=project.name,
                        branch=status.current_branch,
                        dirty_count=status.dirty_count,
                    )
                )

        return sorted(pendentes, key=lambda item: item.dirty_count, reverse=True)[:10]

    def _medidos(self, projects: list[Project]) -> list[str]:
        """Quem já passou pelo verificador — leitura de cache, sem tocar a rede.

        O poller cobre projeto fixado e recente. Para os outros, "0 de 3 online"
        é uma afirmação que ninguém apurou; a tela precisa poder dizer isso.
        """
        medidos = []
        for project in projects:
            for service in project.services:
                if self.health.last_known(project.id, service.key).state != HealthState.UNKNOWN:
                    medidos.append(project.id)
                    break
        return medidos

    def _active_services(self, projects: list[Project]) -> list[ActiveService]:
        """Serviços que respondem — separando os que são deste projeto.

        A verificação de saúde abre um socket e pergunta "tem alguém aí?".
        Nunca soube perguntar "quem?", e as duas respostas divergem sempre que
        dois projetos declaram a mesma porta padrão: o Dashboard-contabil
        apareceu "no ar" mostrando o container da PLATAFORMA DE INGRESSOS, que
        é quem realmente ocupava a 8000.

        Aqui a resposta da porta é cruzada com a atribuição que a descoberta já
        fez. Sem prova de dono, o serviço continua aparecendo — o painel não
        finge que a porta está muda —, mas marcado, e **fora** da contagem de
        projetos rodando.
        """
        observadas = self.ports.last_known().by_port() if self.ports is not None else {}
        ativos: list[ActiveService] = []

        for project in projects:
            for service in project.services:
                resultado = self.health.last_known(project.id, service.key)
                if resultado.state != HealthState.ONLINE:
                    continue

                dono = observadas.get(service.port) if service.port else None
                provado, pista = avaliar_dono(project, dono)

                ativos.append(
                    ActiveService(
                        project_id=project.id,
                        project_name=project.name,
                        key=service.key,
                        label=service.label,
                        url=service.url,
                        port=service.port,
                        state=resultado.state.value,
                        proven=provado,
                        owner_hint=pista,
                    )
                )

        # Provados primeiro: é o que a pessoa foi ver.
        ativos.sort(key=lambda item: not item.proven)
        return ativos[:20]



    def _port_conflicts(self, projects: list[Project]) -> list[PortConflict]:
        """Duas coisas disputando a mesma porta é a dor que aparece na hora errada."""
        por_porta: dict[int, set[str]] = defaultdict(set)

        for project in projects:
            for service in project.services:
                if service.port:
                    por_porta[service.port].add(project.name)

        return [
            PortConflict(port=porta, projects=sorted(nomes))
            for porta, nomes in sorted(por_porta.items())
            if len(nomes) > 1
        ]

    def _recent(self, projects: list[Project]) -> list[RecentProject]:
        com_acesso = [p for p in projects if p.last_accessed_at is not None]
        com_acesso.sort(key=lambda p: p.last_accessed_at, reverse=True)  # type: ignore[arg-type,return-value]

        return [
            RecentProject(
                id=project.id,
                name=project.name,
                status=project.status,
                last_accessed_at=project.last_accessed_at,
            )
            for project in com_acesso[:8]
        ]
