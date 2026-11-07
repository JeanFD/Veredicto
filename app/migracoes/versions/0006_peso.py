"""Peso dos votos: por urna, do voto por celular por sessão, e guardado em cada voto.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE urnas ADD COLUMN peso INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE sessoes ADD COLUMN peso_celular INTEGER NOT NULL DEFAULT 1")
    # o peso com que o voto foi recebido: o resultado não depende do peso atual da urna
    op.execute("ALTER TABLE votos ADD COLUMN peso INTEGER NOT NULL DEFAULT 1")


def downgrade():
    op.execute("ALTER TABLE votos DROP COLUMN peso")
    op.execute("ALTER TABLE sessoes DROP COLUMN peso_celular")
    op.execute("ALTER TABLE urnas DROP COLUMN peso")
