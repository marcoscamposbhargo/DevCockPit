"""Start My Day — o que merece sua atenção hoje, sem IA nenhuma.

Todo o conteúdo desta tela sai de coisas que o painel já mede: última sessão,
próximos passos declarados, alteração pendente no Git, serviço no ar, conflito
de porta. Nenhuma linha é dedução de modelo, e por isso ela funciona no dia em
que não houver provedor configurado — que é o argumento inteiro da Fase 1.

A ordenação é o produto aqui. Dezenove projetos listados em ordem alfabética
não ajudam ninguém a decidir por onde começar; o que ajuda é dizer o que está
esperando, o que ficou pela metade e o que já está de pé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.project import Project, ProjectStatus
from app.repositories.ai_repository import SessionRepository
from app.repositories.project_repository import ProjectRepository

#: Depois disto, um projeto que já teve sessão é "parado" — não é abandono,
#: é só o que vale lembrar de retomar.
DIAS_ATE_ESFRIAR = 7

#: Quantos projetos entram no briefing. A tela existe para decidir o próximo
#: passo, e uma lista de dezenove decide nada.
LIMITE = 6


@dataclass
class ItemDoDia:
    project_id: str
    name: str
    #: Por que este projeto está nesta posição — em texto, para a tela poder
    #: explicar em vez de só ordenar.
    reason: str
    next_step: str | None = None
    last_session_at: datetime | None = None
    last_summary: str | None = None
    open_session: bool = False
    dirty_count: int | None = None
    services_online: int = 0
    score: int = 0


@dataclass
class Briefing:
    generated_at: datetime
    total_projects: int
    open_sessions: list[str] = field(default_factory=list)
    items: list[ItemDoDia] = field(default_factory=list)
    suggestion: str | None = None


class BriefingService:
    def __init__(self, session: Session, cache=None, health=None) -> None:  # type: ignore[no-untyped-def]
        self.projects = ProjectRepository(session)
        self.sessions = SessionRepository(session)
        #: Só leitura do que o poller e as consultas já colocaram lá. Nada é
        #: buscado no disco por aqui: é caminho de requisição (NFR-010).
        self.cache = cache
        self.health = health

    def build(self) -> Briefing:
        projetos, total = self.projects.list(limit=200)
        ultimas = self.sessions.last_closed_by_project()
        abertas = {s.project_id: s for s in self.sessions.open_sessions()}
        agora = utcnow()

        itens: list[ItemDoDia] = []
        for project in projetos:
            if project.status == ProjectStatus.MISSING.value:
                continue
            itens.append(self._avaliar(project, ultimas, abertas, agora))

        itens.sort(key=lambda item: (-item.score, item.name))
        escolhidos = itens[:LIMITE]

        return Briefing(
            generated_at=agora,
            total_projects=total,
            open_sessions=[abertas[pid].project_id for pid in abertas],
            items=escolhidos,
            suggestion=escolhidos[0].name if escolhidos else None,
        )

    def _avaliar(self, project: Project, ultimas, abertas, agora) -> ItemDoDia:  # type: ignore[no-untyped-def]
        sessao = ultimas.get(project.id)
        aberta = abertas.get(project.id)
        item = ItemDoDia(
            project_id=project.id,
            name=project.name,
            reason="",
            open_session=aberta is not None,
            last_session_at=aberta.started_at if aberta else (sessao.ended_at if sessao else None),
            last_summary=sessao.summary if sessao else None,
            next_step=(sessao.next_steps if sessao else None),
        )

        estado = self.cache.get(f"git.status:{project.id}") if self.cache else None
        if estado is not None and getattr(estado, "is_repo", False):
            item.dirty_count = estado.dirty_count

        item.services_online = self._online(project)

        # A pontuação é a opinião da tela, e está escrita aqui em vez de
        # espalhada: sessão aberta é o mais urgente (alguém esqueceu de
        # encerrar, ou parou no meio), próximo passo declarado vem depois —
        # é trabalho que já foi pensado e só espera execução.
        pontos = 0
        motivos: list[str] = []

        if aberta is not None:
            pontos += 100
            quando = aberta.started_at.astimezone().strftime("%d/%m %H:%M")
            motivos.append(f"sessão aberta desde {quando}")
        if item.next_step:
            pontos += 50
            motivos.append("próximo passo já definido")
        if item.dirty_count:
            pontos += 20
            motivos.append(f"{item.dirty_count} arquivo(s) sem commit")
        if item.services_online:
            pontos += 10
            motivos.append(f"{item.services_online} serviço(s) no ar")
        if project.is_pinned:
            pontos += 15
            motivos.append("fixado")

        if sessao is not None and sessao.ended_at is not None:
            parado = agora - sessao.ended_at
            if parado > timedelta(days=DIAS_ATE_ESFRIAR):
                motivos.append(f"parado há {parado.days} dias")
            else:
                pontos += 10

        item.score = pontos
        item.reason = "; ".join(motivos) or "sem sessão registrada ainda"
        return item

    def _online(self, project: Project) -> int:
        """Serviços que o verificador viu no ar.

        Pelo `HealthService`, e não lendo o cache na mão: é ele quem sabe
        marcar `STALE` quando o dado envelheceu, e dado velho apresentado como
        atual é o que destrói a confiança na tela (D-18).
        """
        if self.health is None:
            return 0
        return sum(
            1
            for service in project.services
            if str(self.health.last_known(project.id, service.key).state) == "ONLINE"
        )
