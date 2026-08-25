"""Sessão de trabalho, memória de projeto e autoria na auditoria.

Fundação do Cockpit AI (Fase 1). Nada aqui depende de provedor de IA: uma
sessão registrada e uma memória consultável respondem "onde eu parei?" com a
IA desligada.

`ai_message` fica para a fase do chat, quando alguém passar a escrever nela.

Revision ID: 006_ai_session_memory
Revises: 005_dev_server
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_ai_session_memory"
down_revision = "005_dev_server"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_session",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("next_steps", sa.Text(), nullable=True),
        # JSON com o que foi observado no período: sha e branch no começo e no
        # fim, commits, ações executadas, serviços que caíram.
        sa.Column("facts", sa.Text(), nullable=True),
    )
    op.create_index("ix_ai_session_project", "ai_session", ["project_id", "started_at"])

    op.create_table(
        "ai_memory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Nulo = memória global do desenvolvedor.
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="human"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "session_id",
            sa.String(40),
            sa.ForeignKey("ai_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("relevance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_memory_project_kind", "ai_memory", ["project_id", "kind"])

    # `server_default` mantém válido todo o histórico já gravado: ação sem
    # autor declarado é ação do usuário, que é a verdade do que existe hoje.
    op.add_column(
        "activity_log",
        sa.Column("actor", sa.String(10), nullable=False, server_default="user"),
    )
    op.add_column("activity_log", sa.Column("agent", sa.String(30), nullable=True))
    op.add_column("activity_log", sa.Column("reason", sa.Text(), nullable=True))

    op.add_column(
        "project",
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("project", "ai_enabled")
    op.drop_column("activity_log", "reason")
    op.drop_column("activity_log", "agent")
    op.drop_column("activity_log", "actor")
    op.drop_index("ix_ai_memory_project_kind", table_name="ai_memory")
    op.drop_table("ai_memory")
    op.drop_index("ix_ai_session_project", table_name="ai_session")
    op.drop_table("ai_session")
