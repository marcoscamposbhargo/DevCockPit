"""Processo de servidor de desenvolvimento iniciado pelo painel.

O PID precisa sobreviver a um reinício do DevCockpit. Sem isso, quem subisse o
servidor pelo painel e depois reiniciasse o painel perderia o botão de parar —
e ficaria com um processo que só o Gerenciador de Tarefas alcança.

Revision ID: 005_dev_server
Revises: 004_health_snapshot
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_dev_server"
down_revision = "004_health_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dev_server",
        sa.Column(
            "project_id",
            sa.String(80),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pid", sa.Integer(), nullable=False),
        # Guardado para conferir o PID na volta: identificador de processo é
        # reciclado pelo sistema, e parar o PID errado seria matar o processo
        # de outra pessoa.
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("cwd", sa.Text(), nullable=False),
        sa.Column("log_file", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dev_server")
