import secrets
import sqlite3
import uuid
import asyncio
import time
import csv
import io
import re
import unicodedata

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from app.db import db, agora, registrar_evento, inserir_sessao, ler_presets
from app.ws import gerente
from app.config import EM_PRODUCAO
from app.compartilhado import sinais
from app.observabilidade import formato_prometheus, log, metricas
from app.i18n import idioma_atual, idioma_do_cabecalho, msg
from app.seguranca import exigir_admin, hash_token, exigir_urna, senha_correta, bloqueado, registrar_falha
from app.seguranca import (
    JANELA_CODIGO, chave_telao, codigo_celular, codigo_valido, exigir_telao, janela_atual,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async def vigiar_urnas():
        while True:
            # cada processo calcula a grade a partir do estado compartilhado e entrega
            # só aos seus clientes: publicar no Redis repetiria a grade N vezes
            await gerente.entregar({"tipo": "urnas", "urnas": status_urnas()}, ["mesario"])
            await gerente.entregar({"tipo": "pedidos", "pedidos": pedidos_pendentes()}, ["mesario"])
            await asyncio.sleep(5)

    tarefas = [asyncio.create_task(vigiar_urnas())]
    if gerente.redis:
        tarefas.append(asyncio.create_task(gerente.escutar()))
    yield
    for tarefa in tarefas:
        tarefa.cancel()

app = FastAPI(
    title="Veredicto",
    lifespan=lifespan,
    version="0.1.0",
    docs_url=None if EM_PRODUCAO else "/docs",
    redoc_url=None,
    openapi_url=None if EM_PRODUCAO else "/openapi.json",
)

# latência medida só onde o eleitor espera: o envio do voto
ROTAS_DE_VOTO = {"/api/votos", "/api/celular/votar"}

@app.middleware("http")
async def medir_latencia(request: Request, proximo):
    idioma_atual.set(idioma_do_cabecalho(request.headers.get("accept-language")))
    inicio = time.perf_counter()
    resposta = await proximo(request)
    if request.method == "POST" and request.url.path in ROTAS_DE_VOTO:
        metricas.latencia((time.perf_counter() - inicio) * 1000)
    return resposta

TRANSICOES = {
    "AGUARDANDO": "ABERTA",
    "ABERTA": "ENCERRADA",
    "ENCERRADA": "REVELADA",
}

TOLERANCIA_ATRASO = timedelta(minutes=10)

# votos por celular são gravados com este urna_id, que não pode ser cadastrado como urna
URNA_CELULAR = "celular"


class Heartbeat(BaseModel):
    pendentes: int = Field(ge=0)
    recusados: int = Field(default=0, ge=0)

class NovaUrna(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,30}$")
    nome: str = Field(min_length=1, max_length=60)
    reserva: bool = False
    teste: bool = False

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
    teste: bool = False
    celular: bool = False

class NovoQuestionario(BaseModel):
    perguntas: list[NovaSessao] = Field(min_length=2, max_length=10)
    teste: bool = False
    celular: bool = False

class Celular(BaseModel):
    ativo: bool

class PedidoUrna(BaseModel):
    segredo: str = Field(max_length=100)

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
        "teste": bool(s["teste"]),
        "celular": bool(s["celular"]),
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

def recusa(status: int, motivo: str) -> HTTPException:
    return HTTPException(status, {"motivo": motivo, "mensagem": msg(motivo)})

def registrar_recusa(e: HTTPException, sessao: int | None, urna: str):
    motivo = e.detail["motivo"] if isinstance(e.detail, dict) else str(e.status_code)
    metricas.voto_recusado(motivo)
    log("voto_recusado", sessao=sessao, urna=urna, motivo=motivo)

async def processar_voto(voto: Voto, urna_id: str, sem_prazo: bool = False) -> bool:
    """Grava o voto; devolve False quando ele já existia (reenvio)."""
    try:
        return await gravar_voto(voto, urna_id, sem_prazo)
    except HTTPException as e:
        registrar_recusa(e, voto.sessao_id, urna_id)
        raise

async def gravar_voto(voto: Voto, urna_id: str, sem_prazo: bool) -> bool:
    if db.execute("SELECT 1 FROM votos WHERE id = ?", (str(voto.id),)).fetchone():
        log("voto_reenviado", sessao=voto.sessao_id, urna=urna_id, voto=str(voto.id))
        return False

    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (voto.sessao_id,)).fetchone()
    if not sessao:
        raise recusa(404, "sessao_inexistente")
    if not aceita_voto(sessao, voto.votado_em, sem_prazo):
        if sessao["estado"] in ("ENCERRADA", "REVELADA"):
            raise recusa(409, "sessao_encerrada")
        raise recusa(409, "sessao_nao_aberta")
    if not db.execute("SELECT 1 FROM opcoes WHERE sessao_id = ? AND chave = ?", (voto.sessao_id, voto.opcao)).fetchone():
        raise recusa(400, "opcao_invalida")
    if not sessao["teste"] and db.execute("SELECT 1 FROM urnas WHERE id = ? AND teste = 1", (urna_id,)).fetchone():
        raise recusa(409, "urna_de_teste")

    with db:
        cur = db.execute(
            "INSERT OR IGNORE INTO votos "
            "(id, sessao_id, urna_id, opcao_chave, votado_em, recebido_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(voto.id), voto.sessao_id, urna_id, voto.opcao,
             voto.votado_em.isoformat(), agora()),
        )
    if cur.rowcount:
        # a opção votada fica de fora do log de propósito: sigilo do voto
        metricas.voto_aceito("importacao" if sem_prazo else "urna")
        log("voto_recebido", sessao=voto.sessao_id, urna=urna_id, voto=str(voto.id))
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
    resultado = []
    for u in db.execute("SELECT id, nome, ativa, reserva, teste FROM urnas ORDER BY id"):
        sinal = sinais.obter(u["id"])
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
            "teste": bool(u["teste"]),
            "nunca_conectou": sinal is None,
            "online": sinal is not None and sinal["segundos"] < 15,
            "segundos_sem_sinal": int(sinal["segundos"]) if sinal else None,
            "pendentes": sinal["pendentes"] if sinal else None,
            "recusados": sinal["recusados"] if sinal else 0,
            "votos_sessao": votos,
        })
    return resultado

def problemas_para_revelar() -> list[tuple[str, dict]]:
    """Pendências como (chave, campos): a tela recebe no idioma dela, a auditoria em português."""
    problemas = []
    for u in status_urnas():
        if not u["ativa"] or (u["reserva"] and u["nunca_conectou"]):
            continue
        if u["nunca_conectou"]:
            problemas.append(("problema_nunca_conectou", {"urna": u["id"]}))
        elif not u["online"]:
            problemas.append(("problema_offline", {"urna": u["id"], "s": u["segundos_sem_sinal"]}))
        elif u["pendentes"]:
            problemas.append(("problema_pendentes", {"urna": u["id"], "n": u["pendentes"]}))
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
            "teste": bool(l["teste"]),
            "celular": bool(l["celular"]),
            **posicao_no_questionario(l),
            # pergunta encadeada só pode ser ativada depois de revelada a anterior
            "liberada": anterior is None or anterior["estado"] == "REVELADA",
        })
    return resposta

@app.post("/api/admin/sessoes/{sid}/arquivar", dependencies=[Depends(exigir_admin)])
async def arquivar_sessao(sid: int):
    sessao = db.execute("SELECT ativa FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, msg("sessao_inexistente"))
    if sessao["ativa"]:
        raise HTTPException(409, msg("ative_outra_antes"))
    with db:
        db.execute("UPDATE sessoes SET arquivada = 1 WHERE id = ?", (sid,))
    registrar_evento("sessao_arquivada", f"sessao={sid}")
    return {"ok": True}

@app.post("/api/admin/sessoes/{sid}/celular", dependencies=[Depends(exigir_admin)])
async def alternar_celular(sid: int, c: Celular):
    """Liga ou desliga o voto por celular; num questionário vale para todas as perguntas."""
    sessao = db.execute("SELECT id, grupo_id FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, msg("sessao_inexistente"))
    grupo = sessao["grupo_id"] or sessao["id"]
    with db:
        db.execute("UPDATE sessoes SET celular = ? WHERE id = ? OR grupo_id = ?", (int(c.ativo), grupo, grupo))
    registrar_evento("celular_ligado" if c.ativo else "celular_desligado", f"sessao={sid}")
    await gerente.broadcast(estado_publico(), "telao", "mesario")
    return {"celular": c.ativo}

@app.post("/api/admin/sessoes/{sid}/zerar")
async def zerar_sessao(sid: int, dados: Zerar, responsavel: str = Depends(exigir_admin)):
    sessao = db.execute("SELECT tema, estado FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, msg("sessao_inexistente"))
    if sessao["estado"] == "REVELADA":
        raise HTTPException(409, msg("ja_revelada_zerar"))
    if dados.confirmacao.strip().casefold() != sessao["tema"].casefold():
        raise HTTPException(400, msg("confirmacao_nao_confere"))
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
        raise HTTPException(404, msg("sessao_inexistente"))
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
        sid = inserir_sessao(nova.tema, opcoes, teste=nova.teste, celular=nova.celular)
    registrar_evento("sessao_criada", f"sessao={sid}")
    return {"id": sid}

def validar_opcoes(nova: NovaSessao) -> list[dict]:
    opcoes = [
        {"chave": op.chave or gerar_chave(op.rotulo), "rotulo": op.rotulo, "cor": op.cor}
        for op in nova.opcoes
    ]
    if len({op["chave"] for op in opcoes}) != len(opcoes):
        raise HTTPException(400, msg("opcoes_repetidas"))
    return opcoes

def validar_temas_livres(temas: list[str]):
    if len({t.casefold() for t in temas}) != len(temas):
        raise HTTPException(400, msg("perguntas_repetidas"))
    existentes = {s["tema"].casefold() for s in db.execute("SELECT tema FROM sessoes")}
    if any(t.casefold() in existentes for t in temas):
        raise HTTPException(409, msg("tema_existente"))

@app.post("/api/admin/questionarios", status_code=201, dependencies=[Depends(exigir_admin)])
async def criar_questionario(novo: NovoQuestionario):
    opcoes = [validar_opcoes(p) for p in novo.perguntas]
    validar_temas_livres([p.tema for p in novo.perguntas])
    with db:
        ids = [inserir_sessao(novo.perguntas[0].tema, opcoes[0], teste=novo.teste, celular=novo.celular)]
        db.execute("UPDATE sessoes SET grupo_id = ? WHERE id = ?", (ids[0], ids[0]))
        for n, (p, ops) in enumerate(zip(novo.perguntas[1:], opcoes[1:]), start=2):
            ids.append(inserir_sessao(p.tema, ops, grupo_id=ids[0], pergunta=n, teste=novo.teste,
                                      celular=novo.celular))
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
        raise HTTPException(status_code=404, detail=msg("sessao_inexistente"))
    if sessao["arquivada"]:
        raise HTTPException(409, msg("desarquive_antes"))
    anterior = pergunta_anterior(sessao)
    if anterior and anterior["estado"] != "REVELADA":
        raise HTTPException(409, msg("revele_anterior"))
    with db:
        db.execute("UPDATE sessoes SET ativa = 0")
        db.execute("UPDATE sessoes SET ativa = 1 WHERE id = ?", (sid,))
    await gerente.broadcast(estado_publico(), "telao", "mesario")
    registrar_evento("sessao_ativada", f"sessao={sid}")
    return {"sessao": buscar_sessao_ativa()}

def inserir_urna(u: NovaUrna) -> str:
    """Cadastra a urna (dentro da transação de quem chama) e devolve o token, que só existe aqui."""
    if u.id.lower() == URNA_CELULAR:
        raise HTTPException(409, msg("id_reservado"))
    token = secrets.token_urlsafe(32)
    try:
        db.execute(
            "INSERT INTO urnas (id, nome, token_hash, reserva, teste, criada_em) VALUES (?, ?, ?, ?, ?, ?)",
            (u.id, u.nome, hash_token(token), int(u.reserva), int(u.teste), agora()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=msg("urna_existente"))
    return token

@app.post("/api/admin/urnas", dependencies=[Depends(exigir_admin)])
async def cadastrar_urna(u: NovaUrna):
    with db:
        token = inserir_urna(u)
    registrar_evento("urna_cadastrada", f"urna={u.id}")
    return {"id": u.id, "token": token}

# ---------- Pedido de cadastro de urna ----------
# A urna sem configuração pede um código curto e o mostra na tela; o mesário confere
# o código no painel e aprova, e a urna recebe id e token sem precisar de link.
# O segredo do pedido fica só na urna (aqui, o hash); o token da urna aprovada fica
# guardado até a urna buscá-lo, no máximo até o pedido expirar.
VALIDADE_PEDIDO = 15 * 60
MAX_PEDIDOS = 20
LETRAS_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O e 1/I, que se confundem na tela

def apagar_pedidos_vencidos():
    with db:
        db.execute("DELETE FROM pedidos_urna WHERE criado_em < ?", (time.time() - VALIDADE_PEDIDO,))

def pedidos_pendentes() -> list[dict]:
    apagar_pedidos_vencidos()
    return [
        {"codigo": p["codigo"], "segundos": int(time.time() - p["criado_em"])}
        for p in db.execute("SELECT codigo, criado_em FROM pedidos_urna WHERE urna_id IS NULL ORDER BY criado_em")
    ]

@app.post("/api/urnas/pedido", status_code=201)
async def pedir_cadastro():
    apagar_pedidos_vencidos()
    if db.execute("SELECT COUNT(*) FROM pedidos_urna WHERE urna_id IS NULL").fetchone()[0] >= MAX_PEDIDOS:
        raise recusa(429, "muitos_pedidos")
    segredo = secrets.token_urlsafe(32)
    while True:
        codigo = "".join(secrets.choice(LETRAS_CODIGO) for _ in range(4))
        try:
            with db:
                db.execute("INSERT INTO pedidos_urna (segredo_hash, codigo, criado_em) VALUES (?, ?, ?)",
                           (hash_token(segredo), codigo, time.time()))
            break
        except sqlite3.IntegrityError:
            continue  # código já em uso por outro pedido: sorteia outro
    await gerente.broadcast({"tipo": "pedidos", "pedidos": pedidos_pendentes()}, "mesario")
    return {"codigo": codigo, "segredo": segredo, "validade": VALIDADE_PEDIDO}

@app.post("/api/urnas/pedido/situacao")
async def situacao_pedido(p: PedidoUrna):
    apagar_pedidos_vencidos()
    pedido = db.execute("SELECT * FROM pedidos_urna WHERE segredo_hash = ?", (hash_token(p.segredo),)).fetchone()
    if not pedido:
        raise recusa(404, "pedido_expirado")
    if not pedido["urna_id"]:
        return {"aprovado": False, "codigo": pedido["codigo"]}
    # o token é entregue uma única vez
    with db:
        db.execute("DELETE FROM pedidos_urna WHERE segredo_hash = ?", (pedido["segredo_hash"],))
    return {"aprovado": True, "id": pedido["urna_id"], "token": pedido["token"]}

@app.get("/api/admin/pedidos", dependencies=[Depends(exigir_admin)])
async def listar_pedidos():
    return pedidos_pendentes()

@app.post("/api/admin/pedidos/{codigo}/aprovar", dependencies=[Depends(exigir_admin)])
async def aprovar_pedido(codigo: str, u: NovaUrna):
    apagar_pedidos_vencidos()
    codigo = codigo.upper()
    with db:
        if not db.execute("SELECT 1 FROM pedidos_urna WHERE codigo = ? AND urna_id IS NULL", (codigo,)).fetchone():
            raise HTTPException(404, msg("pedido_inexistente"))
        token = inserir_urna(u)
        db.execute("UPDATE pedidos_urna SET urna_id = ?, token = ? WHERE codigo = ?", (u.id, token, codigo))
    registrar_evento("urna_cadastrada", f"urna={u.id} pedido={codigo}")
    await gerente.broadcast({"tipo": "pedidos", "pedidos": pedidos_pendentes()}, "mesario")
    return {"id": u.id}

@app.delete("/api/admin/pedidos/{codigo}", dependencies=[Depends(exigir_admin)])
async def recusar_pedido(codigo: str):
    with db:
        cur = db.execute("DELETE FROM pedidos_urna WHERE codigo = ? AND urna_id IS NULL", (codigo.upper(),))
    if not cur.rowcount:
        raise HTTPException(404, msg("pedido_inexistente"))
    await gerente.broadcast({"tipo": "pedidos", "pedidos": pedidos_pendentes()}, "mesario")
    return {"ok": True}

@app.post("/api/admin/urnas/{uid}/novo-token", dependencies=[Depends(exigir_admin)])
async def reemitir_token(uid: str):
    # só o hash fica no banco: para mostrar o link de novo é preciso trocar o token
    urna = db.execute("SELECT ativa FROM urnas WHERE id = ?", (uid,)).fetchone()
    if not urna:
        raise HTTPException(404, msg("urna_inexistente"))
    if not urna["ativa"]:
        raise HTTPException(409, msg("urna_desativada"))
    token = secrets.token_urlsafe(32)
    with db:
        db.execute("UPDATE urnas SET token_hash = ? WHERE id = ?", (hash_token(token), uid))
    registrar_evento("urna_token_reemitido", f"urna={uid}")
    return {"id": uid, "token": token}

@app.post("/api/admin/urnas/{uid}/desativar", dependencies=[Depends(exigir_admin)])
async def desativar_urna(uid: str):
    with db:
        cur = db.execute("UPDATE urnas SET ativa = 0 WHERE id = ?", (uid,))
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail=msg("urna_inexistente"))
    registrar_evento("urna_desativada", f"urna={uid}")
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
        raise HTTPException(404, msg("sessao_inexistente"))
    if not sessao["ativa"]:
        raise HTTPException(409, msg("ative_antes"))
    novo = TRANSICOES.get(sessao["estado"])
    if not novo:
        raise HTTPException(409, msg("ja_revelada"))

    if novo == "REVELADA":
        problemas = problemas_para_revelar()
        if problemas and not forcar:
            raise HTTPException(409, {"mensagem": msg("pendencias"), "problemas": [msg(c, **v) for c, v in problemas]})
    else:
        problemas = []

    # o WHERE estado = ? torna a transição atômica: com vários processos, dois
    # cliques simultâneos não avançam a sessão duas vezes
    with db:
        mudou = db.execute(
            "UPDATE sessoes SET estado = ?, encerrada_em = COALESCE(?, encerrada_em) WHERE id = ? AND estado = ?",
            (novo, agora() if novo == "ENCERRADA" else None, sid, sessao["estado"]),
        ).rowcount
    if not mudou:
        raise HTTPException(409, msg("mudou_estado"))
    if problemas:
        registrar_evento("revelacao_forcada", f"sessao={sid} " + "; ".join(msg(c, "pt", **v) for c, v in problemas))

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
    sinais.registrar(urna_id, hb.pendentes, hb.recusados)
    return {"sessao": buscar_sessao_ativa()}

@app.get("/api/admin/urnas", dependencies=[Depends(exigir_admin)])
async def listar_urnas():
    return status_urnas()

# ---------- Monitoramento ----------
def contar_urnas() -> tuple[int, int]:
    # reserva que nunca conectou não é urna fora do ar (mesma regra da revelação)
    ativas = [u for u in status_urnas() if u["ativa"] and not (u["reserva"] and u["nunca_conectou"])]
    return sum(u["online"] for u in ativas), len(ativas)

@app.get("/api/admin/metricas", dependencies=[Depends(exigir_admin)])
async def ver_metricas():
    online, ativas = contar_urnas()
    s = buscar_sessao_ativa()
    return {
        "votos_por_minuto": metricas.votos_por_minuto(),
        "latencia_ms": metricas.percentis(),
        "urnas": {"online": online, "ativas": ativas},
        "sessao": {**s, "total": total_votos(s["id"])} if s else None,
        "votos_total": dict(metricas.votos_total),
        "recusados_total": dict(metricas.recusados_total),
    }

@app.get("/metrics", dependencies=[Depends(exigir_admin)])
async def metricas_prometheus():
    return Response(formato_prometheus(*contar_urnas()), media_type="text/plain; version=0.0.4")

@app.get("/api/admin/eventos", dependencies=[Depends(exigir_admin)])
async def listar_eventos():
    return [dict(e) for e in db.execute("SELECT * FROM eventos ORDER BY id")]

@app.get("/api/admin/sessoes/{sid}/votos.csv", dependencies=[Depends(exigir_admin)])
async def exportar_votos(sid: int):
    sessao = db.execute("SELECT estado FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise HTTPException(404, msg("sessao_inexistente"))
    if sessao["estado"] != "REVELADA":
        raise HTTPException(409, msg("exportacao_apos_revelar"))

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["id", "urna_id", "opcao", "votado_em", "recebido_em"])
    for v in db.execute(
        "SELECT id, urna_id, opcao_chave, votado_em, recebido_em "
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
        raise HTTPException(404, msg("urna_inexistente"))
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

# ---------- Modo teste ----------
# Sessões e urnas de teste servem para ensaiar em produção. "Limpar testes" apaga
# tudo o que é delas (votos, cédulas, opções e eventos), deixando o banco como se
# os testes nunca tivessem acontecido. Urna de teste não vota em sessão real.

def marcados(campos: dict, sessoes: set[str], urnas: set[str]) -> bool:
    return bool({campos.get("sessao"), campos.get("grupo")} & sessoes or campos.get("urna") in urnas)

@app.post("/api/admin/testes/limpar", dependencies=[Depends(exigir_admin)])
async def limpar_testes():
    sessoes = [r[0] for r in db.execute("SELECT id FROM sessoes WHERE teste = 1")]
    urnas = [r[0] for r in db.execute("SELECT id FROM urnas WHERE teste = 1")]
    ativa = buscar_sessao_ativa()
    em_s = ",".join("?" * len(sessoes))
    em_u = ",".join("?" * len(urnas))
    eventos = [
        e["id"] for e in db.execute("SELECT id, detalhe FROM eventos")
        if marcados(dict(p.split("=", 1) for p in e["detalhe"].split() if "=" in p),
                    {str(s) for s in sessoes}, set(urnas))
    ]
    with db:
        votos = db.execute(f"DELETE FROM votos WHERE sessao_id IN ({em_s}) OR urna_id IN ({em_u})",
                           (*sessoes, *urnas)).rowcount
        db.execute(f"DELETE FROM cedulas WHERE sessao_id IN ({em_s})", sessoes)
        db.execute(f"DELETE FROM opcoes WHERE sessao_id IN ({em_s})", sessoes)
        db.execute(f"DELETE FROM sessoes WHERE id IN ({em_s})", sessoes)
        db.execute(f"DELETE FROM urnas WHERE id IN ({em_u})", urnas)
        db.execute(f"DELETE FROM eventos WHERE id IN ({','.join('?' * len(eventos))})", eventos)
        if ativa and ativa["teste"]:
            # ativar o teste desativou a sessão real que estava ativa: ela volta
            ultima = db.execute(
                "SELECT detalhe FROM eventos WHERE tipo = 'sessao_ativada' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if ultima:
                anterior = dict(p.split("=", 1) for p in ultima["detalhe"].split() if "=" in p)["sessao"]
                db.execute("UPDATE sessoes SET ativa = 1 WHERE id = ?", (int(anterior),))
    # registrado só no log: um evento no banco seria justamente o resto que a limpeza evita
    log("testes_limpos", sessoes=len(sessoes), urnas=len(urnas), votos=votos, eventos=len(eventos))
    if ativa and ativa["teste"]:
        await gerente.broadcast(estado_publico(), "telao", "mesario")
    return {"sessoes": len(sessoes), "urnas": len(urnas), "votos": votos, "eventos": len(eventos)}

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
    if tipo == "celular_ligado":
        return "Voto por celular ligado"
    if tipo == "celular_desligado":
        return "Voto por celular desligado"
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
    linhas = db.execute("SELECT * FROM sessoes WHERE estado = 'REVELADA' AND teste = 0 ORDER BY id")
    return [{"id": l["id"], "tema": l["tema"], **pergunta_publica(l)} for l in linhas]

def pergunta_publica(s) -> dict:
    # só a posição: o id da próxima pergunta não interessa ao público
    p = posicao_no_questionario(s)
    return {"pergunta": p["pergunta"], "total_perguntas": p["total_perguntas"]}

@app.get("/api/auditoria/sessoes/{sid}")
async def auditoria_sessao(sid: int):
    sessao = db.execute("SELECT * FROM sessoes WHERE id = ?", (sid,)).fetchone()
    # mesma resposta para inexistente e não revelada: não confirma nada antes da hora
    if not sessao or sessao["estado"] != "REVELADA" or sessao["teste"]:
        raise HTTPException(404, msg("auditoria_apos_revelar"))
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
    sessao = db.execute("SELECT estado, ativa, celular FROM sessoes WHERE id = ?", (sid,)).fetchone()
    if not sessao:
        raise recusa(404, "sessao_inexistente")
    if not sessao["celular"]:
        raise recusa(409, "celular_desligado")
    if not sessao["ativa"] or sessao["estado"] != "ABERTA":
        raise recusa(409, "sessao_fechada")

@app.get("/api/admin/telao", dependencies=[Depends(exigir_admin)])
async def link_telao():
    return {"chave": chave_telao()}

@app.get("/api/telao/codigo", dependencies=[Depends(exigir_telao)])
async def codigo_telao():
    s = buscar_sessao_ativa()
    if not s or s["estado"] != "ABERTA" or not s["celular"]:
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
        raise recusa(403, "codigo_expirado")
    cedula = secrets.token_urlsafe(32)
    with db:
        db.execute(
            "INSERT INTO cedulas (token_hash, sessao_id, criada_em) VALUES (?, ?, ?)",
            (hash_token(cedula), e.sessao_id, agora()),
        )
    return {"cedula": cedula, "sessao": buscar_sessao_ativa()}

@app.post("/api/celular/cedula")
async def conferir_cedula(p: ProximaCedula):
    """O celular confere a cédula guardada: zerar a contagem, limpar testes ou um banco
    novo apagam cédulas, e o número da sessão pode ter sido reaproveitado."""
    cedula = db.execute("SELECT sessao_id, voto_id FROM cedulas WHERE token_hash = ?",
                        (hash_token(p.cedula),)).fetchone()
    if not cedula:
        raise recusa(401, "cedula_invalida")
    return {"sessao_id": cedula["sessao_id"], "votou": cedula["voto_id"] is not None}

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
        raise recusa(401, "cedula_invalida")
    ativa = buscar_sessao_ativa()
    if (not ativa or ativa["grupo_id"] is None or ativa["grupo_id"] != cedula["grupo_id"]
            or ativa["pergunta"] <= cedula["pergunta"]):
        raise recusa(409, "sem_proxima")
    sessao_aberta(ativa["id"])
    nova = secrets.token_urlsafe(32)
    with db:
        # o WHERE garante uma única cédula seguinte mesmo com dois pedidos simultâneos
        if not db.execute(
            "UPDATE cedulas SET seguinte_emitida = 1 WHERE token_hash = ? AND seguinte_emitida = 0",
            (cedula["token_hash"],),
        ).rowcount:
            raise recusa(409, "cedula_usada")
        db.execute(
            "INSERT INTO cedulas (token_hash, sessao_id, criada_em) VALUES (?, ?, ?)",
            (hash_token(nova), ativa["id"], agora()),
        )
    return {"cedula": nova, "sessao": ativa}

@app.post("/api/celular/votar")
async def votar_celular(v: VotoCelular):
    try:
        sid, novo = await gravar_voto_celular(v)
    except HTTPException as e:
        registrar_recusa(e, None, URNA_CELULAR)
        raise
    if novo:
        metricas.voto_aceito(URNA_CELULAR)
        log("voto_recebido", sessao=sid, urna=URNA_CELULAR, voto=str(v.id))
    else:
        log("voto_reenviado", sessao=sid, urna=URNA_CELULAR, voto=str(v.id))
    return {"ok": True}

async def gravar_voto_celular(v: VotoCelular) -> tuple[int, bool]:
    """Grava o voto da cédula; devolve a sessão e se o voto é novo (False no reenvio)."""
    cedula = db.execute("SELECT * FROM cedulas WHERE token_hash = ?", (hash_token(v.cedula),)).fetchone()
    if not cedula:
        raise recusa(401, "cedula_invalida")
    if cedula["voto_id"]:
        # reenvio do mesmo voto (rede instável) é aceito; um segundo voto, não
        if cedula["voto_id"] == str(v.id):
            return cedula["sessao_id"], False
        raise recusa(409, "ja_votou")
    sessao_aberta(cedula["sessao_id"])
    if not db.execute("SELECT 1 FROM opcoes WHERE sessao_id = ? AND chave = ?",
                      (cedula["sessao_id"], v.opcao)).fetchone():
        raise recusa(400, "opcao_invalida")

    try:
        with db:
            # o WHERE voto_id IS NULL garante uso único mesmo com dois envios simultâneos
            marcada = db.execute(
                "UPDATE cedulas SET voto_id = ? WHERE token_hash = ? AND voto_id IS NULL",
                (str(v.id), cedula["token_hash"]),
            ).rowcount
            if not marcada:
                raise recusa(409, "ja_votou")
            db.execute(
                "INSERT INTO votos (id, sessao_id, urna_id, opcao_chave, votado_em, recebido_em) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(v.id), cedula["sessao_id"], URNA_CELULAR, v.opcao, agora(), agora()),
            )
    except sqlite3.IntegrityError:
        # id de voto que já existe: a transação desfaz a marcação da cédula
        raise recusa(409, "voto_repetido")
    await gerente.broadcast(
        {"tipo": "total", "sessao_id": cedula["sessao_id"], "total": total_votos(cedula["sessao_id"])},
        "telao", "mesario",
    )
    return cedula["sessao_id"], True



class Estaticos(StaticFiles):
    """Sem Cache-Control, o navegador guarda os arquivos por heurística e mistura,
    depois de um deploy, HTML novo com JS antigo. no-cache faz revalidar sempre:
    sem mudança, a resposta é um 304 sem corpo."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta

app.mount("/", Estaticos(directory="static", html=True), name="static")