"""Configuração Docker por projeto.

Revision ID: 003_docker_config
Revises: 002_git_repository
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_docker_config"
down_revision = "002_git_repository"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "docker_config",
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Relativo ao diretório do projeto, nunca absoluto: mantém o registro
        # portável e força a resolução por core/paths.py.
        sa.Column("compose_file", sa.String(200), nullable=True),
        sa.Column("project_name", sa.String(120), nullable=True),
        sa.Column("has_dockerfile", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detected_services", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("docker_config")
