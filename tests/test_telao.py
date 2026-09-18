from tests.auxiliares import novo_voto

def test_telao_recebe_snapshot_e_total(cliente, urna, sessao_aberta):
    with cliente.websocket_connect("/ws/telao") as ws:
        inicial = ws.receive_json()
        assert inicial["tipo"] == "snapshot"
        assert inicial["total"] == 0

        voto1 = novo_voto()
        cliente.post("/api/votos", json=voto1, headers=urna)
        assert ws.receive_json() == {"tipo": "total", "sessao_id": 1, "total": 1}

        cliente.post("/api/votos", json=voto1, headers=urna)

        voto2 = novo_voto()
        cliente.post("/api/votos", json=voto2, headers=urna)

        assert ws.receive_json() == {"tipo": "total", "sessao_id": 1, "total": 2}