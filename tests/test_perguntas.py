import pytest

from app.seguranca import chave_telao
from tests.auxiliares import ADMIN, novo_voto

OPCOES = [{"rotulo": "Sim", "cor": "#16a34a"}, {"rotulo": "Não", "cor": "#dc2626"}]

def questionario(cliente, *temas):
    perguntas = [{"tema": t, "opcoes": OPCOES} for t in temas]
    return cliente.post("/api/admin/questionarios", json={"perguntas": perguntas}, auth=ADMIN)

def ativar(cliente, sid):
    return cliente.post(f"/api/admin/sessoes/{sid}/ativar", auth=ADMIN)

def avancar(cliente, sid):
    return cliente.post(f"/api/admin/sessoes/{sid}/avancar", params={"forcar": "true"}, auth=ADMIN)

def votar(cliente, urna, sid, opcao="sim", voto=None):
    voto = voto or novo_voto(opcao)
    return cliente.post("/api/votos", json={**voto, "sessao_id": sid, "opcao": opcao}, headers=urna)

def resultado(cliente, sid):
    r = cliente.get(f"/api/auditoria/sessoes/{sid}")
    return {o["chave"]: o["votos"] for o in r.json()["resultado"]} if r.status_code == 200 else None

@pytest.fixture
def perguntas(cliente):
    return questionario(cliente, "Pergunta A", "Pergunta B", "Pergunta C").json()["ids"]

def revelar(cliente, sid):
    avancar(cliente, sid)  # ENCERRADA
    avancar(cliente, sid)  # REVELADA

# ---------- criação ----------
def test_cria_perguntas_encadeadas_em_ordem(cliente, perguntas):
    sessoes = {s["id"]: s for s in cliente.get("/api/admin/sessoes", auth=ADMIN).json()}
    a, b, c = (sessoes[i] for i in perguntas)
    assert [a["pergunta"], b["pergunta"], c["pergunta"]] == [1, 2, 3]
    assert a["grupo_id"] == b["grupo_id"] == c["grupo_id"] == perguntas[0]
    assert a["total_perguntas"] == 3
    assert a["proxima_pergunta"] == b["id"] and c["proxima_pergunta"] is None

def test_questionario_precisa_de_duas_perguntas(cliente):
    assert questionario(cliente, "Só uma").status_code == 422

def test_perguntas_repetidas_recusadas(cliente):
    assert questionario(cliente, "Igual", "igual").status_code == 400

def test_tema_ja_existente_recusado(cliente):
    assert questionario(cliente, "Sessão de teste", "Nova").status_code == 409

def test_sessao_avulsa_continua_igual(cliente):
    ativar(cliente, 1)
    s = cliente.get("/api/sessao/ativa").json()["sessao"]
    assert (s["pergunta"], s["total_perguntas"], s["grupo_id"], s["proxima_pergunta"]) == (1, 1, None, None)

# ---------- liberação pelo mesário ----------
def test_so_libera_proxima_depois_de_revelar_a_anterior(cliente, urna, perguntas):
    a, b, _ = perguntas
    assert ativar(cliente, b).status_code == 409
    ativar(cliente, a)
    avancar(cliente, a)
    assert ativar(cliente, b).status_code == 409   # A só aberta
    avancar(cliente, a)
    assert ativar(cliente, b).status_code == 409   # A só encerrada
    avancar(cliente, a)
    assert ativar(cliente, b).status_code == 200   # A revelada

def test_lista_indica_pergunta_liberada(cliente, perguntas):
    a, b, _ = perguntas
    liberadas = lambda: {s["id"]: s["liberada"] for s in cliente.get("/api/admin/sessoes", auth=ADMIN).json()}
    assert liberadas()[a] and not liberadas()[b]
    ativar(cliente, a)
    avancar(cliente, a)
    revelar(cliente, a)
    assert liberadas()[b]

def test_sessao_ativa_mostra_posicao(cliente, perguntas):
    ativar(cliente, perguntas[0])
    s = cliente.get("/api/sessao/ativa").json()["sessao"]
    assert (s["pergunta"], s["total_perguntas"], s["proxima_pergunta"]) == (1, 3, perguntas[1])

# ---------- votos por pergunta ----------
def test_fluxo_completo_com_resultado_por_pergunta(cliente, urna, perguntas):
    a, b, c = perguntas
    for sid, votos in ((a, ["sim", "sim", "nao"]), (b, ["nao"]), (c, ["sim", "nao", "nao"])):
        ativar(cliente, sid)
        avancar(cliente, sid)
        for opcao in votos:
            assert votar(cliente, urna, sid, opcao).status_code == 200
        revelar(cliente, sid)
    assert resultado(cliente, a) == {"sim": 2, "nao": 1}
    assert resultado(cliente, b) == {"sim": 0, "nao": 1}
    assert resultado(cliente, c) == {"sim": 1, "nao": 2}

def test_voto_na_pergunta_anterior_recusado(cliente, urna, perguntas):
    a, b, _ = perguntas
    ativar(cliente, a)
    avancar(cliente, a)
    revelar(cliente, a)
    ativar(cliente, b)
    avancar(cliente, b)
    r = votar(cliente, urna, a)
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "sessao_encerrada"

def test_reenvio_idempotente_por_pergunta(cliente, urna, perguntas):
    a = perguntas[0]
    ativar(cliente, a)
    avancar(cliente, a)
    voto = novo_voto("sim")
    votar(cliente, urna, a, voto=voto)
    votar(cliente, urna, a, voto=voto)
    revelar(cliente, a)
    assert resultado(cliente, a) == {"sim": 1, "nao": 0}

def test_revelacao_uma_pergunta_por_vez(cliente, urna, perguntas):
    a, b, _ = perguntas
    ativar(cliente, a)
    avancar(cliente, a)
    votar(cliente, urna, a)
    revelar(cliente, a)
    ativar(cliente, b)
    avancar(cliente, b)
    votar(cliente, urna, b)
    assert resultado(cliente, a) is not None
    assert resultado(cliente, b) is None
    with cliente.websocket_connect("/ws/telao") as ws:
        m = ws.receive_json()
    assert m["sessao"]["id"] == b and "resultado" not in m

def test_csv_exporta_so_a_pergunta_pedida(cliente, urna, perguntas):
    a, b, _ = perguntas
    ativar(cliente, a)
    avancar(cliente, a)
    votar(cliente, urna, a, "sim")
    revelar(cliente, a)
    ativar(cliente, b)
    avancar(cliente, b)
    votar(cliente, urna, b, "nao")
    revelar(cliente, b)
    linhas = cliente.get(f"/api/admin/sessoes/{b}/votos.csv", auth=ADMIN).text.strip().splitlines()
    assert len(linhas) == 2 and linhas[1].split(",")[2] == "nao"

# ---------- celular ----------
TELAO = {"X-Telao-Chave": chave_telao()}

def entrar_celular(cliente, sid):
    codigo = cliente.get("/api/telao/codigo", headers=TELAO).json()["codigo"]
    return cliente.post("/api/celular/entrar", json={"sessao_id": sid, "codigo": codigo}).json()["cedula"]

def proxima(cliente, cedula):
    return cliente.post("/api/celular/proxima", json={"cedula": cedula})

@pytest.fixture
def celular_na_segunda(cliente, perguntas):
    """Celular que votou na pergunta A, com a B já aberta."""
    a, b, _ = perguntas
    ativar(cliente, a)
    avancar(cliente, a)
    cedula = entrar_celular(cliente, a)
    cliente.post("/api/celular/votar", json={"cedula": cedula, "id": novo_voto()["id"], "opcao": "sim"})
    revelar(cliente, a)
    ativar(cliente, b)
    avancar(cliente, b)
    return cedula

def test_celular_segue_para_a_proxima_sem_novo_qr(cliente, perguntas, celular_na_segunda):
    r = proxima(cliente, celular_na_segunda)
    assert r.status_code == 200 and r.json()["sessao"]["id"] == perguntas[1]
    voto = {"cedula": r.json()["cedula"], "id": novo_voto()["id"], "opcao": "nao"}
    assert cliente.post("/api/celular/votar", json=voto).status_code == 200

def test_cedula_gera_uma_unica_seguinte(cliente, celular_na_segunda):
    assert proxima(cliente, celular_na_segunda).status_code == 200
    r = proxima(cliente, celular_na_segunda)
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "cedula_usada"

def test_sem_proxima_com_a_pergunta_fechada(cliente, perguntas):
    a, b, _ = perguntas
    ativar(cliente, a)
    avancar(cliente, a)
    cedula = entrar_celular(cliente, a)
    assert proxima(cliente, cedula).json()["detail"]["motivo"] == "sem_proxima"  # ainda na A
    revelar(cliente, a)
    ativar(cliente, b)
    r = proxima(cliente, cedula)  # B aguardando
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "sessao_fechada"

def test_cedula_de_sessao_avulsa_nao_segue(cliente, sessao_aberta, perguntas):
    cedula = entrar_celular(cliente, 1)
    revelar(cliente, 1)
    ativar(cliente, perguntas[0])
    avancar(cliente, perguntas[0])
    assert proxima(cliente, cedula).json()["detail"]["motivo"] == "sem_proxima"

def test_cedula_inventada(cliente):
    assert proxima(cliente, "inventada").status_code == 401

# ---------- auditoria ----------
def test_auditoria_mostra_posicao_da_pergunta(cliente, urna, perguntas):
    a = perguntas[0]
    ativar(cliente, a)
    avancar(cliente, a)
    revelar(cliente, a)
    [item] = cliente.get("/api/auditoria/sessoes").json()
    assert (item["id"], item["pergunta"], item["total_perguntas"]) == (a, 1, 3)
    detalhe = cliente.get(f"/api/auditoria/sessoes/{a}").json()
    assert (detalhe["pergunta"], detalhe["total_perguntas"]) == (1, 3)
