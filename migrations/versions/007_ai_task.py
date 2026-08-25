"""Tarefa de projeto.

O que falta fazer, no mínimo que responde "qual é a próxima?": título,
prioridade e estado. Sem sprint, sem estimativa, sem responsável — é um painel
de um desenvolvedor só.

Revision ID: 007_ai_task
Revises: 006_ai_session_memory
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_ai_task"
down_revision = "006_ai_session_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_task",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("source", sa.String(20), nullable=False, server_default="human"),
        sa.Column(
            "session_id",
            sa.String(40),
            sa.ForeignKey("ai_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    # A consulta que importa é sempre a mesma: as abertas deste projeto, da
    # mais prioritária para a menos.
    op.create_index(
        "ix_ai_task_project_status", "ai_task", ["project_id", "status", "priority"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_task_project_status", table_name="ai_task")
    op.drop_table("ai_task")
