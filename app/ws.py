from fastapi import WebSocket

class Gerente:
    def __init__(self):
        self.salas: dict[str, set[WebSocket]] = {"telao": set(), "mesario": set()}

    def adicionar(self, ws: WebSocket, sala: str):
        self.salas[sala].add(ws)

    def remover(self, ws: WebSocket):
        for conexoes in self.salas.values():
            conexoes.discard(ws)

    async def broadcast(self, msg: dict, *salas: str):
        for sala in salas:
            for ws in list(self.salas[sala]):
                try:
                    await ws.send_json(msg)
                except Exception:
                    self.remover(ws)

gerente = Gerente()
