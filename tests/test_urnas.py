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
def test_status_mostra_votos_recusados_da_urna(cliente, urna):
    cliente.post("/api/urnas/heartbeat", json={"pendentes": 0, "recusados": 2}, headers=urna)
    [u] = cliente.get("/api/admin/urnas", auth=ADMIN).json()
    assert u["recusados"] == 2

# ---------- apagar ----------
def test_admin_apaga_urna_sem_votos(cliente):
    cliente.post("/api/admin/urnas", json={"id": "urna-velha", "nome": "Velha"}, auth=ADMIN)
    cliente.post("/api/admin/urnas/urna-velha/desativar", auth=ADMIN)
    assert cliente.delete("/api/admin/urnas/urna-velha", auth=ADMIN).status_code == 200
    assert [u["id"] for u in cliente.get("/api/admin/urnas", auth=ADMIN).json()] == []
    assert "urna_apagada" in [e["tipo"] for e in cliente.get("/api/admin/eventos", auth=ADMIN).json()]
    assert cliente.delete("/api/admin/urnas/urna-velha", auth=ADMIN).status_code == 404

def test_urna_com_votos_nao_e_apagada(cliente, urna, sessao_aberta):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    r = cliente.delete("/api/admin/urnas/urna-teste", auth=ADMIN)
    assert r.status_code == 409 and "desative" in r.json()["detail"]
    assert [u["id"] for u in cliente.get("/api/admin/urnas", auth=ADMIN).json()] == ["urna-teste"]

def test_apagar_urna_e_so_do_admin(cliente):
    cliente.post("/api/admin/urnas", json={"id": "urna-velha", "nome": "Velha"}, auth=ADMIN)
    cliente.post("/api/admin/contas", auth=ADMIN,
                 json={"usuario": "maria", "nome": "Maria", "papel": "mesario", "senha": "senha-boa-1"})
    assert cliente.delete("/api/admin/urnas/urna-velha", auth=("maria", "senha-boa-1")).status_code == 403
    assert cliente.delete("/api/admin/urnas/urna-velha").status_code == 401

def test_grade_traz_o_total_de_votos_da_urna(cliente, urna, sessao_aberta):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    assert [u["votos_total"] for u in cliente.get("/api/admin/urnas", auth=ADMIN).json()] == [1]

def test_painel_recebe_a_grade_na_hora(cliente):
    """Cadastrar e desativar aparecem na hora, sem esperar o aviso de 5 em 5 segundos."""
    from tests.auxiliares import login
    with cliente.websocket_connect("/ws/mesario") as ws:
        ws.send_json({"token": login(cliente)})
        ws.receive_json()  # snapshot
        cliente.post("/api/admin/urnas", json={"id": "nova", "nome": "Nova"}, auth=ADMIN)
        assert [u["id"] for u in ws.receive_json()["urnas"]] == ["nova"]
        cliente.post("/api/admin/urnas/nova/desativar", auth=ADMIN)
        assert [u["ativa"] for u in ws.receive_json()["urnas"]] == [False]
