import uuid

import pytest

import app.seguranca
from app.db import db
from app.seguranca import chave_telao, codigo_celular, janela_atual
from tests.auxiliares import ADMIN, novo_voto

TELAO = {"X-Telao-Chave": chave_telao()}

def codigo_do_telao(cliente):
    return cliente.get("/api/telao/codigo", headers=TELAO).json()["codigo"]

def entrar(cliente, codigo=None, sessao_id=1):
    codigo = codigo or codigo_do_telao(cliente)
    return cliente.post("/api/celular/entrar", json={"sessao_id": sessao_id, "codigo": codigo})

def votar(cliente, cedula, opcao="defesa", voto_id=None):
    return cliente.post("/api/celular/votar",
                        json={"cedula": cedula, "id": str(voto_id or uuid.uuid4()), "opcao": opcao})

def contar_votos():
    return db.execute("SELECT COUNT(*) FROM votos WHERE urna_id = 'celular'").fetchone()[0]

@pytest.fixture
def cedula(cliente, sessao_aberta):
    return entrar(cliente).json()["cedula"]

# ---------- voto válido ----------
def test_voto_pelo_celular(cliente, cedula):
    assert votar(cliente, cedula).status_code == 200
    assert contar_votos() == 1

def test_entrar_devolve_sessao_com_opcoes(cliente, sessao_aberta):
    r = entrar(cliente).json()
    assert [o["chave"] for o in r["sessao"]["opcoes"]] == ["acusacao", "defesa"]

def test_voto_celular_entra_no_total_e_no_resultado(cliente, urna, cedula):
    cliente.post("/api/votos", json=novo_voto("acusacao"), headers=urna)
    votar(cliente, cedula, "defesa")
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN)
    with cliente.websocket_connect("/ws/telao") as ws:
        m = ws.receive_json()
    assert m["total"] == 2
    assert {o["chave"]: o["votos"] for o in m["resultado"]} == {"acusacao": 1, "defesa": 1}

# ---------- antifraude ----------
def test_mesma_cedula_nao_vota_duas_vezes(cliente, cedula):
    votar(cliente, cedula)
    r = votar(cliente, cedula, "acusacao")
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == "ja_votou"
    assert contar_votos() == 1

def test_reenvio_do_mesmo_voto_e_aceito_sem_duplicar(cliente, cedula):
    voto_id = uuid.uuid4()
    assert votar(cliente, cedula, voto_id=voto_id).status_code == 200
    assert votar(cliente, cedula, voto_id=voto_id).status_code == 200
    assert contar_votos() == 1

def test_codigo_errado_recusa(cliente, sessao_aberta):
    r = entrar(cliente, codigo="0000000000")
    assert r.status_code == 403
    assert r.json()["detail"]["motivo"] == "codigo_expirado"

def test_codigo_da_janela_anterior_ainda_vale(cliente, sessao_aberta):
    assert entrar(cliente, codigo_celular(1, janela_atual() - 1)).status_code == 200

def test_codigo_antigo_expira(cliente, sessao_aberta, monkeypatch):
    codigo = codigo_do_telao(cliente)
    janela = janela_atual()
    monkeypatch.setattr(app.seguranca, "janela_atual", lambda: janela + 2)
    assert entrar(cliente, codigo).status_code == 403

def test_codigo_de_outra_sessao_nao_vale(cliente, sessao_aberta):
    assert entrar(cliente, codigo_celular(2, janela_atual())).status_code == 403

def test_cedula_inventada_recusa(cliente, sessao_aberta):
    assert votar(cliente, "inventada").status_code == 401

def test_id_de_voto_existente_nao_queima_cedula(cliente, urna, cedula):
    voto = novo_voto()
    cliente.post("/api/votos", json=voto, headers=urna)
    assert votar(cliente, cedula, voto_id=voto["id"]).status_code == 409
    assert votar(cliente, cedula).status_code == 200

# ---------- estado da sessão ----------
def test_entrar_fora_de_aberta_recusa(cliente):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    r = entrar(cliente, codigo_celular(1, janela_atual()))
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == "sessao_fechada"

def test_votar_depois_de_encerrar_recusa(cliente, cedula):
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    r = votar(cliente, cedula)
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == "sessao_fechada"
    assert contar_votos() == 0

def test_telao_sem_codigo_fora_de_aberta(cliente):
    assert cliente.get("/api/telao/codigo", headers=TELAO).json()["codigo"] is None

def test_opcao_invalida(cliente, cedula):
    assert votar(cliente, cedula, "culpado").status_code == 400

# ---------- acesso ----------
def test_codigo_exige_chave_do_telao(cliente, sessao_aberta):
    assert cliente.get("/api/telao/codigo").status_code == 401
    assert cliente.get("/api/telao/codigo", headers={"X-Telao-Chave": "errada"}).status_code == 401

def test_chave_do_telao_so_para_mesario(cliente):
    assert cliente.get("/api/admin/telao").status_code == 401
    assert cliente.get("/api/admin/telao", auth=ADMIN).json()["chave"] == chave_telao()

def test_id_celular_reservado(cliente):
    r = cliente.post("/api/admin/urnas", json={"id": "celular", "nome": "x"}, auth=ADMIN)
    assert r.status_code == 409

def test_zerar_libera_cedulas(cliente, cedula):
    votar(cliente, cedula)
    cliente.post("/api/admin/sessoes/1/zerar", json={"confirmacao": "Sessão de teste"}, auth=ADMIN)
    assert db.execute("SELECT COUNT(*) FROM cedulas").fetchone()[0] == 0
