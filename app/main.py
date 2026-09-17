import secrets
import sqlite3

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.db import db, agora
from app.seguranca import exigir_admin, hash_token

app = FastAPI(title="Veredicto", version="0.1.0")

class NovaUrna(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,30}$")
    nome: str = Field(min_length=1, max_length=60)
    reserva: bool = False

def buscar_sessao_ativa():
    s = db.execute("SELECT * FROM sessoes WHERE ativa = 1").fetchone()
    if not s:
        return None
    opcoes = db.execute(
        "SELECT chave, rotulo, cor FROM opcoes WHERE sessao_id = ? ORDER BY ordem", (s["id"],),
    ).fetchall()
    return {
        "id": s["id"],
        "tema": s["tema"],
        "estado": s["estado"],
        "opcoes": [dict(o) for o in opcoes]
    }

@app.get("/api/sessao/ativa")
async def sessao_ativa():
    return{"sessao": buscar_sessao_ativa()}

@app.get("/api/admin/sessoes", dependencies=[Depends(exigir_admin)])
async def listar_sessoes():
    linhas = db.execute("SELECT id, tema, estado, ativa FROM sessoes ORDER BY id")
    return [dict(l) for l in linhas]

@app.post("/api/admin/sessoes/{sid}/ativar", dependencies=[Depends(exigir_admin)])
async def ativar_sessao(sid: int):
    if not db.execute("SELECT 1 FROM sessoes WHERE id = ?", (sid,)).fetchone():
        raise HTTPException(status_code=404, detail="Sessão inexistente")
    with db:
        db.execute("UPDATE sessoes SET ativa = 0")
        db.execute("UPDATE sessoes SET ativa = 1 WHERE id = ?", (sid,))
    return {"sessao": buscar_sessao_ativa()}

@app.post("/api/admin/urnas", dependencies=[Depends(exigir_admin)])
async def cadastrar_urna(u: NovaUrna):
    token = secrets.token_urlsafe(32)
    try:
        with db:
            db.execute(
                "INSERT INTO urnas (id, nome, token_hash, reserva, criada_em) VALUES (?, ?, ?, ?, ?)",
                (u.id, u.nome, hash_token(token), int(u.reserva), agora()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="ID de urna já existe")
    return {"id": u.id, "token": token}

@app.post("/api/admin/urnas/{uid}/desativar", dependencies=[Depends(exigir_admin)])
async def desativar_urna(uid: str):
    with db:
        cur = db.execute("UPDATE urnas SET ativa = 0 WHERE id = ?", (uid,))
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Urna inexistente")
    return {"ok": True}

app.mount("/", StaticFiles(directory="static", html=True), name="static")