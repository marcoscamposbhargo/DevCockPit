"""JobManager — fila em memória de operações longas (ADR-006).

Três responsabilidades que não estavam no prompt original e são o que torna a
Fase 3b possível:

1. **Saída incremental.** O cliente vê o progresso enquanto o comando roda.
2. **Exclusão mútua por chave.** Dois `compose up` no mesmo projeto ao mesmo
   tempo é uma classe inteira de bug que simplesmente não existe (FR-057).
3. **Timeout com encerramento de árvore.** Processo travado não fica.

Estado é volátil por decisão (D-07): o resultado final vai para `activity_log`,
que é persistente. O processo em si morre com o servidor de qualquer forma.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable

from app.core.errors import DomainError, OperationInProgress
from app.jobs.job import Job, JobStatus
from app.models.base import utcnow
from app.runner.async_runner import AsyncCommandRunner
from app.runner.command_spec import CommandResult, CommandSpec

logger = logging.getLogger(__name__)


def _require_event_loop() -> None:
    """Falha cedo e com mensagem útil.

    `asyncio.create_task` exige loop em execução. Uma rota declarada com `def`
    (em vez de `async def`) roda em threadpool e não tem loop — o erro nativo,
    "no running event loop", não diz o que fazer.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError as exc:
        raise RuntimeError(
            "JobManager.submit exige um event loop em execução. "
            "A rota que enfileira job precisa ser declarada com `async def`."
        ) from exc

#: Assinatura de quem quer registrar o resultado final na auditoria.
AuditHook = Callable[[Job, CommandResult | None], Awaitable[None] | None]


class JobManager:
    def __init__(
        self,
        runner: AsyncCommandRunner | None = None,
        *,
        output_limit: int = 2 * 1024 * 1024,
        retention_s: float = 3600.0,
        audit_hook: AuditHook | None = None,
    ) -> None:
        self.runner = runner or AsyncCommandRunner()
        self.output_limit = output_limit
        self.retention_s = retention_s
        self.audit_hook = audit_hook

        self._jobs: dict[str, Job] = {}
        self._active_by_key: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # --- consulta ---

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, *, project_id: str | None = None, limit: int = 50) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        if project_id is not None:
            jobs = [job for job in jobs if job.project_id == project_id]
        return jobs[:limit]

    def active_for_key(self, key: str) -> Job | None:
        job_id = self._active_by_key.get(key)
        return self._jobs.get(job_id) if job_id else None

    # --- submissão ---

    def submit(
        self,
        spec: CommandSpec,
        *,
        key: str,
        action: str | None = None,
        project_id: str | None = None,
    ) -> Job:
        """Enfileira um comando. Levanta `OperationInProgress` se a chave está ocupada.

        A chave é o mecanismo de FR-057: `docker:{project_id}` garante que dois
        `up` no mesmo projeto não coexistam, sem impedir `up` em projetos
        diferentes ao mesmo tempo.
        """
        _require_event_loop()

        existing = self.active_for_key(key)
        if existing is not None and not existing.status.is_final:
            raise OperationInProgress(
                f"Já existe uma operação em andamento para este projeto "
                f"({existing.action}, job {existing.id})."
            )

        job = Job(
            id=f"j_{uuid.uuid4().hex[:10]}",
            action=action or spec.label,
            key=key,
            project_id=project_id,
        )
        self._jobs[job.id] = job
        self._active_by_key[key] = job.id
        self._tasks[job.id] = asyncio.create_task(self._execute(job, spec))

        self._purge_old()
        return job

    def submit_callable(
        self,
        work: Callable[[Job], Awaitable[str | None]],
        *,
        key: str,
        action: str,
        project_id: str | None = None,
    ) -> Job:
        """Enfileira trabalho em processo, não comando externo.

        Usado pela varredura de disco, que é código Python e não subprocess.
        Ganha o mesmo estado, a mesma exclusão mútua e o mesmo console da UI —
        e é assim que a varredura da Fase 2 cumpre a promessa de D-23.
        """
        _require_event_loop()

        existing = self.active_for_key(key)
        if existing is not None and not existing.status.is_final:
            raise OperationInProgress(
                f"Já existe uma operação em andamento ({existing.action}, job {existing.id})."
            )

        job = Job(id=f"j_{uuid.uuid4().hex[:10]}", action=action, key=key, project_id=project_id)
        self._jobs[job.id] = job
        self._active_by_key[key] = job.id
        self._tasks[job.id] = asyncio.create_task(self._execute_callable(job, work))

        self._purge_old()
        return job

    async def _execute_callable(
        self,
        job: Job,
        work: Callable[[Job], Awaitable[str | None]],
    ) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()

        try:
            message = await work(job)
        except DomainError as exc:
            job.status = JobStatus.FAILED
            job.message = exc.message
        except Exception as exc:  # noqa: BLE001 - job não pode derrubar o servidor
            job.status = JobStatus.FAILED
            job.message = f"Falha: {exc}"
            logger.exception("job falhou", extra={"extra_fields": {"job_id": job.id}})
        else:
            job.status = JobStatus.CANCELLED if job.cancel_requested else JobStatus.SUCCESS
            job.message = message
            job.exit_code = 0
        finally:
            job.finished_at = utcnow()
            if self._active_by_key.get(job.key) == job.id:
                del self._active_by_key[job.key]
            self._tasks.pop(job.id, None)

        if self.audit_hook is not None:
            try:
                outcome = self.audit_hook(job, None)
                if asyncio.iscoroutine(outcome):
                    await outcome
            except Exception:  # noqa: BLE001
                logger.exception("hook de auditoria falhou")

    async def _execute(self, job: Job, spec: CommandSpec) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        result: CommandResult | None = None

        def on_line(_channel: str, line: str) -> None:
            # stdout e stderr entram sem distinção, de propósito: `docker
            # compose` e `git` escrevem **progresso** em stderr, e marcar tudo
            # como erro treinaria o usuário a ignorar a marcação. O que separa
            # sucesso de falha é o código de saída, que já vira o status do job
            # e a mensagem final.
            job.append(line, limit=self.output_limit)

        try:
            result = await self.runner.run(spec, on_line=on_line, cancel_event=job.cancel_event)
        except Exception as exc:  # noqa: BLE001 - job não pode derrubar o servidor
            job.status = JobStatus.FAILED
            job.message = f"Falha ao executar: {exc}"
            logger.exception(
                "job falhou",
                extra={"extra_fields": {"job_id": job.id, "action": job.action}},
            )
        else:
            job.exit_code = result.exit_code
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.message = "Operação cancelada."
            elif result.timed_out:
                job.status = JobStatus.TIMEOUT
                job.message = f"Excedeu o tempo limite de {spec.timeout_s:.0f}s."
            elif result.ok:
                job.status = JobStatus.SUCCESS
            else:
                job.status = JobStatus.FAILED
                job.message = _first_error_line(result) or f"Código de saída {result.exit_code}."
        finally:
            job.finished_at = utcnow()
            if self._active_by_key.get(job.key) == job.id:
                del self._active_by_key[job.key]
            self._tasks.pop(job.id, None)

        if self.audit_hook is not None:
            try:
                outcome = self.audit_hook(job, result)
                if asyncio.iscoroutine(outcome):
                    await outcome
            except Exception:  # noqa: BLE001 - auditoria não pode derrubar o job
                logger.exception("hook de auditoria falhou")

    # --- cancelamento e limpeza ---

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.status.is_final:
            return job
        job.request_cancel()
        return job

    async def wait(self, job_id: str, timeout: float = 30.0) -> Job | None:
        """Aguarda a conclusão. Usado em testes e no encerramento da aplicação."""
        task = self._tasks.get(job_id)
        if task is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return self._jobs.get(job_id)

    async def shutdown(self, timeout: float = 10.0) -> None:
        for job in list(self._jobs.values()):
            if not job.status.is_final:
                job.request_cancel()

        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    def _purge_old(self) -> None:
        """Descarta job concluído há mais tempo que a retenção."""
        now = utcnow()
        for job_id, job in list(self._jobs.items()):
            if not job.status.is_final or job.finished_at is None:
                continue
            if (now - job.finished_at).total_seconds() >= self.retention_s:
                del self._jobs[job_id]


def _first_error_line(result: CommandResult) -> str | None:
    for line in result.stderr.splitlines():
        if line.strip():
            return line.strip()[:300]
    return None
