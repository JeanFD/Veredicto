"""Caso (júri) da sessão, para agrupar a lista como as pastas dos cartões.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE sessoes ADD COLUMN caso TEXT NOT NULL DEFAULT ''")


def downgrade():
    op.execute("ALTER TABLE sessoes DROP COLUMN caso")
