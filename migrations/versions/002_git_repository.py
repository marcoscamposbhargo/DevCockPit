"""Cache de estado do repositório Git.

Revision ID: 002_git_repository
Revises: 001_initial
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_git_repository"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "git_repository",
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("is_repo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_branch", sa.String(200), nullable=True),
        sa.Column("head_sha", sa.String(64), nullable=True),
        sa.Column("remote_origin_url", sa.String(400), nullable=True),
        sa.Column("provider", sa.String(20), nullable=True),
        sa.Column("dirty_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ahead", sa.Integer(), nullable=True),
        sa.Column("behind", sa.Integer(), nullable=True),
        sa.Column("last_commit_subject", sa.Text(), nullable=True),
        sa.Column("last_commit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("git_repository")
