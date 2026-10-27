"""Caminho com vários processos (REDIS_URL), com fakeredis no lugar do Redis.

A propagação entre processos de verdade fica em test_redis_processos.py.
"""
import asyncio

import fakeredis
import pytest

from app.compartilhado import FalhasRedis, SinaisRedis, MAX_FALHAS
from app.observabilidade import MetricasRedis
from app.ws import Gerente
from app.db import db
from tests.auxiliares import ADMIN

class WsFalso:
    def __init__(self):
        self.recebidas = []

    async def send_json(self, msg):
        self.recebidas.append(msg)

async def esperar(condicao, segundos=2.0):
    for _ in range(int(segundos / 0.02)):
        if condicao():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condição não atingida a tempo")

@pytest.fixture
def servidor():
    return fakeredis.FakeServer()

def cliente_sync(servidor):
    return fakeredis.FakeRedis(server=servidor, decode_responses=True)

# ---------- pub/sub ----------
def test_evento_publicado_por_um_processo_chega_nos_outros(servidor):
    async def cenario():
        processos = [Gerente(fakeredis.FakeAsyncRedis(server=servidor, decode_responses=True)) for _ in range(3)]
        telas = [WsFalso() for _ in processos]
        mesario = WsFalso()
        for g, ws in zip(processos, telas):
            g.adicionar(ws, "telao")
        processos[2].adicionar(mesario, "mesario")
        tarefas = [asyncio.create_task(g.escutar()) for g in processos]
        await asyncio.sleep(0.1)  # assinaturas prontas

        await processos[0].broadcast({"tipo": "total", "total": 7}, "telao")
        await esperar(lambda: all(ws.recebidas for ws in telas))
        assert [ws.recebidas for ws in telas] == [[{"tipo": "total", "total": 7}]] * 3
        assert mesario.recebidas == []  # cada evento só vai para as salas pedidas
        for t in tarefas:
            t.cancel()
    asyncio.run(cenario())

def test_redis_fora_entrega_ao_menos_aos_clientes_locais():
    class RedisQuebrado:
        async def publish(self, *args):
            raise ConnectionError("redis caiu")

    async def cenario():
        g = Gerente(RedisQuebrado())
        ws = WsFalso()
        g.adicionar(ws, "telao")
        await g.broadcast({"tipo": "total", "total": 1}, "telao")
        assert ws.recebidas == [{"tipo": "total", "total": 1}]
    asyncio.run(cenario())

def test_sem_redis_entrega_direto():
    async def cenario():
        g = Gerente()
        ws = WsFalso()
        g.adicionar(ws, "mesario")
        await g.broadcast({"tipo": "estado"}, "telao", "mesario")
        assert ws.recebidas == [{"tipo": "estado"}]
    asyncio.run(cenario())

# ---------- estado compartilhado ----------
def test_heartbeat_visto_por_qualquer_processo(servidor):
    um, outro = SinaisRedis(cliente_sync(servidor)), SinaisRedis(cliente_sync(servidor))
    assert outro.obter("urna1") is None
    um.registrar("urna1", pendentes=3, recusados=1)
    sinal = outro.obter("urna1")
    assert (sinal["pendentes"], sinal["recusados"]) == (3, 1) and 0 <= sinal["segundos"] < 5
    outro.limpar()
    assert um.obter("urna1") is None

def test_bloqueio_de_login_somado_entre_processos(servidor):
    um, outro = FalhasRedis(cliente_sync(servidor)), FalhasRedis(cliente_sync(servidor))
    for i in range(MAX_FALHAS):
        (um if i % 2 else outro).registrar("1.2.3.4")
    assert um.bloqueado("1.2.3.4") and outro.bloqueado("1.2.3.4")
    assert not um.bloqueado("5.6.7.8")
    assert 0 < cliente_sync(servidor).ttl("veredicto:falhas:1.2.3.4") <= 300

def test_metricas_somadas_entre_processos(servidor):
    um, outro = MetricasRedis(cliente_sync(servidor)), MetricasRedis(cliente_sync(servidor))
    um.voto_aceito("urna")
    outro.voto_aceito("urna")
    outro.voto_aceito("celular")
    um.voto_recusado("sessao_encerrada")
    for ms in (10, 20, 30, 40):
        (um if ms < 25 else outro).latencia(ms)
    assert um.votos_por_minuto()[-1] == 3 and len(um.votos_por_minuto()) == 30
    assert outro.votos_total == {"urna": 2, "celular": 1}
    assert outro.recusados_total == {"sessao_encerrada": 1}
    assert um.percentis() == {"p50": 30, "p95": 40, "amostras": 4}
    um.zerar()
    assert outro.votos_total == {}

# ---------- máquina de estados ----------
def test_transicao_atomica_entre_processos(cliente, monkeypatch):
    """Outro processo revela a sessão entre a leitura e a gravação deste: 409, sem pular estado."""
    import app.main
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)  # ENCERRADA

    def outro_processo_revela_antes():
        with db:
            db.execute("UPDATE sessoes SET estado = 'REVELADA' WHERE id = 1")
        return []
    monkeypatch.setattr(app.main, "problemas_para_revelar", outro_processo_revela_antes)
    r = cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    assert r.status_code == 409
    assert db.execute("SELECT estado FROM sessoes WHERE id = 1").fetchone()[0] == "REVELADA"
