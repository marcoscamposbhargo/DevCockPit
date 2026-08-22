"""Health da própria aplicação.

A UI usa isto para desabilitar preventivamente as ações cujas ferramentas não
existem, em vez de deixar o usuário clicar e falhar (FR-074).
"""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends

from app.api.deps import get_roots_dep, get_settings_dep
from app.core.config import RootsConfig, Settings
from app.schemas.project import HealthOut, ToolAvailability

router = APIRouter(prefix="/api/health", tags=["health"])


def _tool_available(configured: str, default_name: str) -> bool:
    candidate = configured or default_name
    return shutil.which(candidate) is not None


@router.get("", response_model=HealthOut)
def health(
    settings: Settings = Depends(get_settings_dep),
    roots: RootsConfig = Depends(get_roots_dep),
) -> HealthOut:
    return HealthOut(
        status="ok",
        version=settings.version,
        tools=ToolAvailability(
            git=_tool_available(settings.git_bin, "git"),
            docker=_tool_available(settings.docker_bin, "docker"),
            code=_tool_available(settings.code_bin, "code"),
        ),
        allowed_roots=[root.as_posix() for root in roots.allowed_roots],
    )
