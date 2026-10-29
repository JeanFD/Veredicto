"""Cadastro de urna por pedido: a urna pede um código, o mesário aprova e a urna recebe o token."""
import time

import app.main
from app.db import db
from tests.auxiliares import ADMIN, login, novo_voto

def pedir(cliente):
    r = cliente.post("/api/urnas/pedido")
    assert r.status_code == 201
    return r.json()

def situacao(cliente, segredo):
    return cliente.post("/api/urnas/pedido/situacao", json={"segredo": segredo})

def aprovar(cliente, codigo, uid="urna-nova"):
    return cliente.post(f"/api/admin/pedidos/{codigo}/aprovar", json={"id": uid, "nome": "Entrada"}, auth=ADMIN)

def test_pedido_aprovado_vira_urna_que_vota(cliente):
    p = pedir(cliente)
    assert len(p["codigo"]) == 4
    assert situacao(cliente, p["segredo"]).json() == {"aprovado": False, "codigo": p["codigo"]}
    assert cliente.get("/api/admin/pedidos", auth=ADMIN).json()[0]["codigo"] == p["codigo"]

    assert aprovar(cliente, p["codigo"].lower()).json() == {"id": "urna-nova"}
    assert cliente.get("/api/admin/pedidos", auth=ADMIN).json() == []
    r = situacao(cliente, p["segredo"]).json()
    assert r["aprovado"] and r["id"] == "urna-nova"

    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    assert cliente.post("/api/votos", json=novo_voto(), headers={"X-Urna-Token": r["token"]}).status_code == 200

def test_token_entregue_uma_vez_so(cliente):
    p = pedir(cliente)
    aprovar(cliente, p["codigo"])
    assert situacao(cliente, p["segredo"]).json()["aprovado"]
    assert situacao(cliente, p["segredo"]).status_code == 404
    assert db.execute("SELECT COUNT(*) FROM pedidos_urna").fetchone()[0] == 0

def test_pedido_recusado(cliente):
    p = pedir(cliente)
    assert cliente.delete(f"/api/admin/pedidos/{p['codigo']}", auth=ADMIN).status_code == 200
    r = situacao(cliente, p["segredo"])
    assert r.status_code == 404 and r.json()["detail"]["motivo"] == "pedido_expirado"
    assert aprovar(cliente, p["codigo"]).status_code == 404

def test_pedido_expira(cliente):
    p = pedir(cliente)
    with db:
        db.execute("UPDATE pedidos_urna SET criado_em = ?", (time.time() - app.main.VALIDADE_PEDIDO - 1,))
    assert situacao(cliente, p["segredo"]).status_code == 404
    assert cliente.get("/api/admin/pedidos", auth=ADMIN).json() == []

def test_id_repetido_nao_consome_o_pedido(cliente):
    cliente.post("/api/admin/urnas", json={"id": "urna-nova", "nome": "Já existe"}, auth=ADMIN)
    p = pedir(cliente)
    assert aprovar(cliente, p["codigo"]).status_code == 409
    assert aprovar(cliente, p["codigo"], "outra").status_code == 200

def test_limite_de_pedidos_pendentes(cliente, monkeypatch):
    monkeypatch.setattr(app.main, "MAX_PEDIDOS", 2)
    pedir(cliente)
    pedir(cliente)
    r = cliente.post("/api/urnas/pedido")
    assert r.status_code == 429 and r.json()["detail"]["motivo"] == "muitos_pedidos"

def test_painel_recebe_o_pedido_na_hora(cliente):
    with cliente.websocket_connect("/ws/mesario") as ws:
        ws.send_json({"token": login(cliente)})
        ws.receive_json()  # snapshot
        p = pedir(cliente)
        m = ws.receive_json()
        while m["tipo"] != "pedidos":
            m = ws.receive_json()
        assert [x["codigo"] for x in m["pedidos"]] == [p["codigo"]]

def test_aprovar_e_listar_exigem_senha(cliente):
    p = pedir(cliente)
    assert cliente.get("/api/admin/pedidos").status_code == 401
    assert cliente.post(f"/api/admin/pedidos/{p['codigo']}/aprovar", json={"id": "x", "nome": "x"}).status_code == 401
    assert cliente.delete(f"/api/admin/pedidos/{p['codigo']}").status_code == 401
