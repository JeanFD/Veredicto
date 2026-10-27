from tests.auxiliares import ADMIN, novo_voto

def cadastrar(cliente, uid="u1"):
    return cliente.post("/api/admin/urnas", json={"id": uid, "nome": "U"}, auth=ADMIN).json()["token"]

def test_listagem_e_auditoria_nao_expoem_token(cliente):
    token = cadastrar(cliente)
    cliente.post("/api/urnas/heartbeat", json={"pendentes": 0}, headers={"X-Urna-Token": token})
    for rota in ("/api/admin/urnas", "/api/admin/eventos", "/api/admin/sessoes"):
        r = cliente.get(rota, auth=ADMIN)
        assert token not in r.text
        assert "token" not in r.text

def test_novo_token_invalida_o_antigo(cliente, sessao_aberta):
    antigo = cadastrar(cliente)
    r = cliente.post("/api/admin/urnas/u1/novo-token", auth=ADMIN)
    novo = r.json()["token"]
    assert novo != antigo
    assert cliente.post("/api/votos", json=novo_voto(), headers={"X-Urna-Token": antigo}).status_code == 401
    assert cliente.post("/api/votos", json=novo_voto(), headers={"X-Urna-Token": novo}).status_code == 200

def test_novo_token_registra_auditoria(cliente):
    cadastrar(cliente)
    cliente.post("/api/admin/urnas/u1/novo-token", auth=ADMIN)
    assert cliente.get("/api/admin/eventos", auth=ADMIN).json()[-1]["tipo"] == "urna_token_reemitido"

def test_novo_token_recusa_urna_desativada_ou_inexistente(cliente):
    cadastrar(cliente)
    cliente.post("/api/admin/urnas/u1/desativar", auth=ADMIN)
    assert cliente.post("/api/admin/urnas/u1/novo-token", auth=ADMIN).status_code == 409
    assert cliente.post("/api/admin/urnas/nao-existe/novo-token", auth=ADMIN).status_code == 404

def test_novo_token_exige_mesario(cliente):
    cadastrar(cliente)
    assert cliente.post("/api/admin/urnas/u1/novo-token").status_code == 401
