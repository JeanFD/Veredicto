import secrets
import sqlite3
import uuid
import asyncio
import time
from fastapi import Depends, FastAPI, HTTPException
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from datetime import datetime
from contextlib import asyncccontextmanager

from app.db import db, agora
from app.ws import gerente
from app.seguranca import exigir_admin, hash_token, exigir_urna, senha_correta

@asyncccontextmanager
async def lifespan(app: FastAPI):
    async def vigiar_urnas():
        while True:
            await gerente.broadcast({"tipo": "urnas", "urnas": status_urnas()}, "mesario")
            await asyncio.sleep(5)

    tarefa = asyncio.create_task(vigiar_urnas())
    yield
    tarefa.cancel()

app = FastAPI(title="Veredicto", lifespan=lifespan, version="0.1.0")

TRANSICOES = {
    "AGUARDANDO": "ABERTA",
    "ABERTA": "ENCERRADA",
    "ENCERRADA": "REVELADA",
}

ultimo_sinal: dict[str, dict] = {}

class Heartbeat(BaseModel):
    pendentes: int = Field(ge=0)

class NovaUrna(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,30}$")
    nome: str = Field(min_length=1, max_length=60)
    reserva: bool = False

class Voto(BaseModel):
    id: uuid.UUID
    sessao_id: int
    opcao: str
    votado_em: datetime



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

def total_votos(sid: int) -> int:
    return db.execute("SELECT COUNT(*) FROM votos WHERE sessao_id = ?", (sid,)).fetchone()[0]

async def processar_voto(voto: Voto, urna_id: str):
    if db.execute("SELECT 1 FROM votos WHERE id = ?", (str(voto.id),)).fetchone():
        return

    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (voto.sessao_id,)).fetchone()
    if not sessao:
        raise HTTPException(404, "Sessão inexistente")
    if sessao["estado"] != "ABERTA":
        raise HTTPException(409, "Sessão não está aberta")
    if not db.execute("SELECT 1 FROM opcoes WHERE sessao_id = ? AND chave = ?", (voto.sessao_id, voto.opcao)).fetchone():
        raise HTTPException(400, "Opção inválida")

    with db:
        cur = db.execute(
            "INSERT OR IGNORE INTO votos "
            "(id, sessao_id, urna_id, opcao_chave, votado_em, recebido_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(voto.id), voto.sessao_id, urna_id, voto.opcao,
             voto.votado_em.isoformat(), agora()),
        )
    if cur.rowcount:
        await gerente.broadcast(
            {"tipo": "total", "sessao_id": voto.sessao_id, "total": total_votos(voto.sessao_id)},
            "telao", "mesario",
        )

def estado_publico(tipo: str = "estado") -> dict:
    s=buscar_sessao_ativa()
    msg = {"tipo": tipo, "sessao": s, "total": total_votos(s["id"]) if s else 0}
    if s and s["estado"] == "REVELADA":
        msg["resultado"] = contar_por_opcao(s["id"])
    return msg

def contar_por_opcao(sid: int) -> list[dict]:
    linhas = db.execute("""
        SELECT o.chave, o.rotulo, o.cor, COUNT(v.id) AS votos
        FROM opcoes o
        LEFT JOIN votos v ON v.sessao_id = o.sessao_id AND v.opcao_chave = o.chave
        WHERE o.sessao_id = ?
        GROUP BY o.id
        ORDER BY o.ordem
    """, (sid,)).fetchall()
    return [dict(l) for l in linhas]

def status_urnas() -> list[dict]:
    s = buscar_sessao_ativa()
    agora_mono = time.monotonic()
    resultado = []
    for u in db.execute("SELECT id, nome, ativa, reserva FROM urnas ORDER BY id"):
        sinal = ultimo_sinal.get(u["id"])
        votos = 0
        if s:
            votos = db.execute(
                "SELECT COUNT(*) FROM votos WHERE urna_id = ? AND sessao_id = ?",
                (u["id"], s["id"]),
            ).fetchone()[0]
        resultado.append({
            "id": u["id"],
            "nome": u["nome"],
            "ativa": bool(u["ativa"]),
            "reserva": bool(u["reserva"]),
            "nunca_conectou": sinal is None,
            "online": sinal is not None and agora_mono - sinal["em"] < 15,
            "segundos_sem_sinal": int(agora_mono - sinal["em"]) if sinal else None,
            "pendentes": sinal["pendentes"] if sinal else None,
            "votos_sessao": votos,
        })
    return resultado

def problemas_para_revelar() -> list[str]:
    problemas = []
    for u in status_urnas():
        if not u["ativa"] or (u["reserva"] and u["nunca_conectou"]):
            continue
        if u["nunca_conectou"]:
            problemas.append(f'{u["id"]}: nunca conectou')
        elif not u["online"]:
            problemas.append(f'{u["id"]}: offline há {u["segundos_sem_sinal"]}s, pendências desconhecidas')
        elif u["pendentes"]:
            problemas.append(f'{u["id"]}: {u["pendentes"]} votos pendentes')
    return problemas




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
    await gerente.broadcast(estado_publico(), "telao", "mesario")
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

@app.post("/api/votos")
async def registrar_voto(voto: Voto, urna_id: str = Depends(exigir_urna)):
    await processar_voto(voto, urna_id)
    return {"ok": True}

@app.websocket("/ws/telao")
async def ws_telao(ws: WebSocket):
    await ws.accept()
    gerente.adicionar(ws, "telao")
    await ws.send_json(estado_publico("snapshot"))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        gerente.remover(ws)

@app.post("/api/admin/sessoes/{sid}/avancar", dependencies=[Depends(exigir_admin)])
async def avancar_sessao(sid: int, forcar: bool = False):
    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, "Sessão inexistente")
    if not sessao["ativa"]:
        raise HTTPException(409, "Ative a sessão antes")
    novo = TRANSICOES.get(sessao["estado"])
    if not novo:
        raise HTTPException(409, "Sessão já revelada")

    if novo == "REVELADA" and not forcar:
        problemas = problemas_para_revelar()
        if problemas:
            raise HTTPException(409, {"mensagem": "Há pendências", "problemas": problemas})

@app.websocket("/ws/mesario")
async def ws_mesario(ws: WebSocket):
    await ws.accept()
    try:
        auth = await asyncio.wait_for(ws.receive_json(), timeout = 5)
    except Exception:
        await ws.close(code=4401)
        return
    if not senha_correta(str(auth.get("senha",""))):
        await ws.close(code=4401)
        return

    gerente.adicionar(ws, "mesario")
    await ws.send_json(estado_publico("snapshot"))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        gerente.remover(ws)

@app.post("/api/urnas/heartbeat")
async def heartbeat(hb: Heartbeat, urna_id: str = Depends(exigir_urna)):
    ultimo_sinal[urna_id] = {"em": time.monotonic(), "pendentes": hb.pendentes}
    return {"sessao": buscar_sessao_ativa}

@app.get("/api/admin/urnas", dependencies=[Depends(exigir_admin)])
async def listar_urnas():
    return status_urnas()


app.mount("/", StaticFiles(directory="static", html=True), name="static")