"""Cartões do telão: pano de fundo, notícias e laudos preparados antes da sessão.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE cartoes (
            id INTEGER PRIMARY KEY,
            pasta TEXT NOT NULL,
            titulo TEXT NOT NULL,
            texto TEXT NOT NULL,
            fonte TEXT NOT NULL DEFAULT '',
            no_telao INTEGER NOT NULL DEFAULT 0,
            criado_em TEXT NOT NULL
        )
    """)


def downgrade():
    op.execute("DROP TABLE cartoes")
