"""Tarefas: o que falta, o que está em curso, o que já foi.

A regra de ordenação é a única opinião deste serviço, e está escrita num lugar
só: **em curso antes de aberta, prioridade antes de idade, mais velha antes de
mais nova**. Tarefa começada e largada é o que mais custa lembrar; tarefa antiga
subindo na lista é o que evita o backlog virar depósito.
"""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.base import utcnow
from app.models.task import AiTask, TaskStatus

PRIORIDADE_MIN = 1
PRIORIDADE_MAX = 3


class TaskService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- leitura ---

    def list(self, project_id: str, *, include_done: bool = True, limit: int = 200):  # type: ignore[no-untyped-def]
        stmt = select(AiTask).where(AiTask.project_id == project_id)
        if not include_done:
            stmt = stmt.where(AiTask.status.in_([TaskStatus.OPEN.value, TaskStatus.DOING.value]))

        stmt = stmt.order_by(self._ordem(), AiTask.priority, AiTask.created_at).limit(limit)
        return list(self.session.execute(stmt).scalars())

    def next_for(self, project_ids: list[str]) -> dict[str, AiTask]:
        """A próxima tarefa de cada projeto, numa consulta só.

        O "Meu dia" precisa disso para dezenove projetos; perguntar um a um
        seriam dezenove consultas no caminho da requisição (NFR-010).
        """
        if not project_ids:
            return {}

        stmt = (
            select(AiTask)
            .where(
                AiTask.project_id.in_(project_ids),
                AiTask.status.in_([TaskStatus.OPEN.value, TaskStatus.DOING.value]),
            )
            .order_by(AiTask.project_id, self._ordem(), AiTask.priority, AiTask.created_at)
        )

        proximas: dict[str, AiTask] = {}
        for tarefa in self.session.execute(stmt).scalars():
            proximas.setdefault(tarefa.project_id, tarefa)
        return proximas

    def counts_for(self, project_ids: list[str]) -> dict[str, int]:
        """Quantas tarefas abertas por projeto."""
        if not project_ids:
            return {}

        stmt = (
            select(AiTask.project_id, func.count())
            .where(
                AiTask.project_id.in_(project_ids),
                AiTask.status.in_([TaskStatus.OPEN.value, TaskStatus.DOING.value]),
            )
            .group_by(AiTask.project_id)
        )
        return {str(pid): int(total) for pid, total in self.session.execute(stmt)}

    # --- escrita ---

    def create(
        self,
        project_id: str,
        *,
        title: str,
        detail: str | None = None,
        priority: int = 2,
        source: str = "human",
        session_id: str | None = None,
    ) -> AiTask:
        titulo = (title or "").strip()
        if not titulo:
            raise ValidationError("Toda tarefa precisa de um título.")

        tarefa = AiTask(
            project_id=project_id,
            title=titulo[:200],
            detail=(detail or "").strip() or None,
            priority=self._validar_prioridade(priority),
            source=source,
            session_id=session_id,
        )
        self.session.add(tarefa)
        self.session.flush()
        return tarefa

    def update(
        self,
        task_id: int,
        *,
        title: str | None = None,
        detail: str | None = None,
        status: str | None = None,
        priority: int | None = None,
    ) -> AiTask:
        tarefa = self.get(task_id)

        if title is not None:
            novo = title.strip()
            if not novo:
                raise ValidationError("Toda tarefa precisa de um título.")
            tarefa.title = novo[:200]
        if detail is not None:
            tarefa.detail = detail.strip() or None
        if priority is not None:
            tarefa.priority = self._validar_prioridade(priority)
        if status is not None:
            self._mudar_estado(tarefa, status)

        self.session.flush()
        return tarefa

    def delete(self, task_id: int) -> None:
        self.session.delete(self.get(task_id))
        self.session.flush()

    def get(self, task_id: int) -> AiTask:
        tarefa = self.session.get(AiTask, task_id)
        if tarefa is None:
            raise ValidationError(f"Tarefa {task_id} não encontrada.")
        return tarefa

    # --- regras ---

    @staticmethod
    def _ordem():  # type: ignore[no-untyped-def]
        """Em curso primeiro; depois aberta; feita e descartada no fim.

        Tarefa começada e largada é o que mais custa lembrar — por isso ela
        encabeça a lista, mesmo com prioridade menor.
        """
        return case(
            (AiTask.status == TaskStatus.DOING.value, 0),
            (AiTask.status == TaskStatus.OPEN.value, 1),
            (AiTask.status == TaskStatus.DONE.value, 2),
            else_=3,
        )

    @staticmethod
    def _mudar_estado(tarefa: AiTask, status: str) -> None:
        conhecidos = {item.value for item in TaskStatus}
        if status not in conhecidos:
            raise ValidationError(
                f"Estado inválido: {status!r}. Conhecidos: {', '.join(sorted(conhecidos))}."
            )

        tarefa.status = status
        # `done_at` marca quando saiu da lista, seja por conclusão ou por
        # desistência: as duas encerram, e a data serve ao resumo da sessão.
        tarefa.done_at = utcnow() if TaskStatus(status).is_final else None

    @staticmethod
    def _validar_prioridade(priority: int) -> int:
        try:
            valor = int(priority)
        except (TypeError, ValueError) as erro:
            raise ValidationError("Prioridade precisa ser 1, 2 ou 3.") from erro
        if not PRIORIDADE_MIN <= valor <= PRIORIDADE_MAX:
            raise ValidationError("Prioridade precisa ser 1 (alta), 2 (média) ou 3 (baixa).")
        return valor
