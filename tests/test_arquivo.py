from app.db import db
from tests.auxiliares import ADMIN, novo_voto

def listar(cliente, **params):
    return cliente.get("/api/admin/sessoes", params=params, auth=ADMIN).json()

def arquivar(cliente, sid=1):
    return cliente.post(f"/api/admin/sessoes/{sid}/arquivar", auth=ADMIN)

def test_arquivada_some_da_lista_padrao(cliente):
    assert arquivar(cliente).status_code == 200
    assert listar(cliente) == []
    [s] = listar(cliente, arquivadas=True)
    assert s["arquivada"] is True

def test_desarquivar_volta_para_lista(cliente):
    arquivar(cliente)
    assert cliente.post("/api/admin/sessoes/1/desarquivar", auth=ADMIN).status_code == 200
    [s] = listar(cliente)
    assert s["arquivada"] is False

def test_arquivar_mantem_votos(cliente, urna, sessao_aberta):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    with db:
        db.execute("UPDATE sessoes SET ativa = 0")
    arquivar(cliente)
    assert db.execute("SELECT COUNT(*) FROM votos WHERE sessao_id = 1").fetchone()[0] == 1

def test_sessao_ativa_nao_arquiva(cliente):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    assert arquivar(cliente).status_code == 409

def test_arquivada_nao_ativa(cliente):
    arquivar(cliente)
    assert cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN).status_code == 409
