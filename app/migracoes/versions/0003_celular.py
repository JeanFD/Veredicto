"""Voto por celular configurável por sessão (desligado por padrão: só urnas).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE sessoes ADD COLUMN celular INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE sessoes DROP COLUMN celular")
