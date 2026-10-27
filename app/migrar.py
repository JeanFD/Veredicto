"""Migrações do banco com Alembic.

A app aplica as migrações ao subir (no-op quando o banco já está em dia). Em
produção, o deploy roda `python -m app.migrar` antes de trocar o container: faz
backup e migra; se falhar, o deploy para e a versão antiga continua no ar.

Nova migração: alembic revision -m "descricao" (e escrever o upgrade à mão).
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

PASTA = Path(__file__).parent / "migracoes"

def configuracao() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(PASTA))
    return cfg

def motor(conexao: sqlite3.Connection):
    # usa a conexão já aberta pela app: com DB_PATH=":memory:" (testes) outra
    # conexão abriria um banco vazio diferente
    return create_engine("sqlite://", creator=lambda: conexao, poolclass=StaticPool)

def pendente(conexao: sqlite3.Connection) -> bool:
    with motor(conexao).connect() as c:
        atual = MigrationContext.configure(c).get_current_revision()
    return atual != ScriptDirectory.from_config(configuracao()).get_current_head()

def migrar(conexao: sqlite3.Connection):
    with motor(conexao).begin() as c:
        cfg = configuracao()
        cfg.attributes["connection"] = c
        command.upgrade(cfg, "head")

def backup(conexao: sqlite3.Connection, caminho_banco: str) -> Path:
    pasta = Path(caminho_banco).parent / "backups"
    pasta.mkdir(exist_ok=True)
    destino = pasta / f"pre-migracao-{datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(destino) as copia:
        conexao.backup(copia)  # cópia consistente mesmo com a app antiga gravando
    return destino

def principal():
    from app.config import DB_PATH
    conexao = sqlite3.connect(DB_PATH)
    if not pendente(conexao):
        print("banco já está na última migração")
        return
    print(f"backup em {backup(conexao, DB_PATH)}")
    migrar(conexao)
    print("migrações aplicadas")

if __name__ == "__main__":
    sys.exit(principal())
