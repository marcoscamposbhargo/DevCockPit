"""Sessão de trabalho: abrir, encerrar e — sobretudo — reunir os fatos.

A parte que importa deste serviço não é guardar texto. É esta: **o resumo de
uma sessão é montado do que o painel observou**, não redigido de memória por
ninguém, nem por um modelo depois.

`git log` diz quais commits nasceram no período. `activity_log` diz o que foi
executado. `health_snapshot` diz o que caiu. Um resumo com essa base é registro;
sem ela seria um diário simpático e inútil — e, quando a IA entrar (Fase 2),
seria texto gerado alimentando texto gerado.

Uma sessão aberta por projeto. Abrir a segunda encerra a primeira: sessão
esquecida aberta por três dias não mede nada.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.ai import AiSession
from app.models.base import utcnow
from app.models.project import ActivityLog, HealthSnapshot, Project
from app.repositories.ai_repository import SessionRepository

logger = logging.getLogger(__name__)

#: Teto de itens guardados por lista de fatos. Uma sessão de doze horas pode
#: ter centenas de ações; o que serve ao resumo são as primeiras.
LIMITE_FATOS = 40


@dataclass
class MarcoGit:
    """O estado do Git num instante — começo ou fim da sessão."""

    branch: str | None = None
    head_sha: str | None = None
    dirty_count: int | None = None
    #: `False` quando o diretório não é repositório: aí não há marco nenhum e
    #: o resumo não finge que há.
    is_repo: bool = False


@dataclass
class FatosDaSessao:
    """O que o painel observou entre o início e o fim.

    Tudo aqui é fato registrado por outro subsistema. Nada é dedução.
    """

    git_start: MarcoGit = field(default_factory=MarcoGit)
    git_end: MarcoGit | None = None
    commits: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    services_down: list[dict] = field(default_factory=list)
    duration_minutes: int | None = None
    truncated: bool = False


class SessionService:
    def __init__(
        self,
        session: Session,
        git=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self.session = session
        self.repo = SessionRepository(session)
        #: Opcional: sem Git o resto continua funcionando, e os marcos ficam
        #: como "não é repositório". Ausência de dependência externa nunca vira
        #: erro de tela (NFR-060).
        self.git = git

    # --- abrir ---

    def start(self, project: Project, objective: str | None = None) -> AiSession:
        aberta = self.repo.open_for(project.id)
        if aberta is not None:
            # Encerrar a anterior antes de abrir é mais honesto que recusar: a
            # pessoa quer trabalhar agora, e a sessão esquecida de ontem não
            # pode virar obstáculo.
            self.end(project, note="Encerrada automaticamente ao abrir uma nova sessão.")

        fatos = FatosDaSessao(git_start=self._marco_git(project))
        registro = AiSession(
            id=f"s_{uuid.uuid4().hex[:10]}",
            project_id=project.id,
            started_at=utcnow(),
            objective=(objective or "").strip() or None,
            facts=json.dumps(asdict(fatos), ensure_ascii=False),
        )
        return self.repo.add(registro)

    # --- encerrar ---

    def end(
        self,
        project: Project,
        *,
        summary: str | None = None,
        next_steps: str | None = None,
        note: str | None = None,
    ) -> AiSession:
        registro = self.repo.open_for(project.id)
        if registro is None:
            raise ValidationError(
                f"Não há sessão aberta em {project.name}. Inicie uma antes de encerrar."
            )

        fim = utcnow()
        fatos = self._reunir_fatos(project, registro, fim)

        registro.ended_at = fim
        registro.facts = json.dumps(asdict(fatos), ensure_ascii=False)
        registro.summary = (summary or "").strip() or self._resumir(fatos, note)
        registro.next_steps = (next_steps or "").strip() or None
        self.session.flush()
        return registro

    # --- leitura ---

    def current(self, project: Project) -> AiSession | None:
        return self.repo.open_for(project.id)

    def previous(self, project: Project) -> AiSession | None:
        return self.repo.last_closed(project.id)

    def history(self, project: Project, limit: int = 20) -> list[AiSession]:
        return self.repo.list_for(project.id, limit=limit)

    def get(self, session_id: str) -> AiSession:
        registro = self.repo.get(session_id)
        if registro is None:
            raise ValidationError(f"Sessão {session_id} não encontrada.")
        return registro

    @staticmethod
    def facts_of(registro: AiSession) -> FatosDaSessao:
        """Lê o JSON de fatos com tolerância: registro velho não pode quebrar a tela."""
        if not registro.facts:
            return FatosDaSessao()
        try:
            dados = json.loads(registro.facts)
        except json.JSONDecodeError:
            logger.warning("fatos ilegíveis", extra={"extra_fields": {"session": registro.id}})
            return FatosDaSessao()

        fatos = FatosDaSessao()
        fatos.git_start = MarcoGit(**(dados.get("git_start") or {}))
        fim = dados.get("git_end")
        fatos.git_end = MarcoGit(**fim) if fim else None
        fatos.commits = dados.get("commits") or []
        fatos.actions = dados.get("actions") or []
        fatos.services_down = dados.get("services_down") or []
        fatos.duration_minutes = dados.get("duration_minutes")
        fatos.truncated = bool(dados.get("truncated"))
        return fatos

    # --- coleta ---

    def _marco_git(self, project: Project) -> MarcoGit:
        if self.git is None:
            return MarcoGit()
        try:
            estado = self.git.status(project.id, project.path)
        except Exception:  # noqa: BLE001 - Git ausente não impede trabalhar
            logger.debug("git indisponível para marco de sessão", exc_info=True)
            return MarcoGit()

        if not getattr(estado, "is_repo", False):
            return MarcoGit()
        return MarcoGit(
            branch=estado.current_branch,
            head_sha=estado.head_sha,
            dirty_count=estado.dirty_count,
            is_repo=True,
        )

    def _reunir_fatos(
        self, project: Project, registro: AiSession, fim: datetime
    ) -> FatosDaSessao:
        fatos = self.facts_of(registro)
        fatos.git_end = self._marco_git(project)
        fatos.duration_minutes = max(
            0, int((fim - registro.started_at).total_seconds() // 60)
        )
        fatos.commits = self._commits_do_periodo(project, fatos)
        fatos.actions = self._acoes(project.id, registro.started_at, fim)
        fatos.services_down = self._quedas(project.id, registro.started_at, fim)
        return fatos

    def _commits_do_periodo(self, project: Project, fatos: FatosDaSessao) -> list[dict]:
        """Commits que nasceram entre o marco inicial e agora.

        O corte é pelo `sha` do início, e não por data: relógio de commit pode
        vir de rebase, de outra máquina ou de fuso diferente, e contar por data
        traria commit alheio para dentro da sessão.
        """
        if self.git is None or not fatos.git_start.is_repo:
            return []

        inicio = fatos.git_start.head_sha
        try:
            self.git.invalidate(project.id)
            recentes = self.git.commits(project.id, project.path, limit=LIMITE_FATOS)
        except Exception:  # noqa: BLE001
            logger.debug("não foi possível ler commits da sessão", exc_info=True)
            return []

        novos: list[dict] = []
        for commit in recentes:
            sha = commit.get("sha") if isinstance(commit, dict) else getattr(commit, "sha", None)
            if inicio and sha and sha.startswith(inicio[:7]):
                break
            novos.append(
                commit
                if isinstance(commit, dict)
                else {
                    "sha": getattr(commit, "sha", None),
                    "subject": getattr(commit, "subject", None),
                    "author": getattr(commit, "author", None),
                }
            )
        return novos

    def _acoes(self, project_id: str, inicio: datetime, fim: datetime) -> list[dict]:
        stmt = (
            select(ActivityLog)
            .where(
                ActivityLog.project_id == project_id,
                ActivityLog.created_at >= inicio,
                ActivityLog.created_at <= fim,
            )
            .order_by(ActivityLog.created_at)
            .limit(LIMITE_FATOS)
        )
        return [
            {
                "action": item.action,
                "status": item.status,
                "at": item.created_at.isoformat(),
                "message": (item.message or "")[:200] or None,
            }
            for item in self.session.execute(stmt).scalars()
        ]

    def _quedas(self, project_id: str, inicio: datetime, fim: datetime) -> list[dict]:
        """Serviços que saíram do ar durante a sessão.

        Só a transição para fora de `ONLINE` interessa: o histórico grava
        mudança de estado, então cada linha aqui é uma queda observada, não uma
        amostragem repetida.
        """
        stmt = (
            select(HealthSnapshot)
            .where(
                HealthSnapshot.project_id == project_id,
                HealthSnapshot.checked_at >= inicio,
                HealthSnapshot.checked_at <= fim,
                HealthSnapshot.state != "ONLINE",
            )
            .order_by(HealthSnapshot.checked_at)
            .limit(LIMITE_FATOS)
        )
        return [
            {
                "service": item.service_key,
                "state": item.state,
                "at": item.checked_at.isoformat(),
            }
            for item in self.session.execute(stmt).scalars()
        ]

    # --- redação ---

    @staticmethod
    def _resumir(fatos: FatosDaSessao, note: str | None = None) -> str:
        """Resumo montado dos fatos, em português corrido.

        Sem modelo nenhum: é contagem e concordância. Quando a Fase 2 chegar, o
        modelo vai redigir melhor **a partir destes mesmos fatos** — nunca no
        lugar deles.
        """
        partes: list[str] = []

        if fatos.duration_minutes is not None:
            horas, minutos = divmod(fatos.duration_minutes, 60)
            tempo = f"{horas}h{minutos:02d}" if horas else f"{minutos} min"
            partes.append(f"Sessão de {tempo}.")

        if fatos.commits:
            quantos = len(fatos.commits)
            primeiro = fatos.commits[0].get("subject") or ""
            partes.append(
                f"{quantos} commit(s)"
                + (f", o último: “{primeiro[:80]}”." if primeiro else ".")
            )
        elif fatos.git_start.is_repo:
            partes.append("Nenhum commit no período.")

        fim = fatos.git_end
        if fim and fim.is_repo and fim.dirty_count:
            partes.append(f"{fim.dirty_count} arquivo(s) sem commit ao encerrar.")

        if fatos.actions:
            falhas = sum(1 for a in fatos.actions if a.get("status") != "SUCCESS")
            partes.append(
                f"{len(fatos.actions)} ação(ões) pelo painel"
                + (f", {falhas} sem sucesso." if falhas else ".")
            )

        if fatos.services_down:
            servicos = sorted({q["service"] for q in fatos.services_down})
            partes.append("Saiu do ar durante a sessão: " + ", ".join(servicos) + ".")

        if note:
            partes.append(note)

        return " ".join(partes) or "Sessão sem atividade registrada."
