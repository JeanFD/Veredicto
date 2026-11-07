"""Peso dos votos: por urna e do celular por sessão; o resultado soma pontos."""
from app.db import db
from app.seguranca import chave_telao
from tests.auxiliares import ADMIN, novo_voto

TELAO = {"X-Telao-Chave": chave_telao()}

def nova_urna(cliente, uid, peso=1):
    r = cliente.post("/api/admin/urnas", json={"id": uid, "nome": uid, "peso": peso}, auth=ADMIN)
    assert r.status_code == 200, r.text
    return {"X-Urna-Token": r.json()["token"]}

def votar(cliente, urna, opcao, n=1):
    for _ in range(n):
        assert cliente.post("/api/votos", json=novo_voto(opcao), headers=urna).status_code == 200

def abrir(cliente, sid=1):
    cliente.post(f"/api/admin/sessoes/{sid}/ativar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)

def revelar(cliente, sid=1):
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar?forcar=true", auth=ADMIN)

def resultado(cliente, sid=1):
    return {o["chave"]: (o["votos"], o["pontos"]) for o in cliente.get(f"/api/auditoria/sessoes/{sid}").json()["resultado"]}

def test_turma_peso_3_contra_tecnico_peso_1(cliente):
    turma, tecnico = nova_urna(cliente, "turma", 3), nova_urna(cliente, "tecnico")
    abrir(cliente)
    votar(cliente, turma, "acusacao", 2)
    votar(cliente, tecnico, "defesa", 5)
    revelar(cliente)
    assert resultado(cliente) == {"acusacao": (2, 6), "defesa": (5, 5)}
    with cliente.websocket_connect("/ws/telao") as ws:
        m = ws.receive_json()
    assert m["total"] == 7
    assert {o["chave"]: o["pontos"] for o in m["resultado"]} == {"acusacao": 6, "defesa": 5}

def test_auditoria_mostra_peso_e_pontos_por_urna(cliente):
    turma = nova_urna(cliente, "turma", 3)
    abrir(cliente)
    votar(cliente, turma, "defesa", 2)
    revelar(cliente)
    [urna] = cliente.get("/api/auditoria/sessoes/1").json()["por_urna"]
    assert (urna["votos"], urna["peso"], urna["pontos"]) == (2, 3, 6)
    linhas = cliente.get("/api/admin/sessoes/1/votos.csv", auth=ADMIN).text.strip().splitlines()
    assert linhas[0].endswith(",peso") and all(l.endswith(",3") for l in linhas[1:])

def test_peso_fica_no_voto(cliente):
    turma = nova_urna(cliente, "turma", 3)
    abrir(cliente)
    votar(cliente, turma, "defesa")
    revelar(cliente)
    # sessão revelada: o peso pode mudar, e o voto já dado continua valendo 3
    assert cliente.post("/api/admin/urnas/turma/peso", json={"peso": 1}, auth=ADMIN).status_code == 200
    assert resultado(cliente) == {"acusacao": (0, 0), "defesa": (1, 3)}

def test_peso_bloqueado_com_votos_em_andamento(cliente):
    turma = nova_urna(cliente, "turma", 3)
    abrir(cliente)
    assert cliente.post("/api/admin/urnas/turma/peso", json={"peso": 2}, auth=ADMIN).status_code == 200
    votar(cliente, turma, "defesa")
    r = cliente.post("/api/admin/urnas/turma/peso", json={"peso": 1}, auth=ADMIN)
    assert r.status_code == 409 and "já há votos" in r.json()["detail"]
    assert db.execute("SELECT peso FROM urnas WHERE id = 'turma'").fetchone()[0] == 2
    assert "urna_peso_alterado" in [e["tipo"] for e in cliente.get("/api/admin/eventos", auth=ADMIN).json()]

def test_peso_fora_do_intervalo(cliente):
    nova_urna(cliente, "turma")
    for peso in (0, 11):
        assert cliente.post("/api/admin/urnas/turma/peso", json={"peso": peso}, auth=ADMIN).status_code == 422
        r = cliente.post("/api/admin/urnas", json={"id": f"u{peso}", "nome": "x", "peso": peso}, auth=ADMIN)
        assert r.status_code == 422

def test_pedido_aprovado_com_peso(cliente):
    p = cliente.post("/api/urnas/pedido").json()
    cliente.post(f"/api/admin/pedidos/{p['codigo']}/aprovar", json={"id": "turma", "nome": "Turma", "peso": 3}, auth=ADMIN)
    assert [u["peso"] for u in cliente.get("/api/admin/urnas", auth=ADMIN).json()] == [3]

def test_importacao_usa_o_peso_da_urna(cliente):
    nova_urna(cliente, "turma", 3)
    abrir(cliente)
    r = cliente.post("/api/admin/importar", auth=ADMIN, json={"urna_id": "turma", "votos": [novo_voto("defesa")]})
    assert r.json()["aceitos"] == 1
    assert db.execute("SELECT peso FROM votos").fetchone()[0] == 3

# ---------- celular ----------
def votar_pelo_celular(cliente, sid, opcao="sim"):
    codigo = cliente.get("/api/telao/codigo", headers=TELAO).json()["codigo"]
    cedula = cliente.post("/api/celular/entrar", json={"sessao_id": sid, "codigo": codigo}).json()["cedula"]
    voto = {"cedula": cedula, "id": novo_voto()["id"], "opcao": opcao}
    assert cliente.post("/api/celular/votar", json=voto).status_code == 200

OPCOES = [{"rotulo": "Sim", "cor": "#16a34a"}, {"rotulo": "Não", "cor": "#dc2626"}]

def test_peso_do_celular_por_sessao(cliente):
    sid = cliente.post("/api/admin/sessoes", auth=ADMIN, json={
        "tema": "Pesada", "opcoes": OPCOES, "celular": True, "peso_celular": 2}).json()["id"]
    abrir(cliente, sid)
    assert cliente.get("/api/sessao/ativa").json()["sessao"]["peso_celular"] == 2
    votar_pelo_celular(cliente, sid)
    r = cliente.post(f"/api/admin/sessoes/{sid}/peso-celular", json={"peso": 1}, auth=ADMIN)
    assert r.status_code == 409
    revelar(cliente, sid)
    assert resultado(cliente, sid)["sim"] == (1, 2)

def test_peso_do_celular_vale_para_o_questionario(cliente):
    ids = cliente.post("/api/admin/questionarios", auth=ADMIN, json={"celular": True, "perguntas": [
        {"tema": "Q1", "opcoes": OPCOES}, {"tema": "Q2", "opcoes": OPCOES}]}).json()["ids"]
    assert cliente.post(f"/api/admin/sessoes/{ids[0]}/peso-celular", json={"peso": 4}, auth=ADMIN).status_code == 200
    pesos = {s["id"]: s["peso_celular"] for s in cliente.get("/api/admin/sessoes", auth=ADMIN).json()}
    assert [pesos[i] for i in ids] == [4, 4]

def test_mudar_peso_exige_mesario(cliente):
    nova_urna(cliente, "turma")
    assert cliente.post("/api/admin/urnas/turma/peso", json={"peso": 2}).status_code == 401
    assert cliente.post("/api/admin/sessoes/1/peso-celular", json={"peso": 2}).status_code == 401
