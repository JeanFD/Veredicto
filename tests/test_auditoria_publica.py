import pytest

from tests.auxiliares import ADMIN, novo_voto

def avancar(cliente, **params):
    return cliente.post("/api/admin/sessoes/1/avancar", params=params, auth=ADMIN)

def votar(cliente, urna, *opcoes):
    for opcao in opcoes:
        cliente.post("/api/votos", json=novo_voto(opcao), headers=urna)

@pytest.fixture
def revelada(cliente, urna, sessao_aberta):
    """Sessão com histórico completo: zerada uma vez e revelada à força."""
    votar(cliente, urna, "defesa", "defesa", "acusacao")
    cliente.post("/api/admin/sessoes/1/zerar", json={"confirmacao": "Sessão de teste"}, auth=ADMIN)
    avancar(cliente)                      # ABERTA de novo após zerar
    votar(cliente, urna, "defesa", "defesa")
    avancar(cliente)                      # ENCERRADA
    avancar(cliente, forcar="true")       # REVELADA
    return 1

# ---------- antes da revelação ----------
@pytest.mark.parametrize("estado", ["AGUARDANDO", "ABERTA", "ENCERRADA"])
def test_nada_antes_de_revelar(cliente, urna, estado):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    if estado != "AGUARDANDO":
        avancar(cliente)
        cliente.post("/api/votos", json=novo_voto(), headers=urna)
    if estado == "ENCERRADA":
        avancar(cliente)

    assert cliente.get("/api/auditoria/sessoes").json() == []
    r = cliente.get("/api/auditoria/sessoes/1")
    assert r.status_code == 404
    assert r.json() == cliente.get("/api/auditoria/sessoes/999").json()
    assert "votos" not in r.text and "total" not in r.text

# ---------- depois da revelação ----------
def test_lista_sessoes_reveladas(cliente, revelada):
    assert cliente.get("/api/auditoria/sessoes").json() == [
        {"id": 1, "tema": "Sessão de teste", "pergunta": 1, "total_perguntas": 1},
    ]

def test_total_por_urna_sem_divisao_por_opcao(cliente, revelada):
    a = cliente.get("/api/auditoria/sessoes/1").json()
    assert a["total"] == 2
    assert {o["chave"]: o["votos"] for o in a["resultado"]} == {"acusacao": 0, "defesa": 2}
    [urna] = a["por_urna"]
    assert urna["urna"] == "Teste" and urna["votos"] == 2
    assert set(urna) == {"urna", "votos", "primeiro_voto", "ultimo_voto"}

def test_linha_do_tempo_publica_sem_ip(cliente, revelada):
    r = cliente.get("/api/auditoria/sessoes/1")
    eventos = [e["evento"] for e in r.json()["eventos"]]
    assert eventos == [
        "Sessão ativada",
        "Contagem zerada (3 votos apagados)",
        "Estado alterado para ABERTA",
        "Estado alterado para ENCERRADA",
        "Revelação forçada com pendências nas urnas",
        "Estado alterado para REVELADA",
    ]
    assert "testclient" not in r.text and "mesario@" not in r.text

def test_nao_expoe_tokens_nem_eventos_de_urna(cliente, revelada):
    r = cliente.get("/api/auditoria/sessoes/1")
    assert "token" not in r.text
    assert "urna_cadastrada" not in r.text

def test_votos_por_celular_aparecem_com_nome(cliente, sessao_aberta):
    from app.seguranca import chave_telao
    codigo = cliente.get("/api/telao/codigo", headers={"X-Telao-Chave": chave_telao()}).json()["codigo"]
    cedula = cliente.post("/api/celular/entrar", json={"sessao_id": 1, "codigo": codigo}).json()["cedula"]
    cliente.post("/api/celular/votar", json={"cedula": cedula, "id": novo_voto()["id"], "opcao": "defesa"})
    avancar(cliente)
    avancar(cliente)
    [urna] = cliente.get("/api/auditoria/sessoes/1").json()["por_urna"]
    assert urna["urna"] == "Voto por celular"
