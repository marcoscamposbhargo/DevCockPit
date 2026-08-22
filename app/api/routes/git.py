"""Rotas de Git — somente leitura.

Não existe rota de escrita, e isso é decisão de segurança (FR-038), não
omissão. Um teste garante que a allowlist não ganhe `commit`, `reset`,
`clean`, `checkout` nem `push`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_git_service, get_project_service
from app.models.base import utcnow
from app.schemas.git import (
    BranchList,
    ChangedFileOut,
    CommitList,
    CommitOut,
    GitStatusOut,
    RemoteList,
    RemoteOut,
)
from app.services.git_service import GitService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects/{project_id}/git", tags=["git"])


@router.get("/status", response_model=GitStatusOut)
def git_status(
    project_id: str,
    file_limit: int = Query(default=50, ge=1, le=500),
    projects: ProjectService = Depends(get_project_service),
    git: GitService = Depends(get_git_service),
) -> GitStatusOut:
    project = projects.get(project_id)
    status = git.status(project.id, project.path, file_limit=file_limit)

    return GitStatusOut(
        is_repo=status.is_repo,
        repo_root=status.repo_root,
        inside_other_repo=status.inside_other_repo,
        current_branch=status.current_branch,
        detached=status.detached,
        head_sha=status.head_sha,
        ahead=status.ahead,
        behind=status.behind,
        counts=status.counts,
        dirty_count=status.dirty_count,
        files=[
            ChangedFileOut(path=f.path, change=f.change, staged=f.staged) for f in status.files
        ],
        files_truncated=status.files_truncated,
        checked_at=utcnow(),
    )


@router.get("/commits", response_model=CommitList)
def git_commits(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    projects: ProjectService = Depends(get_project_service),
    git: GitService = Depends(get_git_service),
) -> CommitList:
    project = projects.get(project_id)
    return CommitList(
        items=[CommitOut(**commit) for commit in git.commits(project.id, project.path, limit)]
    )


@router.get("/branches", response_model=BranchList)
def git_branches(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    git: GitService = Depends(get_git_service),
) -> BranchList:
    project = projects.get(project_id)
    status = git.status(project.id, project.path, file_limit=1)
    return BranchList(
        items=git.branches(project.id, project.path),
        current=status.current_branch,
    )


@router.get("/remotes", response_model=RemoteList)
def git_remotes(
    project_id: str,
    projects: ProjectService = Depends(get_project_service),
    git: GitService = Depends(get_git_service),
) -> RemoteList:
    project = projects.get(project_id)
    return RemoteList(
        items=[RemoteOut(**remote) for remote in git.remotes(project.id, project.path)]
    )
