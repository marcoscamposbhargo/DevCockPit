"""Rotas do manifesto `devcockpit.yml` (FR-110, FR-111, FR-112).

Três operações, todas iniciadas pelo usuário. Nenhuma roda sozinha, e a única
que escreve no disco do projeto exige `confirm: true` no corpo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_manifest_service, get_project_service
from app.schemas.manifest import (
    ManifestExportRequest,
    ManifestExportResult,
    ManifestImportResult,
    ManifestPreview,
    ManifestStatus,
)
from app.schemas.project import ServiceOut
from app.services.manifest_service import ManifestService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects/{project_id}/manifest", tags=["manifest"])


@router.get("", response_model=ManifestStatus)
def manifest_status(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    manifests: ManifestService = Depends(get_manifest_service),
) -> ManifestStatus:
    """Estado do manifesto e a comparação com o banco, sem alterar nada.

    Arquivo ausente, YAML quebrado e versão desconhecida devolvem `200` com
    aviso: a tela do projeto precisa carregar de qualquer jeito.
    """
    project = projects.get(project_id)
    read = manifests.read(project)
    diff = manifests.compare(project, read)

    return ManifestStatus(
        exists=read.exists,
        filename=read.filename,
        valid=read.valid,
        version=read.manifest.version if read.manifest else None,
        warnings=read.warnings,
        diff=diff,
        in_sync=read.valid and not diff,
    )


@router.get("/preview", response_model=ManifestPreview)
def manifest_preview(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    manifests: ManifestService = Depends(get_manifest_service),
) -> ManifestPreview:
    """O YAML que a exportação escreveria. Ver antes de gravar é o ponto."""
    project = projects.get(project_id)
    return ManifestPreview(content=manifests.render(project))


@router.post("/import", response_model=ManifestImportResult)
def manifest_import(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    manifests: ManifestService = Depends(get_manifest_service),
) -> ManifestImportResult:
    project = projects.get(project_id)
    read = manifests.read(project)
    applied = manifests.import_into(project, read)

    return ManifestImportResult(
        applied=applied,
        warnings=read.warnings,
        services=[ServiceOut.model_validate(service) for service in project.services],
    )


@router.post("/export", response_model=ManifestExportResult)
def manifest_export(
    project_id: str,
    payload: ManifestExportRequest,
    projects: ProjectService = Depends(get_project_service),
    manifests: ManifestService = Depends(get_manifest_service),
) -> ManifestExportResult:
    """Única escrita do DevCockpit dentro de pasta de projeto."""
    project = projects.get(project_id)
    destino, escritos, sobrescrito = manifests.export(project, confirm=payload.confirm)

    return ManifestExportResult(
        path=destino.as_posix(), bytes_written=escritos, overwritten=sobrescrito
    )
