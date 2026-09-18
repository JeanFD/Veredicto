import pytest
from tests.auxiliares import ADMIN, novo_voto

def preparar_encerrada(cliente):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)

def test_urna_nunca_conectou_aparece(cliente, urna):
    [u] = cliente.get("/api/admin/urnas", auth=ADMIN).json()
    assert u["nunca_conectou"] is True

def test_revelar_bloqueia_com_pendentes(cliente, urna):
    preparar_encerrada(cliente)
    cliente.post("/api/urnas/heartbeat", json={"pendentes": 3}, headers=urna)
    r = cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    assert r.status_code == 409
    assert "3 votos pendentes" in r.json()["detail"]["problemas"][0]
    r = cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN)
    assert r.status_code == 200

def test_reserva_sem_uso_nao_bloqueia(cliente):
    cliente.post("/api/admin/urnas", json={"id": "reserva1", "nome": "R", "reserva": True}, auth=ADMIN)
    preparar_encerrada(cliente)
    assert cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN).status_code == 200

@pytest.mark.parametrize("n_urnas", [1, 3, 10])
def test_total_bate_com_varias_urnas(cliente, n_urnas):
    tokens = []
    for i in range(n_urnas):
        r = cliente.post("/api/admin/urnas", json={"id": f"u{i}", "nome": f"U{i}"}, auth=ADMIN)
        tokens.append({"X-Urna-Token": r.json()["token"]})
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)

    for headers in tokens:
        for _ in range(5):
            voto = novo_voto()
            cliente.post("/api/votos", json=voto, headers=headers)
            cliente.post("/api/votos", json=voto, headers=headers)   

    urnas = cliente.get("/api/admin/urnas", auth=ADMIN).json()
    assert sum(u["votos_sessao"] for u in urnas) == n_urnas * 5