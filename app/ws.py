import asyncio
import json

from fastapi import WebSocket

from app.observabilidade import log

# Com REDIS_URL, cada evento é publicado neste canal e todo processo (inclusive o
# que publicou) o entrega aos seus clientes: assim o telão conectado num processo
# vê o voto que chegou por outro. Sem Redis, a entrega é direta, como sempre foi.
CANAL = "veredicto:ws"

class Gerente:
    def __init__(self, redis=None):
        self.salas: dict[str, set[WebSocket]] = {"telao": set(), "mesario": set()}
        self.redis = redis

    def adicionar(self, ws: WebSocket, sala: str):
        self.salas[sala].add(ws)

    def remover(self, ws: WebSocket):
        for conexoes in self.salas.values():
            conexoes.discard(ws)

    async def entregar(self, msg: dict, salas):
        """Só para os clientes conectados a este processo."""
        for sala in salas:
            for ws in list(self.salas[sala]):
                try:
                    await ws.send_json(msg)
                except Exception:
                    self.remover(ws)

    async def broadcast(self, msg: dict, *salas: str):
        if self.redis:
            try:
                await self.redis.publish(CANAL, json.dumps({"salas": salas, "msg": msg}))
                return
            except Exception as e:
                # Redis fora: ao menos os clientes deste processo continuam recebendo
                log("redis_indisponivel", erro=type(e).__name__)
        await self.entregar(msg, salas)

    async def escutar(self):
        """Tarefa de fundo: entrega aqui o que qualquer processo publicou."""
        while True:
            try:
                async with self.redis.pubsub() as assinatura:
                    await assinatura.subscribe(CANAL)
                    async for m in assinatura.listen():
                        if m["type"] == "message":
                            dados = json.loads(m["data"])
                            await self.entregar(dados["msg"], dados["salas"])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log("redis_indisponivel", erro=type(e).__name__)
                await asyncio.sleep(1)

def criar_gerente():
    from app.compartilhado import REDIS_URL, conectar_async
    return Gerente(conectar_async() if REDIS_URL else None)

gerente = criar_gerente()
