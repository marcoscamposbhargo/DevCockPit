"""Acesso a dados de sessão, memória e execução da IA."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.ai import AiMemory, AiMessage, AiSession, AiUsageDay
from app.models.ai_run import STATUS_DE_FALHA, AiRun, RunStatus
from app.models.base import utcnow


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiSession) -> AiSession:
        self.session.add(registro)
        self.session.flush()
        return registro

    def get(self, session_id: str) -> AiSession | None:
        return self.session.get(AiSession, session_id)

    def open_for(self, project_id: str) -> AiSession | None:
        """A sessão aberta deste projeto, se houver.

        Uma por projeto: abrir a segunda encerra a primeira. Sessão esquecida
        aberta por três dias não mede nada.
        """
        stmt = (
            select(AiSession)
            .where(AiSession.project_id == project_id, AiSession.ended_at.is_(None))
            .order_by(AiSession.started_at.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def last_closed(self, project_id: str) -> AiSession | None:
        stmt = (
            select(AiSession)
            .where(AiSession.project_id == project_id, AiSession.ended_at.is_not(None))
            .order_by(AiSession.ended_at.desc())
        )
        return self.session.execute(stmt).scalars().first()

    def list_for(self, project_id: str, limit: int = 20) -> list[AiSession]:
        stmt = (
            select(AiSession)
            .where(AiSession.project_id == project_id)
            .order_by(AiSession.started_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def open_sessions(self) -> list[AiSession]:
        stmt = select(AiSession).where(AiSession.ended_at.is_(None))
        return list(self.session.execute(stmt).scalars())

    def last_closed_by_project(self) -> dict[str, AiSession]:
        """A última sessão encerrada de cada projeto, numa consulta só.

        O briefing do dia precisa disso para 19 projetos; perguntar um a um
        seriam 19 consultas no caminho da requisição (NFR-010).
        """
        recente = (
            select(AiSession.project_id, func.max(AiSession.ended_at).label("fim"))
            .where(AiSession.ended_at.is_not(None))
            .group_by(AiSession.project_id)
            .subquery()
        )
        stmt = select(AiSession).join(
            recente,
            (AiSession.project_id == recente.c.project_id)
            & (AiSession.ended_at == recente.c.fim),
        )
        return {s.project_id: s for s in self.session.execute(stmt).scalars()}


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiMemory) -> AiMemory:
        self.session.add(registro)
        self.session.flush()
        return registro

    def get(self, memory_id: int) -> AiMemory | None:
        return self.session.get(AiMemory, memory_id)

    def delete(self, registro: AiMemory) -> None:
        self.session.delete(registro)
        self.session.flush()

    def list(
        self,
        *,
        project_id: str | None = None,
        global_only: bool = False,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[AiMemory]:
        stmt = select(AiMemory)
        if global_only:
            stmt = stmt.where(AiMemory.project_id.is_(None))
        elif project_id is not None:
            stmt = stmt.where(AiMemory.project_id == project_id)
        if kind is not None:
            stmt = stmt.where(AiMemory.kind == kind)

        # Confirmada antes de sugerida, e mais nova antes de mais velha: o que
        # alguém afirmou vale mais que o que ainda é palpite.
        stmt = stmt.order_by(
            AiMemory.confirmed_at.is_(None), AiMemory.updated_at.desc()
        ).limit(limit)
        return list(self.session.execute(stmt).scalars())

    def prune_unconfirmed(self, before: datetime) -> int:
        """Apaga sugestão que ninguém confirmou e já envelheceu."""
        alvos = self.session.execute(
            select(AiMemory).where(
                AiMemory.confirmed_at.is_(None), AiMemory.created_at < before
            )
        ).scalars()

        apagados = 0
        for registro in alvos:
            self.session.delete(registro)
            apagados += 1

        # `autoflush` está desligado nesta sessão: sem descarregar, a linha
        # apagada continua voltando na consulta seguinte, e a poda pareceria
        # não ter funcionado.
        self.session.flush()
        return apagados


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiMessage) -> AiMessage:
        self.session.add(registro)
        self.session.flush()
        return registro

    def list_for(self, session_id: str, limit: int = 50) -> list[AiMessage]:
        """As mensagens de uma sessão, em ordem de conversa.

        A consulta pega as **últimas** e devolve na ordem certa: numa conversa
        longa, o que interessa é o fim, mas ler de trás para a frente não é
        conversa.
        """
        stmt = (
            select(AiMessage)
            .where(AiMessage.session_id == session_id)
            .order_by(AiMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(list(self.session.execute(stmt).scalars())))


class UsageRepository:
    """Gasto por dia. Uma linha, criada na primeira chamada do dia."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _hoje() -> str:
        # Dia **local**: quem lê a tela pensa no próprio calendário, não em UTC.
        return utcnow().astimezone().date().isoformat()

    def today(self) -> AiUsageDay:
        dia = self._hoje()
        registro = self.session.get(AiUsageDay, dia)
        if registro is None:
            registro = AiUsageDay(day=dia)
            self.session.add(registro)
            self.session.flush()
        return registro

    def add(self, *, tokens_in: int = 0, tokens_out: int = 0) -> AiUsageDay:
        registro = self.today()
        registro.tokens_in += max(0, int(tokens_in))
        registro.tokens_out += max(0, int(tokens_out))
        registro.calls += 1
        self.session.flush()
        return registro

    def recent(self, days: int = 14) -> list[AiUsageDay]:
        stmt = select(AiUsageDay).order_by(AiUsageDay.day.desc()).limit(days)
        return list(self.session.execute(stmt).scalars())


@dataclass(frozen=True)
class RunSummary:
    """O consumo de um período, já agregado.

    Todo campo que pode não ter sido medido é `None`, nunca `0` (**P-02**):
    banco vazio devolve custo, latência e data de preço nulos, e a tela diz "não
    medido" em vez de anunciar que o dia saiu de graça.
    """

    attempts: int
    #: Perguntas distintas — `correlation_id` diferentes no período.
    questions: int
    tokens_in: int
    tokens_out: int

    local_attempts: int
    local_tokens: int
    cloud_attempts: int
    cloud_tokens: int

    #: `None` quando nenhuma tentativa do período tinha preço declarado.
    estimated_cost: float | None
    #: A data mais recente entre as tabelas de preço usadas. Vai junto do custo
    #: aonde ele aparecer (REQ-11).
    price_date: str | None
    #: Quantas tentativas entraram na conta sem custo conhecido. É o que permite
    #: a tela dizer "parcial" em vez de apresentar um total como se fosse tudo.
    attempts_without_cost: int

    #: `None` quando nenhuma tentativa chegou a ser executada.
    avg_latency_ms: float | None
    #: `timeout` e `error`. `skipped` não conta: não é falha, é candidato que a
    #: cadeia nem chegou a tentar.
    failures: int
    #: Perguntas que precisaram de mais de uma tentativa.
    fallbacks: int


class RunRepository:
    """As tentativas de execução da IA (REQ-10).

    Nenhum método aqui abre transação longa. O runner acumula as tentativas em
    memória e chama `add_all` **depois** do stream fechar: gravar durante o
    stream deixa a transação aberta pelos minutos da resposta e devolve
    `database is locked` em botão sem relação com a IA — foi exatamente o que
    aconteceu na Fase 3 (`fbabea1`).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, registro: AiRun) -> AiRun:
        self.session.add(registro)
        self.session.flush()
        return registro

    def add_all(self, registros: Iterable[AiRun]) -> list[AiRun]:
        """Grava a cadeia inteira de uma vez, num `flush` só."""
        linhas = list(registros)
        if not linhas:
            return []
        self.session.add_all(linhas)
        self.session.flush()
        return linhas

    def list_for(self, correlation_id: str) -> list[AiRun]:
        """As tentativas de uma pergunta, na ordem em que a cadeia tentou.

        Ordena por `attempt` e desempata por `id`: é a ordem de leitura de quem
        quer entender por que a resposta veio do terceiro provedor.
        """
        stmt = (
            select(AiRun)
            .where(AiRun.correlation_id == correlation_id)
            .order_by(AiRun.attempt, AiRun.id)
        )
        return list(self.session.execute(stmt).scalars())

    def aggregate(
        self,
        *,
        since: datetime,
        until: datetime | None = None,
        local_providers: Collection[str],
    ) -> RunSummary:
        """O consumo entre `since` e `until`, para a tela do REQ-12.

        `local_providers` vem de quem chama, não daqui: a linha não guarda se o
        provedor é local ou de nuvem — isso é declaração de `configs/ai.yml`, e
        um provedor pode mudar de lado sem que o histórico mude de significado.

        As somas de custo e a média de latência saem do SQL **sem `coalesce`**
        de propósito: `NULL` agregado já é "ninguém mediu", que é a resposta
        certa (**P-02**). Trocar por `0` seria inventar o número.
        """
        fim = until if until is not None else utcnow()
        periodo = (AiRun.created_at >= since, AiRun.created_at <= fim)
        eh_local = AiRun.provider.in_(list(local_providers))
        executada = AiRun.status != RunStatus.SKIPPED.value

        stmt = select(
            func.count(AiRun.id),
            func.count(func.distinct(AiRun.correlation_id)),
            func.coalesce(func.sum(AiRun.tokens_in), 0),
            func.coalesce(func.sum(AiRun.tokens_out), 0),
            func.coalesce(func.sum(case((eh_local, 1), else_=0)), 0),
            func.coalesce(
                func.sum(case((eh_local, AiRun.tokens_in + AiRun.tokens_out), else_=0)), 0
            ),
            func.coalesce(func.sum(case((eh_local, 0), else_=1)), 0),
            func.coalesce(
                func.sum(case((eh_local, 0), else_=AiRun.tokens_in + AiRun.tokens_out)), 0
            ),
            func.sum(AiRun.estimated_cost),
            func.max(AiRun.price_date),
            func.coalesce(func.sum(case((AiRun.estimated_cost.is_(None), 1), else_=0)), 0),
            func.avg(case((executada, AiRun.latency_ms))),
            func.coalesce(
                func.sum(case((AiRun.status.in_(sorted(STATUS_DE_FALHA)), 1), else_=0)), 0
            ),
            func.count(func.distinct(case((AiRun.attempt > 1, AiRun.correlation_id)))),
        ).where(*periodo)

        linha = self.session.execute(stmt).one()
        custo = linha[8]
        return RunSummary(
            attempts=int(linha[0]),
            questions=int(linha[1]),
            tokens_in=int(linha[2]),
            tokens_out=int(linha[3]),
            local_attempts=int(linha[4]),
            local_tokens=int(linha[5]),
            cloud_attempts=int(linha[6]),
            cloud_tokens=int(linha[7]),
            estimated_cost=float(custo) if custo is not None else None,
            price_date=linha[9],
            attempts_without_cost=int(linha[10]),
            avg_latency_ms=float(linha[11]) if linha[11] is not None else None,
            failures=int(linha[12]),
            fallbacks=int(linha[13]),
        )
