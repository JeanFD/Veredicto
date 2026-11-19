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
    [sessao] = cliente.get("/api/auditoria/sessoes").json()
    assert sessao["id"] == 1 and sessao["tema"] == "Sessão de teste"
    assert (sessao["pergunta"], sessao["total_perguntas"]) == (1, 1)
    # caso e data: sem eles a lista vira uma pilha de perguntas sem referência
    assert sessao["caso"] == "Ensaio" and sessao["grupo_id"] is None
    assert sessao["encerrada_em"]

def test_total_por_urna_sem_divisao_por_opcao(cliente, revelada):
    a = cliente.get("/api/auditoria/sessoes/1").json()
    assert a["total"] == 2
    assert {o["chave"]: o["votos"] for o in a["resultado"]} == {"acusacao": 0, "defesa": 2}
    [urna] = a["por_urna"]
    assert urna["urna"] == "Teste" and urna["votos"] == 2
    assert set(urna) == {"urna", "votos", "pontos", "peso", "primeiro_voto", "ultimo_voto"}

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

def test_quem_fez_cada_coisa_so_para_quem_entrou(cliente, revelada):
    """A auditoria é pública; o nome de quem operou é da mesa, não da rua."""
    publico = cliente.get("/api/auditoria/sessoes/1").json()["eventos"]
    assert publico and all("por" not in e for e in publico), publico

    com_conta = cliente.get("/api/auditoria/sessoes/1", auth=ADMIN).json()["eventos"]
    assert all(e["por"] == "admin" for e in com_conta), com_conta

def test_senha_errada_na_auditoria_nao_tranca_o_ip(cliente, revelada):
    """A página é pública: errar a senha aqui não pode bloquear o login de todo mundo."""
    for _ in range(10):
        r = cliente.get("/api/auditoria/sessoes/1", auth=("admin", "errada"))
        assert r.status_code == 200
        assert all("por" not in e for e in r.json()["eventos"])
    assert cliente.post("/api/login", json={"usuario": ADMIN[0], "senha": ADMIN[1]}).status_code == 200
