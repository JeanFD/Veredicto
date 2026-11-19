import json
import sqlite3
from contextvars import ContextVar
from datetime import datetime, timezone

from app.config import CARTOES_PATH, DB_PATH, SESSOES_PATH
from app.migrar import migrar
from app.observabilidade import campos_do_detalhe, log

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
if DB_PATH != ":memory:":
    db.execute("PRAGMA journal_mode=WAL")

# o esquema vem das migrações em app/migracoes; ver app/migrar.py
migrar(db)

# conta que fez o pedido em andamento (posta pela checagem de acesso; vazia em rotas
# públicas): todo evento registrado por ela leva "por=usuario" na auditoria interna
responsavel: ContextVar[str | None] = ContextVar("responsavel", default=None)

def agora() -> str:
    return datetime.now(timezone.utc).isoformat()

def ler_presets() -> list[dict]:
    # utf-8-sig: aceita o arquivo salvo com BOM pelo Bloco de Notas
    with open(SESSOES_PATH, encoding="utf-8-sig") as f:
        return json.load(f)

def inserir_sessao(tema: str, opcoes: list[dict], grupo_id: int | None = None, pergunta: int = 1,
                   teste: bool = False, celular: bool = False, peso_celular: int = 1, caso: str = "") -> int:
    cur = db.execute(
        "INSERT INTO sessoes (tema, grupo_id, pergunta, teste, celular, peso_celular, caso) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tema, grupo_id, pergunta, int(teste), int(celular), peso_celular, caso),
    )
    inserir_opcoes(cur.lastrowid, opcoes)
    return cur.lastrowid

def inserir_opcoes(sessao_id: int, opcoes: list[dict]):
    for ordem, op in enumerate(opcoes):
        db.execute(
            "INSERT INTO opcoes (sessao_id, chave, rotulo, cor, ordem) "
            "VALUES (?, ?, ?, ?, ?)",
            (sessao_id, op["chave"], op["rotulo"], op["cor"], ordem),
        )

def ler_cartoes() -> list[dict]:
    """Cartões prontos do júri; sem o arquivo, o painel começa sem nenhum."""
    try:
        with open(CARTOES_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def carregar_cartoes():
    if db.execute("SELECT 1 FROM cartoes").fetchone():
        return
    with db:
        for c in ler_cartoes():
            db.execute(
                "INSERT INTO cartoes (pasta, titulo, texto, fonte, criado_em) VALUES (?, ?, ?, ?, ?)",
                (c["pasta"], c["titulo"], c["texto"], c.get("fonte", ""), agora()),
            )

def carregar_sessoes():
    if db.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0] != 0:
        return
    with db:
        for s in ler_presets():
            inserir_sessao(s["tema"], s["opcoes"], caso=s.get("caso", ""))

def registrar_evento(tipo: str, detalhe: str = ""):
    if responsavel.get():
        detalhe = f"{detalhe} por={responsavel.get()}".strip()
    with db:
        db.execute("INSERT INTO eventos (tipo, detalhe, em) VALUES (?, ?, ?)",
                   (tipo, detalhe, agora()))
    log(tipo, **campos_do_detalhe(detalhe))

carregar_sessoes()
carregar_cartoes()