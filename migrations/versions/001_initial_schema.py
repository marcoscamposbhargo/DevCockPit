"""Schema inicial: project, project_technology, project_service, activity_log.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("path", sa.String(500), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="REGISTERED"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detection_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_status", "project", ["status"])
    op.create_index("ix_project_last_accessed", "project", ["last_accessed_at"])

    op.create_table(
        "project_technology",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("source", sa.String(10), nullable=False, server_default="DETECTED"),
        sa.Column("evidence", sa.String(200), nullable=True),
        sa.UniqueConstraint("project_id", "name", name="uq_project_technology"),
    )

    op.create_table(
        "project_service",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("host", sa.String(80), nullable=False, server_default="localhost"),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(300), nullable=True),
        sa.Column("health_url", sa.String(300), nullable=True),
        sa.Column("health_kind", sa.String(10), nullable=False, server_default="TCP"),
        sa.Column("open_in_browser", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("project_id", "key", name="uq_project_service"),
    )
    op.create_index("ix_project_service_port", "project_service", ["port"])

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("argv", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_activity_project_created", "activity_log", ["project_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_activity_project_created", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_index("ix_project_service_port", table_name="project_service")
    op.drop_table("project_service")
    op.drop_table("project_technology")
    op.drop_index("ix_project_last_accessed", table_name="project")
    op.drop_index("ix_project_status", table_name="project")
    op.drop_table("project")
