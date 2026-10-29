from app.db import db
from tests.auxiliares import ADMIN, novo_voto

TEMA = "Sessão de teste"

def zerar(cliente, confirmacao=TEMA, sid=1):
    return cliente.post(f"/api/admin/sessoes/{sid}/zerar", json={"confirmacao": confirmacao}, auth=ADMIN)

def votar(cliente, urna, n=3):
    for _ in range(n):
        cliente.post("/api/votos", json=novo_voto(), headers=urna)

def contar_votos():
    return db.execute("SELECT COUNT(*) FROM votos WHERE sessao_id = 1").fetchone()[0]

def test_zerar_apaga_votos_e_mantem_sessao(cliente, urna, sessao_aberta):
    votar(cliente, urna)
    r = zerar(cliente)
    assert r.json() == {"apagados": 3}
    assert contar_votos() == 0
    assert db.execute("SELECT COUNT(*) FROM opcoes WHERE sessao_id = 1").fetchone()[0] == 2

    assert cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN).json()["estado"] == "ABERTA"
    votar(cliente, urna, 1)
    assert contar_votos() == 1

def test_zerar_registra_auditoria(cliente, urna, sessao_aberta):
    votar(cliente, urna)
    zerar(cliente)
    ultimo = cliente.get("/api/admin/eventos", auth=ADMIN).json()[-1]
    assert ultimo["tipo"] == "sessao_zerada"
    assert "votos=3" in ultimo["detalhe"]
    assert "por=admin" in ultimo["detalhe"]

def test_confirmacao_errada_nao_zera(cliente, urna, sessao_aberta):
    votar(cliente, urna)
    assert zerar(cliente, "sim").status_code == 400
    assert contar_votos() == 3

def test_confirmacao_ignora_maiusculas_e_espacos(cliente, urna, sessao_aberta):
    assert zerar(cliente, "  sessão DE TESTE ").status_code == 200

def test_revelada_nao_zera(cliente, urna, sessao_aberta):
    votar(cliente, urna)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN)
    assert zerar(cliente).status_code == 409
    assert contar_votos() == 3

def test_zerar_exige_mesario(cliente):
    assert cliente.post("/api/admin/sessoes/1/zerar", json={"confirmacao": TEMA}).status_code == 401
