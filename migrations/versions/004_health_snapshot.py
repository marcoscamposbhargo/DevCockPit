"""Histórico de health check.

Revision ID: 004_health_snapshot
Revises: 003_docker_config
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_health_snapshot"
down_revision = "003_docker_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service_key", sa.String(32), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_health_service_checked", "health_snapshot", ["project_id", "service_key", "checked_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_health_service_checked", table_name="health_snapshot")
    op.drop_table("health_snapshot")
