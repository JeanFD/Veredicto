"""Esquema inicial: as tabelas como estavam antes do Alembic.

Também adota bancos criados antes do Alembic (como o de produção): as tabelas
são criadas só se faltarem e as colunas que entraram depois são acrescentadas
só se faltarem, sem tocar nos dados.

Revision ID: 0001
Revises:
Create Date: 2026-10-27
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# questionário: perguntas encadeadas são sessões com o mesmo grupo_id (o id da
# primeira), cada uma com estado próprio; sessão avulsa tem grupo_id nulo
TABELAS = """
    CREATE TABLE IF NOT EXISTS sessoes (
        id INTEGER PRIMARY KEY,
        tema TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'AGUARDANDO',
        ativa INTEGER NOT NULL DEFAULT 0,
        encerrada_em TEXT,
        arquivada INTEGER NOT NULL DEFAULT 0,
        grupo_id INTEGER,
        pergunta INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS opcoes (
        id INTEGER PRIMARY KEY,
        sessao_id INTEGER NOT NULL REFERENCES sessoes(id),
        chave TEXT NOT NULL,
        rotulo TEXT NOT NULL,
        cor TEXT NOT NULL,
        ordem INTEGER NOT NULL,
        UNIQUE (sessao_id, chave)
    );
    CREATE TABLE IF NOT EXISTS urnas (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        ativa INTEGER NOT NULL DEFAULT 1,
        reserva INTEGER NOT NULL DEFAULT 0,
        criada_em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS votos (
        id TEXT PRIMARY KEY,
        sessao_id INTEGER NOT NULL REFERENCES sessoes(id),
        urna_id TEXT NOT NULL REFERENCES urnas(id),
        opcao_chave TEXT NOT NULL,
        votado_em TEXT NOT NULL,
        recebido_em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY,
        tipo TEXT NOT NULL,
        detalhe TEXT NOT NULL DEFAULT '',
        em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS cedulas (
        token_hash TEXT PRIMARY KEY,
        sessao_id INTEGER NOT NULL REFERENCES sessoes(id),
        criada_em TEXT NOT NULL,
        voto_id TEXT,
        seguinte_emitida INTEGER NOT NULL DEFAULT 0
    )
"""

# colunas acrescentadas depois da criação das tabelas, antes do Alembic
COLUNAS_TARDIAS = [
    ("sessoes", "arquivada", "INTEGER NOT NULL DEFAULT 0"),
    ("sessoes", "grupo_id", "INTEGER"),
    ("sessoes", "pergunta", "INTEGER NOT NULL DEFAULT 1"),
    ("cedulas", "seguinte_emitida", "INTEGER NOT NULL DEFAULT 0"),
]


def upgrade():
    conexao = op.get_bind()
    for comando in TABELAS.split(";"):
        op.execute(comando)
    for tabela, coluna, definicao in COLUNAS_TARDIAS:
        existentes = {c[1] for c in conexao.exec_driver_sql(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            op.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


def downgrade():
    raise NotImplementedError("o esquema inicial não tem volta")
