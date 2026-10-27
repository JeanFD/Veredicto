import json
import sqlite3
from datetime import datetime, timezone

from app.config import DB_PATH, SESSOES_PATH
from app.migrar import migrar

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
if DB_PATH != ":memory:":
    db.execute("PRAGMA journal_mode=WAL")

# o esquema vem das migrações em app/migracoes; ver app/migrar.py
migrar(db)

def agora() -> str:
    return datetime.now(timezone.utc).isoformat()

def ler_presets() -> list[dict]:
    # utf-8-sig: aceita o arquivo salvo com BOM pelo Bloco de Notas
    with open(SESSOES_PATH, encoding="utf-8-sig") as f:
        return json.load(f)

def inserir_sessao(tema: str, opcoes: list[dict], grupo_id: int | None = None, pergunta: int = 1) -> int:
    cur = db.execute(
        "INSERT INTO sessoes (tema, grupo_id, pergunta) VALUES (?, ?, ?)", (tema, grupo_id, pergunta),
    )
    for ordem, op in enumerate(opcoes):
        db.execute(
            "INSERT INTO opcoes (sessao_id, chave, rotulo, cor, ordem) "
            "VALUES (?, ?, ?, ?, ?)",
            (cur.lastrowid, op["chave"], op["rotulo"], op["cor"], ordem),
        )
    return cur.lastrowid

def carregar_sessoes():
    if db.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0] != 0:
        return
    with db:
        for s in ler_presets():
            inserir_sessao(s["tema"], s["opcoes"])

def registrar_evento(tipo: str, detalhe: str = ""):
    with db:
        db.execute("INSERT INTO eventos (tipo, detalhe, em) VALUES (?, ?, ?)",
                   (tipo, detalhe, agora()))

carregar_sessoes()