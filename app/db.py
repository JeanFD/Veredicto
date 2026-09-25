import json
import sqlite3
from datetime import datetime, timezone

from app.config import DB_PATH, SESSOES_PATH

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
if DB_PATH != ":memory:":
    db.execute("PRAGMA journal_mode=WAL")

db.executescript("""
        CREATE TABLE IF NOT EXISTS sessoes (
        id INTEGER PRIMARY KEY,
        tema TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'AGUARDANDO',
        ativa INTEGER NOT NULL DEFAULT 0,
        encerrada_em TEXT
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
""")

def agora() -> str:
    return datetime.now(timezone.utc).isoformat()

def carregar_sessoes():
    if db.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0] != 0:
        return
    with open(SESSOES_PATH, encoding="utf-8") as f:
        sessoes = json.load(f)
    with db:
        for s in sessoes:
            cur = db.execute("INSERT INTO sessoes (tema) VALUES (?)", (s["tema"],))
            for ordem, op in enumerate(s["opcoes"]):
                db.execute(
                    "INSERT INTO opcoes (sessao_id, chave, rotulo, cor, ordem) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cur.lastrowid, op["chave"], op["rotulo"], op["cor"], ordem),
                )

def registrar_evento(tipo: str, detalhe: str = ""):
    with db:
        db.execute("INSERT INTO eventos (tipo, detalhe, em) VALUES (?, ?, ?)",
                   (tipo, detalhe, agora()))

carregar_sessoes()