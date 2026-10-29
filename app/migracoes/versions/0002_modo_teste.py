"""Modo teste: sessões e urnas marcadas como teste, apagáveis de uma vez.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE sessoes ADD COLUMN teste INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE urnas ADD COLUMN teste INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE sessoes DROP COLUMN teste")
    op.execute("ALTER TABLE urnas DROP COLUMN teste")
