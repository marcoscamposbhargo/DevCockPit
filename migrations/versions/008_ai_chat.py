"""Mensagens do chat e gasto diário de tokens.

Entram agora, na fase em que passam a ser escritas — e não antes.

Revision ID: 008_ai_chat
Revises: 007_ai_task
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_ai_chat"
down_revision = "007_ai_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_message",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(40),
            sa.ForeignKey("ai_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Resumo do contexto, não o conteúdo: o contexto carrega trecho de
        # código do projeto, e copiá-lo dobraria o banco do painel para nada.
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("context_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_message_session", "ai_message", ["session_id", "id"])

    op.create_table(
        "ai_usage_day",
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_day")
    op.drop_index("ix_ai_message_session", table_name="ai_message")
    op.drop_table("ai_message")
