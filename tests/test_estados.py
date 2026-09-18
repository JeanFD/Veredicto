from tests.auxiliares import ADMIN, novo_voto

def avancar(cliente, sid=1, **params):
    return cliente.post(f"/api/admin/sessoes/{sid}/avancar", params=params, auth=ADMIN)

def test_fluxo_completo(cliente):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    assert avancar(cliente).json()["estado"] == "ABERTA"
    assert avancar(cliente).json()["estado"] == "ENCERRADA"
    assert avancar(cliente).json()["estado"] == "REVELADA"
    assert avancar(cliente).status_code == 409

def test_sessao_inativa_nao_avanca(cliente):
    assert avancar(cliente).status_code == 409

def test_resultado_so_apos_revelar(cliente, urna):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    avancar(cliente)                                   # ABERTA
    cliente.post("/api/votos", json=novo_voto("defesa"), headers=urna)
    avancar(cliente)                                   # ENCERRADA

    with cliente.websocket_connect("/ws/telao") as ws:
        assert "resultado" not in ws.receive_json()

    avancar(cliente, forcar="true")                                   # REVELADA
    with cliente.websocket_connect("/ws/telao") as ws:
        resultado = {o["chave"]: o["votos"] for o in ws.receive_json()["resultado"]}
    assert resultado == {"acusacao": 0, "defesa": 1}


def test_mesario_senha_errada_desconecta(cliente):
    with cliente.websocket_connect("/ws/mesario") as ws:
        ws.send_json({"senha": "errada"})
        mensagem = ws.receive()
        assert mensagem["type"] == "websocket.close"
        assert mensagem["code"] == 4401


        