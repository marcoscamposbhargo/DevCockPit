"""Uma linha por tentativa de execução da IA.

Tabela nova, nenhuma coluna alterada, nenhum dado migrado. Ela existe porque com
cadeia de fallback uma pergunta tem várias execuções, e guardar só a que
respondeu apaga o motivo de a resposta ter vindo de onde veio.

Sem coluna de prompt e sem coluna de resposta (REQ-10). `estimated_cost` e
`price_date` anuláveis de propósito: `null` é "não medido", e `0` seria afirmar
que a chamada saiu de graça (**P-02**).

Reversão: `downgrade` derruba a tabela. Nada depende dela, e a tela de consumo
degrada para "não medido" se ela sumir.

Revision ID: 010_ai_run
Revises: 009_ai_especialista
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010_ai_run"
down_revision = "009_ai_especialista"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Comum às tentativas da mesma pergunta.
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("task_type", sa.String(24), nullable=False),
        # auto | manual
        sa.Column("decision", sa.String(8), nullable=False, server_default="auto"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        # ok | timeout | error | skipped
        sa.Column("status", sa.String(8), nullable=False),
        # Anuláveis por P-02: sem preço declarado, fica `null` — nunca `0`.
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("price_date", sa.String(10), nullable=True),
        # Mensagem já mascarada por app/services/ai/redaction.py.
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_run_correlation", "ai_run", ["correlation_id", "attempt"])


def downgrade() -> None:
    op.drop_index("ix_ai_run_correlation", table_name="ai_run")
    op.drop_table("ai_run")
