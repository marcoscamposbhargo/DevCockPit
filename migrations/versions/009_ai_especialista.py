"""Quem respondeu, e com qual prompt.

Duas colunas em `ai_message`. A primeira responde "qual chapéu atendeu"; a
segunda liga a resposta ao **texto** que a produziu.

A segunda parece exagero até o prompt mudar. Depois disso, uma resposta guardada
sem a versão vira algo que ninguém consegue explicar: o texto que a gerou não
existe mais em lugar nenhum.

Revision ID: 009_ai_especialista
Revises: 008_ai_chat
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_ai_especialista"
down_revision = "008_ai_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_message", sa.Column("agent", sa.String(length=30), nullable=True))
    op.add_column("ai_message", sa.Column("prompt_versao", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_message", "prompt_versao")
    op.drop_column("ai_message", "agent")
