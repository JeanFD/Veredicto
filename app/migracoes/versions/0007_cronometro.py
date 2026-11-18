"""Cronômetro das falas no telão: uma linha só, com o estado da contagem.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-18
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE cronometro (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            titulo TEXT NOT NULL DEFAULT '',
            restante REAL NOT NULL DEFAULT 0,
            fim_em REAL NOT NULL DEFAULT 0,
            rodando INTEGER NOT NULL DEFAULT 0,
            visivel INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("INSERT INTO cronometro (id) VALUES (1)")


def downgrade():
    op.execute("DROP TABLE cronometro")
