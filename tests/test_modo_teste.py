"""Modo teste: ensaiar em produção e apagar tudo depois, sem tocar no que é real."""
from app.db import db
from tests.auxiliares import ADMIN, novo_voto

OPCOES = [{"rotulo": "Sim", "cor": "#16a34a"}, {"rotulo": "Não", "cor": "#dc2626"}]

def foto():
    """Conteúdo de todas as tabelas, para comparar antes e depois da limpeza."""
    tabelas = ("sessoes", "opcoes", "urnas", "votos", "eventos", "cedulas")
    return {t: [tuple(l) for l in db.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tabelas}

def abrir(cliente, sid):
    cliente.post(f"/api/admin/sessoes/{sid}/ativar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)

def nova_urna(cliente, uid, teste=False):
    r = cliente.post("/api/admin/urnas", json={"id": uid, "nome": uid, "teste": teste}, auth=ADMIN)
    return {"X-Urna-Token": r.json()["token"]}

def revelar(cliente, sid):
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar?forcar=true", auth=ADMIN)

def test_limpar_testes_deixa_o_banco_como_antes(cliente):
    # cenário real: sessão revelada com votos de uma urna de verdade
    real = nova_urna(cliente, "real")
    abrir(cliente, 1)
    cliente.post("/api/votos", json=novo_voto(opcao="defesa"), headers=real)
    revelar(cliente, 1)
    antes = foto()

    # ensaio: questionário e sessão de teste, urna de teste e a urna real votando no teste
    q = cliente.post("/api/admin/questionarios", auth=ADMIN, json={"teste": True, "perguntas": [
        {"tema": "Ensaio 1", "opcoes": OPCOES}, {"tema": "Ensaio 2", "opcoes": OPCOES}]}).json()["ids"]
    sid = cliente.post("/api/admin/sessoes", auth=ADMIN,
                       json={"tema": "Ensaio avulso", "opcoes": OPCOES, "teste": True}).json()["id"]
    de_teste = nova_urna(cliente, "ensaio", teste=True)
    abrir(cliente, sid)
    for urna in (de_teste, real, de_teste):
        assert cliente.post("/api/votos", json=novo_voto(opcao="sim", sessao_id=sid), headers=urna).status_code == 200
    revelar(cliente, sid)
    abrir(cliente, q[0])
    cliente.post("/api/admin/importar", auth=ADMIN, json={"urna_id": "ensaio", "votos": []})

    r = cliente.post("/api/admin/testes/limpar", auth=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"sessoes": 3, "urnas": 1, "votos": 3, "eventos": r.json()["eventos"]}
    assert r.json()["eventos"] > 5
    assert foto() == antes
    # a sessão real que estava ativa antes do ensaio volta a ser a ativa
    assert cliente.get("/api/sessao/ativa").json()["sessao"]["id"] == 1

def test_sessao_de_teste_fora_da_auditoria_publica(cliente):
    sid = cliente.post("/api/admin/sessoes", auth=ADMIN,
                       json={"tema": "Ensaio", "opcoes": OPCOES, "teste": True}).json()["id"]
    abrir(cliente, sid)
    revelar(cliente, sid)
    assert cliente.get("/api/auditoria/sessoes").json() == []
    assert cliente.get(f"/api/auditoria/sessoes/{sid}").status_code == 404

def test_telas_e_painel_sabem_o_que_e_teste(cliente):
    sid = cliente.post("/api/admin/sessoes", auth=ADMIN,
                       json={"tema": "Ensaio", "opcoes": OPCOES, "teste": True}).json()["id"]
    nova_urna(cliente, "ensaio", teste=True)
    abrir(cliente, sid)
    assert cliente.get("/api/sessao/ativa").json()["sessao"]["teste"] is True
    marcadas = {s["id"]: s["teste"] for s in cliente.get("/api/admin/sessoes", auth=ADMIN).json()}
    assert marcadas == {1: False, sid: True}
    assert [u["teste"] for u in cliente.get("/api/admin/urnas", auth=ADMIN).json()] == [True]

def test_urna_de_teste_nao_vota_em_sessao_real(cliente):
    de_teste = nova_urna(cliente, "ensaio", teste=True)
    abrir(cliente, 1)
    r = cliente.post("/api/votos", json=novo_voto(), headers={**de_teste, "Accept-Language": "en"})
    assert r.status_code == 409
    assert r.json()["detail"] == {"motivo": "urna_de_teste",
                                  "mensagem": "A test ballot box cannot vote in a real session"}

def test_limpar_sem_testes_nao_muda_nada(cliente):
    abrir(cliente, 1)
    antes = foto()
    assert cliente.post("/api/admin/testes/limpar", auth=ADMIN).json() == {
        "sessoes": 0, "urnas": 0, "votos": 0, "eventos": 0}
    assert foto() == antes

def test_limpar_exige_senha(cliente):
    assert cliente.post("/api/admin/testes/limpar").status_code == 401
