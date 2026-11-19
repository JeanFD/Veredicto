"""Aparência do telão (cores, textos e revelação), configurada pelo admin no painel.

Uma linha só, com a configuração em JSON: o que não está nela segue o padrão.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE aparencia_telao (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            config TEXT NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("INSERT INTO aparencia_telao (id) VALUES (1)")


def downgrade():
    op.execute("DROP TABLE aparencia_telao")
