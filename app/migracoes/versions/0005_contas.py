"""Contas individuais com papel (admin, mesário, monitor) e logins com validade.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE contas (
            usuario TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            papel TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            ativa INTEGER NOT NULL DEFAULT 1,
            criada_em TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE logins (
            token_hash TEXT PRIMARY KEY,
            usuario TEXT NOT NULL REFERENCES contas(usuario),
            expira_em REAL NOT NULL
        )
    """)


def downgrade():
    op.execute("DROP TABLE logins")
    op.execute("DROP TABLE contas")
