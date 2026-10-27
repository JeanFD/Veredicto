import secrets
import sqlite3
import uuid
import asyncio
import time
import csv
import io
import re
import unicodedata

from fastapi import Depends, FastAPI, HTTPException
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from app.db import db, agora, registrar_evento, inserir_sessao, ler_presets
from app.ws import gerente
from app.config import EM_PRODUCAO
from app.seguranca import exigir_admin, hash_token, exigir_urna, senha_correta, bloqueado, registrar_falha
from app.seguranca import (
    JANELA_CODIGO, chave_telao, codigo_celular, codigo_valido, exigir_telao, janela_atual,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async def vigiar_urnas():
        while True:
            await gerente.broadcast({"tipo": "urnas", "urnas": status_urnas()}, "mesario")
            await asyncio.sleep(5)

    tarefa = asyncio.create_task(vigiar_urnas())
    yield
    tarefa.cancel()

app = FastAPI(
    title="Veredicto",
    lifespan=lifespan,
    version="0.1.0",
    docs_url=None if EM_PRODUCAO else "/docs",
    redoc_url=None,
    openapi_url=None if EM_PRODUCAO else "/openapi.json",
)

TRANSICOES = {
    "AGUARDANDO": "ABERTA",
    "ABERTA": "ENCERRADA",
    "ENCERRADA": "REVELADA",
}

TOLERANCIA_ATRASO = timedelta(minutes=10)

# votos por celular são gravados com este urna_id, que não pode ser cadastrado como urna
URNA_CELULAR = "celular"

ultimo_sinal: dict[str, dict] = {}

class Heartbeat(BaseModel):
    pendentes: int = Field(ge=0)
    recusados: int = Field(default=0, ge=0)

class NovaUrna(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,30}$")
    nome: str = Field(min_length=1, max_length=60)
    reserva: bool = False

class Voto(BaseModel):
    id: uuid.UUID
    sessao_id: int
    opcao: str
    votado_em: datetime

class Importacao(BaseModel):
    urna_id: str
    votos: list[Voto] = Field(max_length=10000)

class Zerar(BaseModel):
    confirmacao: str

class EntradaCelular(BaseModel):
    sessao_id: int
    codigo: str = Field(max_length=20)

class VotoCelular(BaseModel):
    cedula: str = Field(max_length=100)
    id: uuid.UUID
    opcao: str

class NovaOpcao(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    chave: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,30}$")
    rotulo: str = Field(min_length=1, max_length=40)
    cor: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")

class NovaSessao(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    tema: str = Field(min_length=1, max_length=200)
    opcoes: list[NovaOpcao] = Field(min_length=2, max_length=10)

class NovoQuestionario(BaseModel):
    perguntas: list[NovaSessao] = Field(min_length=2, max_length=10)

class ProximaCedula(BaseModel):
    cedula: str = Field(max_length=100)



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
        "opcoes": [dict(o) for o in opcoes],
        **posicao_no_questionario(s),
    }

def posicao_no_questionario(s) -> dict:
    """Pergunta k de N; para sessão avulsa, 1 de 1 e sem próxima."""
    if s["grupo_id"] is None:
        return {"grupo_id": None, "pergunta": 1, "total_perguntas": 1, "proxima_pergunta": None}
    irmas = db.execute(
        "SELECT id, pergunta FROM sessoes WHERE grupo_id = ? ORDER BY pergunta", (s["grupo_id"],),
    ).fetchall()
    proxima = next((i["id"] for i in irmas if i["pergunta"] == s["pergunta"] + 1), None)
    return {"grupo_id": s["grupo_id"], "pergunta": s["pergunta"],
            "total_perguntas": len(irmas), "proxima_pergunta": proxima}

def pergunta_anterior(s):
    if s["grupo_id"] is None or s["pergunta"] == 1:
        return None
    return db.execute(
        "SELECT id, estado FROM sessoes WHERE grupo_id = ? AND pergunta = ?", (s["grupo_id"], s["pergunta"] - 1),
    ).fetchone()

def total_votos(sid: int) -> int:
    return db.execute("SELECT COUNT(*) FROM votos WHERE sessao_id = ?", (sid,)).fetchone()[0]

def recusa(status: int, motivo: str, mensagem: str) -> HTTPException:
    return HTTPException(status, {"motivo": motivo, "mensagem": mensagem})

async def processar_voto(voto: Voto, urna_id: str, sem_prazo: bool = False) -> bool:
    """Grava o voto; devolve False quando ele já existia (reenvio)."""
    if db.execute("SELECT 1 FROM votos WHERE id = ?", (str(voto.id),)).fetchone():
        return False

    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (voto.sessao_id,)).fetchone()
    if not sessao:
        raise recusa(404, "sessao_inexistente", "Sessão inexistente")
    if not aceita_voto(sessao, voto.votado_em, sem_prazo):
        if sessao["estado"] in ("ENCERRADA", "REVELADA"):
            raise recusa(409, "sessao_encerrada", "Sessão encerrada")
        raise recusa(409, "sessao_nao_aberta", "Sessão ainda não foi aberta")
    if not db.execute("SELECT 1 FROM opcoes WHERE sessao_id = ? AND chave = ?", (voto.sessao_id, voto.opcao)).fetchone():
        raise recusa(400, "opcao_invalida", "Opção inválida")

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
    return bool(cur.rowcount)

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
            "recusados": sinal["recusados"] if sinal else 0,
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

def aceita_voto(sessao, votado_em: datetime, sem_prazo: bool = False) -> bool:
    if sessao["estado"] == "ABERTA":
        return True
    if sessao["estado"] == "ENCERRADA" and sessao["encerrada_em"]:
        encerrada = datetime.fromisoformat(sessao["encerrada_em"])
        # sem_prazo: importação pelo mesário de urna que ficou isolada além da tolerância
        dentro_do_prazo = sem_prazo or datetime.fromisoformat(agora()) - encerrada <= TOLERANCIA_ATRASO
        return votado_em <= encerrada and dentro_do_prazo
    return False




@app.get("/api/sessao/ativa")
async def sessao_ativa():
    return{"sessao": buscar_sessao_ativa()}

@app.get("/api/admin/sessoes", dependencies=[Depends(exigir_admin)])
async def listar_sessoes(arquivadas: bool = False):
    linhas = db.execute(
        "SELECT * FROM sessoes WHERE arquivada = 0 OR ? ORDER BY id", (arquivadas,),
    ).fetchall()
    resposta = []
    for l in linhas:
        anterior = pergunta_anterior(l)
        resposta.append({
            "id": l["id"], "tema": l["tema"], "estado": l["estado"], "ativa": l["ativa"],
            "arquivada": bool(l["arquivada"]),
            **posicao_no_questionario(l),
            # pergunta encadeada só pode ser ativada depois de revelada a anterior
            "liberada": anterior is None or anterior["estado"] == "REVELADA",
        })
    return resposta

@app.post("/api/admin/sessoes/{sid}/arquivar", dependencies=[Depends(exigir_admin)])
async def arquivar_sessao(sid: int):
    sessao = db.execute("SELECT ativa FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, "Sessão inexistente")
    if sessao["ativa"]:
        raise HTTPException(409, "Ative outra sessão antes de arquivar esta")
    with db:
        db.execute("UPDATE sessoes SET arquivada = 1 WHERE id = ?", (sid,))
    registrar_evento("sessao_arquivada", f"sessao={sid}")
    return {"ok": True}

@app.post("/api/admin/sessoes/{sid}/zerar")
async def zerar_sessao(sid: int, dados: Zerar, responsavel: str = Depends(exigir_admin)):
    sessao = db.execute("SELECT tema, estado FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, "Sessão inexistente")
    if sessao["estado"] == "REVELADA":
        raise HTTPException(409, "Sessão já revelada: o resultado não pode ser apagado")
    if dados.confirmacao.strip().casefold() != sessao["tema"].casefold():
        raise HTTPException(400, "Confirmação não confere com o tema da sessão")
    with db:
        apagados = db.execute("DELETE FROM votos WHERE sessao_id = ?", (sid,)).rowcount
        db.execute("DELETE FROM cedulas WHERE sessao_id = ?", (sid,))
        db.execute("UPDATE sessoes SET estado = 'AGUARDANDO', encerrada_em = NULL WHERE id = ?", (sid,))
    registrar_evento("sessao_zerada", f"sessao={sid} votos={apagados} por={responsavel}")
    await gerente.broadcast(estado_publico(), "telao", "mesario")
    return {"apagados": apagados}

@app.post("/api/admin/sessoes/{sid}/desarquivar", dependencies=[Depends(exigir_admin)])
async def desarquivar_sessao(sid: int):
    with db:
        cur = db.execute("UPDATE sessoes SET arquivada = 0 WHERE id = ?", (sid,))
    if not cur.rowcount:
        raise HTTPException(404, "Sessão inexistente")
    registrar_evento("sessao_desarquivada", f"sessao={sid}")
    return {"ok": True}

def gerar_chave(rotulo: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", rotulo).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")[:30] or "opcao"

@app.post("/api/admin/sessoes", status_code=201, dependencies=[Depends(exigir_admin)])
async def criar_sessao(nova: NovaSessao):
    opcoes = validar_opcoes(nova)
    validar_temas_livres([nova.tema])
    with db:
        sid = inserir_sessao(nova.tema, opcoes)
    registrar_evento("sessao_criada", f"sessao={sid}")
    return {"id": sid}

def validar_opcoes(nova: NovaSessao) -> list[dict]:
    opcoes = [
        {"chave": op.chave or gerar_chave(op.rotulo), "rotulo": op.rotulo, "cor": op.cor}
        for op in nova.opcoes
    ]
    if len({op["chave"] for op in opcoes}) != len(opcoes):
        raise HTTPException(400, "Opções repetidas")
    return opcoes

def validar_temas_livres(temas: list[str]):
    if len({t.casefold() for t in temas}) != len(temas):
        raise HTTPException(400, "Perguntas repetidas")
    existentes = {s["tema"].casefold() for s in db.execute("SELECT tema FROM sessoes")}
    if any(t.casefold() in existentes for t in temas):
        raise HTTPException(409, "Já existe uma sessão com este tema")

@app.post("/api/admin/questionarios", status_code=201, dependencies=[Depends(exigir_admin)])
async def criar_questionario(novo: NovoQuestionario):
    opcoes = [validar_opcoes(p) for p in novo.perguntas]
    validar_temas_livres([p.tema for p in novo.perguntas])
    with db:
        ids = [inserir_sessao(novo.perguntas[0].tema, opcoes[0])]
        db.execute("UPDATE sessoes SET grupo_id = ? WHERE id = ?", (ids[0], ids[0]))
        for n, (p, ops) in enumerate(zip(novo.perguntas[1:], opcoes[1:]), start=2):
            ids.append(inserir_sessao(p.tema, ops, grupo_id=ids[0], pergunta=n))
    for sid in ids:
        registrar_evento("sessao_criada", f"sessao={sid} grupo={ids[0]}")
    return {"ids": ids}

@app.get("/api/admin/presets", dependencies=[Depends(exigir_admin)])
async def listar_presets():
    return ler_presets()

@app.post("/api/admin/sessoes/{sid}/ativar", dependencies=[Depends(exigir_admin)])
async def ativar_sessao(sid: int):
    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão inexistente")
    if sessao["arquivada"]:
        raise HTTPException(409, "Desarquive a sessão antes de ativá-la")
    anterior = pergunta_anterior(sessao)
    if anterior and anterior["estado"] != "REVELADA":
        raise HTTPException(409, "Revele a pergunta anterior antes de liberar esta")
    with db:
        db.execute("UPDATE sessoes SET ativa = 0")
        db.execute("UPDATE sessoes SET ativa = 1 WHERE id = ?", (sid,))
    await gerente.broadcast(estado_publico(), "telao", "mesario")
    registrar_evento("sessao_ativada", f"sessao={sid}")
    return {"sessao": buscar_sessao_ativa()}

@app.post("/api/admin/urnas", dependencies=[Depends(exigir_admin)])
async def cadastrar_urna(u: NovaUrna):
    if u.id.lower() == URNA_CELULAR:
        raise HTTPException(409, "ID reservado para os votos por celular")
    token = secrets.token_urlsafe(32)
    try:
        with db:
            db.execute(
                "INSERT INTO urnas (id, nome, token_hash, reserva, criada_em) VALUES (?, ?, ?, ?, ?)",
                (u.id, u.nome, hash_token(token), int(u.reserva), agora()),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="ID de urna já existe")
    registrar_evento("urna_cadastrada", u.id)
    return {"id": u.id, "token": token}

@app.post("/api/admin/urnas/{uid}/novo-token", dependencies=[Depends(exigir_admin)])
async def reemitir_token(uid: str):
    # só o hash fica no banco: para mostrar o link de novo é preciso trocar o token
    urna = db.execute("SELECT ativa FROM urnas WHERE id = ?", (uid,)).fetchone()
    if not urna:
        raise HTTPException(404, "Urna inexistente")
    if not urna["ativa"]:
        raise HTTPException(409, "Urna desativada")
    token = secrets.token_urlsafe(32)
    with db:
        db.execute("UPDATE urnas SET token_hash = ? WHERE id = ?", (hash_token(token), uid))
    registrar_evento("urna_token_reemitido", uid)
    return {"id": uid, "token": token}

@app.post("/api/admin/urnas/{uid}/desativar", dependencies=[Depends(exigir_admin)])
async def desativar_urna(uid: str):
    with db:
        cur = db.execute("UPDATE urnas SET ativa = 0 WHERE id = ?", (uid,))
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Urna inexistente")
    registrar_evento("urna_desativada", uid)
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

    if novo == "REVELADA":
        problemas = problemas_para_revelar()
        if problemas and not forcar:
            raise HTTPException(409, {"mensagem": "Há pendências", "problemas": problemas})
        if problemas:
            registrar_evento("revelacao_forcada", f"sessao={sid} " + "; ".join(problemas))
        
    with db:
        if novo == "ENCERRADA":
            db.execute("UPDATE sessoes SET estado = ?, encerrada_em = ? WHERE id = ?",
                       (novo, agora(), sid))
        else:
            db.execute("UPDATE sessoes SET estado = ? WHERE id = ?", (novo, sid))

    await gerente.broadcast(estado_publico(), "telao", "mesario")
    registrar_evento("sessao_avancada", f"sessao={sid} estado={novo}")
    return {"estado": novo}

@app.websocket("/ws/mesario")
async def ws_mesario(ws: WebSocket):
    ip = ws.client.host
    await ws.accept()
    if bloqueado(ip):
        await ws.close(code=4429)
        return
    try:
        auth = await asyncio.wait_for(ws.receive_json(), timeout=5)
    except Exception:
        await ws.close(code=4401)
        return
    if not senha_correta(str(auth.get("senha", ""))):
        registrar_falha(ip)
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
    ultimo_sinal[urna_id] = {"em": time.monotonic(), "pendentes": hb.pendentes, "recusados": hb.recusados}
    return {"sessao": buscar_sessao_ativa()}

@app.get("/api/admin/urnas", dependencies=[Depends(exigir_admin)])
async def listar_urnas():
    return status_urnas()

@app.get("/api/admin/eventos", dependencies=[Depends(exigir_admin)])
async def listar_eventos():
    return [dict(e) for e in db.execute("SELECT * FROM eventos ORDER BY id")]

@app.get("/api/admin/sessoes/{sid}/votos.csv", dependencies=[Depends(exigir_admin)])
async def exportar_votos(sid: int):
    sessao = db.execute("SELECT estado FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, "Sessão inexistente")
    if sessao["estado"] != "REVELADA":
        raise HTTPException(409, "Exportação liberada só após revelar")

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["id", "urna_id", "opcao", "votado_em", "recebido_em"])
    for v in db.execute(
        "SELECT id, urna_id, opcao_chave, votado_em, recebido_em"
        "FROM votos WHERE sessao_id = ? ORDER BY recebido_em", (sid,)
    ):
        escritor.writerow(list(v))

    registrar_evento("votos_exportados", f"sessao={sid}")
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="sessao-{sid}-votos.csv"'},
    )

@app.post("/api/admin/importar", dependencies=[Depends(exigir_admin)])
async def importar_votos(dados: Importacao):
    if not db.execute("SELECT 1 FROM urnas WHERE id = ?", (dados.urna_id,)).fetchone():
        raise HTTPException(404, "Urna inexistente")
    aceitos, existentes, recusados = 0, 0, []
    for voto in dados.votos:
        try:
            if await processar_voto(voto, dados.urna_id, sem_prazo=True):
                aceitos += 1
            else:
                existentes += 1
        except HTTPException as e:
            recusados.append({"id": str(voto.id), "motivo": e.detail["motivo"]})
    registrar_evento(
        "importacao",
        f"urna={dados.urna_id} aceitos={aceitos} existentes={existentes} recusados={len(recusados)}",
    )
    return {"aceitos": aceitos, "existentes": existentes, "recusados": recusados}

# ---------- Auditoria pública ----------
# Invariante: nada de uma sessão sai daqui antes de ela estar REVELADA.
# Por urna vai só a quantidade de votos, nunca a divisão por opção: numa urna
# com poucos votos, ela revelaria em quem cada pessoa votou.

def descrever_evento(tipo: str, campos: dict) -> str | None:
    """Texto público de um evento da sessão; None para eventos que não são publicados."""
    if tipo == "sessao_ativada":
        return "Sessão ativada"
    if tipo == "sessao_avancada":
        return f"Estado alterado para {campos.get('estado')}"
    if tipo == "sessao_zerada":
        # 'por' traz o IP de quem zerou: fica só na auditoria interna
        return f"Contagem zerada ({campos.get('votos')} votos apagados)"
    if tipo == "revelacao_forcada":
        return "Revelação forçada com pendências nas urnas"
    if tipo == "votos_exportados":
        return "Votos exportados pelo mesário"
    return None

def eventos_publicos(sid: int) -> list[dict]:
    publicos = []
    for e in db.execute("SELECT tipo, detalhe, em FROM eventos ORDER BY id"):
        campos = dict(p.split("=", 1) for p in e["detalhe"].split() if "=" in p)
        if campos.get("sessao") != str(sid):
            continue
        texto = descrever_evento(e["tipo"], campos)
        if texto:
            publicos.append({"em": e["em"], "evento": texto})
    return publicos

@app.get("/api/auditoria/sessoes")
async def auditoria_sessoes():
    linhas = db.execute("SELECT * FROM sessoes WHERE estado = 'REVELADA' ORDER BY id")
    return [{"id": l["id"], "tema": l["tema"], **pergunta_publica(l)} for l in linhas]

def pergunta_publica(s) -> dict:
    # só a posição: o id da próxima pergunta não interessa ao público
    p = posicao_no_questionario(s)
    return {"pergunta": p["pergunta"], "total_perguntas": p["total_perguntas"]}

@app.get("/api/auditoria/sessoes/{sid}")
async def auditoria_sessao(sid: int):
    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (sid,)).fetchone()
    # mesma resposta para inexistente e não revelada: não confirma nada antes da hora
    if not sessao or sessao["estado"] != "REVELADA":
        raise HTTPException(404, "Auditoria disponível só após a revelação")
    nomes = {u["id"]: u["nome"] for u in db.execute("SELECT id, nome FROM urnas")}
    nomes[URNA_CELULAR] = "Voto por celular"
    por_urna = [
        {"urna": nomes.get(u["urna_id"], u["urna_id"]), "votos": u["votos"],
         "primeiro_voto": u["primeiro"], "ultimo_voto": u["ultimo"]}
        for u in db.execute(
            "SELECT urna_id, COUNT(*) AS votos, MIN(recebido_em) AS primeiro, MAX(recebido_em) AS ultimo "
            "FROM votos WHERE sessao_id = ? GROUP BY urna_id ORDER BY urna_id", (sid,),
        )
    ]
    return {
        "id": sessao["id"],
        "tema": sessao["tema"],
        **pergunta_publica(sessao),
        "total": total_votos(sid),
        "resultado": contar_por_opcao(sid),
        "por_urna": por_urna,
        "eventos": eventos_publicos(sid),
    }

# ---------- Voto por celular ----------
def sessao_aberta(sid: int):
    sessao = db.execute("SELECT estado, ativa FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise recusa(404, "sessao_inexistente", "Sessão inexistente")
    if not sessao["ativa"] or sessao["estado"] != "ABERTA":
        raise recusa(409, "sessao_fechada", "A votação não está aberta")

@app.get("/api/admin/telao", dependencies=[Depends(exigir_admin)])
async def link_telao():
    return {"chave": chave_telao()}

@app.get("/api/telao/codigo", dependencies=[Depends(exigir_telao)])
async def codigo_telao():
    s = buscar_sessao_ativa()
    if not s or s["estado"] != "ABERTA":
        return {"sessao_id": None, "codigo": None}
    janela = janela_atual()
    return {
        "sessao_id": s["id"],
        "codigo": codigo_celular(s["id"], janela),
        "expira_em": (janela + 1) * JANELA_CODIGO,
    }

@app.post("/api/celular/entrar")
async def entrar_celular(e: EntradaCelular):
    sessao_aberta(e.sessao_id)
    if not codigo_valido(e.sessao_id, e.codigo):
        raise recusa(403, "codigo_expirado", "QR code expirado: escaneie de novo o código do telão")
    cedula = secrets.token_urlsafe(32)
    with db:
        db.execute(
            "INSERT INTO cedulas (token_hash, sessao_id, criada_em) VALUES (?, ?, ?)",
            (hash_token(cedula), e.sessao_id, agora()),
        )
    return {"cedula": cedula, "sessao": buscar_sessao_ativa()}

@app.post("/api/celular/proxima")
async def proxima_cedula(p: ProximaCedula):
    """Troca a cédula de uma pergunta pela da pergunta seguinte do mesmo questionário.

    Cada cédula gera no máximo uma seguinte: o celular passa pelas perguntas sem
    escanear o QR de novo e continua valendo um voto por pergunta."""
    cedula = db.execute(
        "SELECT c.token_hash, s.grupo_id, s.pergunta FROM cedulas c JOIN sessoes s ON s.id = c.sessao_id "
        "WHERE c.token_hash = ?", (hash_token(p.cedula),),
    ).fetchone()
    if not cedula:
        raise recusa(401, "cedula_invalida", "Cédula inválida: escaneie o QR code do telão")
    ativa = buscar_sessao_ativa()
    if (not ativa or ativa["grupo_id"] is None or ativa["grupo_id"] != cedula["grupo_id"]
            or ativa["pergunta"] <= cedula["pergunta"]):
        raise recusa(409, "sem_proxima", "Não há outra pergunta deste questionário liberada")
    sessao_aberta(ativa["id"])
    nova = secrets.token_urlsafe(32)
    with db:
        # o WHERE garante uma única cédula seguinte mesmo com dois pedidos simultâneos
        if not db.execute(
            "UPDATE cedulas SET seguinte_emitida = 1 WHERE token_hash = ? AND seguinte_emitida = 0",
            (cedula["token_hash"],),
        ).rowcount:
            raise recusa(409, "cedula_usada", "Escaneie o QR code do telão para a próxima pergunta")
        db.execute(
            "INSERT INTO cedulas (token_hash, sessao_id, criada_em) VALUES (?, ?, ?)",
            (hash_token(nova), ativa["id"], agora()),
        )
    return {"cedula": nova, "sessao": ativa}

@app.post("/api/celular/votar")
async def votar_celular(v: VotoCelular):
    cedula = db.execute("SELECT * FROM cedulas WHERE token_hash = ?", (hash_token(v.cedula),)).fetchone()
    if not cedula:
        raise recusa(401, "cedula_invalida", "Cédula inválida: escaneie o QR code do telão")
    if cedula["voto_id"]:
        # reenvio do mesmo voto (rede instável) é aceito; um segundo voto, não
        if cedula["voto_id"] == str(v.id):
            return {"ok": True}
        raise recusa(409, "ja_votou", "Este celular já votou nesta sessão")
    sessao_aberta(cedula["sessao_id"])
    if not db.execute("SELECT 1 FROM opcoes WHERE sessao_id = ? AND chave = ?",
                      (cedula["sessao_id"], v.opcao)).fetchone():
        raise recusa(400, "opcao_invalida", "Opção inválida")

    try:
        with db:
            # o WHERE voto_id IS NULL garante uso único mesmo com dois envios simultâneos
            marcada = db.execute(
                "UPDATE cedulas SET voto_id = ? WHERE token_hash = ? AND voto_id IS NULL",
                (str(v.id), cedula["token_hash"]),
            ).rowcount
            if not marcada:
                raise recusa(409, "ja_votou", "Este celular já votou nesta sessão")
            db.execute(
                "INSERT INTO votos (id, sessao_id, urna_id, opcao_chave, votado_em, recebido_em) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(v.id), cedula["sessao_id"], URNA_CELULAR, v.opcao, agora(), agora()),
            )
    except sqlite3.IntegrityError:
        # id de voto que já existe: a transação desfaz a marcação da cédula
        raise recusa(409, "voto_repetido", "Voto repetido")
    await gerente.broadcast(
        {"tipo": "total", "sessao_id": cedula["sessao_id"], "total": total_votos(cedula["sessao_id"])},
        "telao", "mesario",
    )
    return {"ok": True}



app.mount("/", StaticFiles(directory="static", html=True), name="static")