"""Pedidos de cadastro de urna: a urna pede com um código curto e o mesário aprova.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-29
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE pedidos_urna (
            segredo_hash TEXT PRIMARY KEY,
            codigo TEXT NOT NULL UNIQUE,
            criado_em REAL NOT NULL,
            urna_id TEXT,
            token TEXT
        )
    """)


def downgrade():
    op.execute("DROP TABLE pedidos_urna")
