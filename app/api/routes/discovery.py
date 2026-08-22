"""Descoberta de projetos: varredura, candidatos e importação em lote."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_discovery_service, get_job_manager, get_project_service
from app.core.errors import DomainError
from app.jobs.job import Job
from app.jobs.job_manager import JobManager
from app.schemas.git import (
    CandidateOut,
    ImportItemResult,
    ImportRequest,
    ImportResponse,
    ScanRequest,
    ScanResponse,
)
from app.schemas.job import JobAccepted
from app.schemas.project import ProjectCreate
from app.services.discovery_service import DiscoveryService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

SCAN_KEY = "discovery:scan"

#: Último resultado de varredura, por raiz. A varredura roda como job, então o
#: resultado não cabe na resposta HTTP que devolve 202.
_last_scan: dict[str, ScanResponse] = {}


def _to_response(result) -> ScanResponse:  # type: ignore[no-untyped-def]
    return ScanResponse(
        root=result.root,
        scanned_dirs=result.scanned_dirs,
        truncated=result.truncated,
        skipped_dirs=result.skipped_dirs,
        items=[CandidateOut(**vars(candidate)) for candidate in result.candidates],
    )


@router.post("/scan", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def scan(
    payload: ScanRequest,
    service: DiscoveryService = Depends(get_discovery_service),
    manager: JobManager = Depends(get_job_manager),
) -> JobAccepted:
    """Dispara a varredura como job (FR-090, cumprindo D-23).

    Valida a raiz **antes** de enfileirar: erro de allowlist tem que aparecer na
    hora, não escondido num job que falha depois.

    A rota é `async` por necessidade: `submit_callable` cria uma task, e uma
    rota síncrona roda em threadpool, onde não há event loop. Vale para toda
    rota que enfileira job.
    """
    service.assert_root_allowed(payload.root)

    async def work(job: Job) -> str:
        job.append(f"Varrendo {payload.root}…", limit=1024 * 64)
        result = await asyncio.to_thread(service.scan, payload.root, payload.max_depth)
        response = _to_response(result)
        _last_scan[response.root] = response

        job.append(
            f"{len(response.items)} candidato(s) em {response.scanned_dirs} diretório(s).",
            limit=1024 * 64,
        )
        for skipped in response.skipped_dirs:
            job.append(f"sem permissão, ignorado: {skipped}", limit=1024 * 64)

        return f"{len(response.items)} candidato(s) encontrado(s)."

    job = manager.submit_callable(work, key=SCAN_KEY, action="discovery.scan")
    return JobAccepted(job_id=job.id, action=job.action, status=job.status)


@router.get("/candidates", response_model=ScanResponse)
def candidates(
    root: str,
    service: DiscoveryService = Depends(get_discovery_service),
) -> ScanResponse:
    """Resultado da última varredura daquela raiz.

    A chave é o path **resolvido**, não o texto que o cliente digitou: caixa
    diferente ou barra no fim não podem virar "nenhum candidato".
    """
    resolved = service.assert_root_allowed(root).as_posix()
    found = _last_scan.get(resolved)
    if found is None:
        return ScanResponse(
            root=resolved, scanned_dirs=0, truncated=False, skipped_dirs=[], items=[]
        )
    return found


@router.post("/import", response_model=ImportResponse)
def import_candidates(
    payload: ImportRequest,
    projects: ProjectService = Depends(get_project_service),
) -> ImportResponse:
    """Cadastra vários candidatos. Falha individual não aborta o lote."""
    items: list[ImportItemResult] = []

    for path in payload.paths:
        try:
            project = projects.create(ProjectCreate(path=path, run_detection=True))
            items.append(ImportItemResult(path=path, ok=True, project_id=project.id))
        except DomainError as exc:
            items.append(
                ImportItemResult(path=path, ok=False, error_code=exc.code, message=exc.message)
            )

    imported = sum(1 for item in items if item.ok)
    return ImportResponse(imported=imported, failed=len(items) - imported, items=items)


@router.delete("/candidates", status_code=status.HTTP_204_NO_CONTENT)
def clear_candidates() -> Response:
    _last_scan.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
