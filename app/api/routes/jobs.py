"""Rotas de job: consulta, listagem, cancelamento e SSE.

O SSE tem fallback: o cliente que não conseguir manter o stream aberto usa
`GET /api/jobs/{id}?after=<revision>` em polling. Antivírus e proxy locais no
Windows interferem em conexão persistente, então a dependência única seria
frágil (ADR-006).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_job_manager
from app.core.errors import DomainError
from app.jobs.job import Job
from app.jobs.job_manager import JobManager
from app.schemas.job import JobList, JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

SSE_HEARTBEAT_S = 15.0
SSE_POLL_S = 0.25


class JobNotFound(DomainError):
    code = "JOB_NOT_FOUND"
    status_code = 404
    default_message = "Job não encontrado."


def _to_out(job: Job, after: int = 0) -> JobOut:
    """`after` permite ao cliente pedir só as linhas que ainda não viu."""
    lines = job.lines[after:] if after > 0 else job.lines
    return JobOut(
        id=job.id,
        action=job.action,
        project_id=job.project_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        exit_code=job.exit_code,
        duration_ms=job.duration_ms,
        message=job.message,
        output="\n".join(lines),
        revision=job.revision,
        line_count=len(job.lines),
        output_truncated=job.output_truncated,
    )


def _require(manager: JobManager, job_id: str) -> Job:
    job = manager.get(job_id)
    if job is None:
        raise JobNotFound(f"Job {job_id!r} não encontrado ou já descartado.")
    return job


@router.get("", response_model=JobList)
def list_jobs(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    manager: JobManager = Depends(get_job_manager),
) -> JobList:
    jobs = manager.list(project_id=project_id, limit=limit)
    return JobList(items=[_to_out(job) for job in jobs])


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    after: int = Query(default=0, ge=0, description="devolve só as linhas após este índice"),
    manager: JobManager = Depends(get_job_manager),
) -> JobOut:
    return _to_out(_require(manager, job_id), after=after)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: str,
    manager: JobManager = Depends(get_job_manager),
) -> JobOut:
    _require(manager, job_id)
    job = manager.cancel(job_id)
    return _to_out(job)  # type: ignore[arg-type]


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str,
    request: Request,
    manager: JobManager = Depends(get_job_manager),
) -> StreamingResponse:
    job = _require(manager, job_id)

    async def events():  # type: ignore[no-untyped-def]
        delivered = 0
        idle = 0.0

        while True:
            if await request.is_disconnected():
                break

            if job.revision > delivered:
                chunk = job.lines[delivered:]
                delivered = len(job.lines)
                idle = 0.0
                payload = json.dumps({"lines": chunk, "revision": delivered})
                yield f"event: log\ndata: {payload}\n\n"

            if job.status.is_final:
                final = json.dumps(
                    {
                        "status": job.status.value,
                        "exit_code": job.exit_code,
                        "duration_ms": job.duration_ms,
                        "message": job.message,
                    }
                )
                yield f"event: end\ndata: {final}\n\n"
                break

            await asyncio.sleep(SSE_POLL_S)
            idle += SSE_POLL_S

            # Comentário SSE serve de keep-alive: proxy local costuma fechar
            # conexão silenciosa.
            if idle >= SSE_HEARTBEAT_S:
                idle = 0.0
                yield ": keep-alive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
