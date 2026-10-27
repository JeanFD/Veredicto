"""scripts/carga.py e scripts/caos.py: a conferência pega voto perdido ou duplicado."""
import asyncio
import random

import httpx
import pytest

from app.db import db
from app.main import app
from scripts import carga, caos
from tests.auxiliares import ADMIN

def rodar(transporte=None, **opcoes):
    async def cenario():
        async with httpx.AsyncClient(transport=transporte or httpx.ASGITransport(app=app),
                                     base_url="http://teste", auth=ADMIN) as http:
            return await carga.executar(http, intervalo=0, semente=1, **opcoes)
    return asyncio.run(cenario())

class RedeInstavel(httpx.AsyncBaseTransport):
    """Perde pedidos antes de chegar e respostas depois de o servidor gravar."""

    def __init__(self, chance=0.3):
        self.app = httpx.ASGITransport(app=app)
        self.rnd = random.Random(7)
        self.chance = chance

    async def handle_async_request(self, pedido):
        if pedido.url.path == "/api/votos" and self.rnd.random() < self.chance:
            if self.rnd.random() < 0.5:
                raise httpx.ConnectError("caiu na ida")
            await self.app.handle_async_request(pedido)
            raise httpx.ReadError("caiu na volta")
        return await self.app.handle_async_request(pedido)

class PerdeUmVoto(httpx.AsyncBaseTransport):
    """Servidor que responde 200 sem gravar um dos votos: a conferência tem de acusar."""

    def __init__(self):
        self.app = httpx.ASGITransport(app=app)
        self.engoliu = False

    async def handle_async_request(self, pedido):
        if pedido.url.path == "/api/votos" and not self.engoliu:
            self.engoliu = True
            return httpx.Response(200, json={"ok": True})
        return await self.app.handle_async_request(pedido)

def test_carga_com_reenvios_bate_voto_a_voto(cliente):
    rel = rodar(urnas=4, votos=15, reenvio=0.5)
    assert rel.problemas == []
    assert len(rel.enviados) == 60 and rel.reenvios > 0
    sessao = db.execute("SELECT id, estado FROM sessoes WHERE tema LIKE 'Carga %'").fetchone()
    assert sessao["estado"] == "REVELADA"
    assert db.execute("SELECT COUNT(*) FROM votos WHERE sessao_id = ?", (sessao["id"],)).fetchone()[0] == 60
    # as urnas de carga não ficam valendo depois do teste
    assert db.execute("SELECT COUNT(*) FROM urnas WHERE ativa = 1").fetchone()[0] == 0

def test_rede_instavel_nao_perde_nem_duplica(cliente):
    rel = rodar(RedeInstavel(), urnas=3, votos=20, reenvio=0.2)
    assert rel.problemas == []
    assert rel.falhas_de_rede > 0

def test_conferencia_acusa_voto_perdido(cliente):
    rel = rodar(PerdeUmVoto(), urnas=2, votos=5, reenvio=0)
    assert len(rel.problemas) == 1 and rel.problemas[0].endswith("perdido")

def test_conferencia_acusa_duplicado_e_voto_estranho():
    rel = carga.Relatorio(enviados={"a": ("u1", "alfa"), "b": ("u1", "beta")})
    carga.conferir("id,urna_id,opcao,votado_em,recebido_em\n"
                   "a,u1,alfa,,\na,u1,alfa,,\nb,u2,beta,,\nc,u1,alfa,,\n", rel)
    assert rel.problemas == [
        "voto a duplicado (2x)",
        "voto c no servidor, mas não foi enviado pela carga",
        "voto b gravado como u2/beta, enviado como ('u1', 'beta')",
    ]

def test_nao_roda_durante_votacao(cliente, sessao_aberta):
    with pytest.raises(SystemExit, match="votação em andamento"):
        rodar(urnas=1, votos=1)
    assert db.execute("SELECT COUNT(*) FROM sessoes WHERE tema LIKE 'Carga %'").fetchone()[0] == 0

def test_vigia_acusa_servico_fora_do_ar():
    async def cenario():
        vigias = [caos.Vigia("http://127.0.0.1:9/")]  # porta discard: ninguém escuta
        parar = asyncio.Event()
        tarefa = asyncio.create_task(caos.vigiar(vigias, parar))
        await asyncio.sleep(0.3)
        parar.set()
        await tarefa
        return vigias
    [v] = asyncio.run(cenario())
    assert v.checagens >= 1 and len(v.falhas) == v.checagens
    texto, ok = caos.relatorio(carga.Relatorio(), 1, 1, [v])
    assert not ok and "FORA DO AR" in texto

def test_caos_local_com_kill_nao_perde_votos():
    """Servidor de verdade morto com kill no meio da votação, duas vezes."""
    servidor = caos.ServidorLocal()
    servidor.subir()

    async def falhar():
        servidor.matar()
        await asyncio.sleep(0.5)
        await asyncio.to_thread(servidor.subir)
    try:
        rel, feitas, _ = asyncio.run(caos.executar(
            servidor.url, servidor.senha, falhar, quedas=2, espera=1.0,
            urnas=4, votos=40, intervalo=0.05, semente=3,
        ))
    finally:
        servidor.desligar()
    assert feitas == 2
    assert rel.problemas == []
    assert len(rel.enviados) == 160
