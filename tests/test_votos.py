from app.db import db
from tests.auxiliares import ADMIN, novo_voto

def contar_votos():
    return db.execute("SELECT COUNT(*) FROM votos").fetchone()[0]

def test_voto_repetido_conta_uma_vez(cliente,urna, sessao_aberta):
    voto = novo_voto()
    for _ in range(3):
        assert cliente.post("/api/votos", json=voto, headers=urna).status_code == 200
    assert contar_votos() == 1

def test_sessao_fechada_recusa(cliente, urna):
    assert cliente.post("/api/votos", json=novo_voto(), headers=urna).status_code == 409

def test_opcao_invalida_recusa(cliente, urna, sessao_aberta):
    r = cliente.post("/api/votos", json=novo_voto("culpado"), headers=urna)
    assert r.status_code == 400

def test_token_invalido_recusa(cliente, sessao_aberta):
    r = cliente.post("/api/votos", json=novo_voto(), headers={"X-Urna-Token": "falso"})
    assert r.status_code == 401

def test_urna_desativada_recusa(cliente, urna, sessao_aberta):
    cliente.post("/api/admin/urnas/urna-teste/desativar", auth=ADMIN)
    assert cliente.post("/api/votos", json=novo_voto(), headers=urna).status_code == 401

def test_voto_gravado_com_urna_do_token(cliente, urna,sessao_aberta):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    assert db.execute("SELECT urna_id FROM votos").fetchone()[0] == "urna-teste"

def test_token_aparece_so_no_cadastro(cliente):
    r = cliente.post("/api/admin/urnas", json={"id": "urna-x", "nome": "x"}, auth=ADMIN)
    token = r.json()["token"]
    guardado = db.execute("SELECT token_hash FROM urnas WHERE id = 'urna-x'").fetchone()[0]
    assert guardado != token
    