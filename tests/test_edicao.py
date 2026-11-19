"""Editar uma sessão já criada: tudo muda enquanto ela não abriu; depois, só o texto."""
from app.db import db
from tests.auxiliares import ADMIN, novo_voto

OPCOES = [{"rotulo": "Acusação", "cor": "#dc2626"}, {"rotulo": "Defesa", "cor": "#2563eb"}]

def criar(cliente, tema="Edição", caso=""):
    return cliente.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "caso": caso},
                        auth=ADMIN).json()["id"]

def questionario(cliente, n=3, caso="Júri"):
    perguntas = [{"tema": f"Pergunta {i}", "opcoes": OPCOES} for i in range(1, n + 1)]
    return cliente.post("/api/admin/questionarios", json={"caso": caso, "perguntas": perguntas},
                        auth=ADMIN).json()["ids"]

def edicao(cliente, sid):
    return cliente.get(f"/api/admin/sessoes/{sid}/edicao", auth=ADMIN).json()

def editar(cliente, sid, corpo):
    return cliente.put(f"/api/admin/sessoes/{sid}", json=corpo, auth=ADMIN)

def sem_chave(opcoes):
    return [{"rotulo": o["rotulo"], "cor": o["cor"]} for o in opcoes]

def abrir_com_voto(cliente, sid, urna, opcao="defesa"):
    cliente.post(f"/api/admin/sessoes/{sid}/ativar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)
    assert cliente.post("/api/votos", json=novo_voto(opcao, sessao_id=sid), headers=urna).status_code == 200

def eventos(tipo):
    return [r[0] for r in db.execute("SELECT detalhe FROM eventos WHERE tipo = ? ORDER BY id", (tipo,))]

def test_aguardando_edita_tema_caso_e_opcoes(cliente):
    sid = criar(cliente)
    r = editar(cliente, sid, {"caso": "Novo caso", "perguntas": [{"id": sid, "tema": "Tema novo", "opcoes": [
        {"rotulo": "Culpado", "cor": "#111111"}, {"rotulo": "Inocente", "cor": "#222222"},
        {"rotulo": "Abstenção", "cor": "#333333"}]}]})
    assert r.status_code == 200, r.text
    dados = edicao(cliente, sid)
    assert dados["caso"] == "Novo caso"
    assert dados["estrutura_livre"] is True
    p = dados["perguntas"][0]
    assert p["tema"] == "Tema novo" and p["livre"] is True
    assert [(o["chave"], o["rotulo"], o["cor"]) for o in p["opcoes"]] == [
        ("culpado", "Culpado", "#111111"), ("inocente", "Inocente", "#222222"), ("abstencao", "Abstenção", "#333333")]
    assert eventos("sessao_editada") == [f"sessao={sid} mudou=tema,caso,opcoes por=admin"]

def test_sem_mudanca_nao_registra_nada(cliente):
    sid = criar(cliente)
    p = edicao(cliente, sid)["perguntas"][0]
    r = editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": p["tema"], "opcoes": p["opcoes"]}]})
    assert r.json()["editadas"] == 0
    assert eventos("sessao_editada") == []

def test_aberta_recusa_mudar_opcoes(cliente, urna):
    sid = criar(cliente)
    abrir_com_voto(cliente, sid, urna)
    p = edicao(cliente, sid)["perguntas"][0]
    assert p["livre"] is False and p["votos"] == 1
    for opcoes in (
        [{"rotulo": "Acusação", "cor": "#dc2626"}, {"rotulo": "Réu", "cor": "#2563eb"}],      # rótulo
        [{"rotulo": "Acusação", "cor": "#dc2626"}, {"rotulo": "Defesa", "cor": "#000000"}],   # cor
        OPCOES + [{"rotulo": "Abstenção", "cor": "#999999"}],                                  # mais uma
    ):
        r = editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": "Edição", "opcoes": opcoes}]})
        assert r.status_code == 409
        assert "opções" in r.json()["detail"]
    assert sem_chave(edicao(cliente, sid)["perguntas"][0]["opcoes"]) == OPCOES

def test_aberta_muda_so_o_texto_e_vai_para_a_auditoria(cliente, urna):
    sid = criar(cliente)
    abrir_com_voto(cliente, sid, urna)
    r = editar(cliente, sid, {"caso": "Caso X", "perguntas": [{"id": sid, "tema": "Edição corrigida", "opcoes": OPCOES}]})
    assert r.status_code == 200, r.text
    # o voto continua apontando para a mesma opção
    assert db.execute("SELECT opcao_chave FROM votos WHERE sessao_id = ?", (sid,)).fetchone()[0] == "defesa"
    assert eventos("sessao_editada") == [f"sessao={sid} mudou=tema,caso apos_abrir=1 por=admin"]
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar?forcar=true", auth=ADMIN)
    publico = [e["evento"] for e in cliente.get(f"/api/auditoria/sessoes/{sid}").json()["eventos"]]
    assert "Texto alterado pelo mesário depois da abertura (tema, caso)" in publico

def test_edicao_antes_de_abrir_nao_vai_para_a_auditoria(cliente):
    sid = criar(cliente)
    editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": "Outro", "opcoes": OPCOES}]})
    with db:
        db.execute("UPDATE sessoes SET estado = 'REVELADA' WHERE id = ?", (sid,))
    publico = [e["evento"] for e in cliente.get(f"/api/auditoria/sessoes/{sid}").json()["eventos"]]
    assert not any("Texto alterado" in e for e in publico)

def test_tema_de_outra_sessao_recusa(cliente):
    criar(cliente, tema="Ocupado")
    sid = criar(cliente)
    r = editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": " ocupado ", "opcoes": OPCOES}]})
    assert r.status_code == 409

def test_questionario_inclui_tira_e_reordena_enquanto_ninguem_abriu(cliente):
    ids = questionario(cliente)
    perguntas = [{"id": ids[2], "tema": "Pergunta 3", "opcoes": OPCOES},
                 {"id": ids[0], "tema": "Pergunta 1", "opcoes": OPCOES},
                 {"tema": "Pergunta nova", "opcoes": OPCOES}]
    r = editar(cliente, ids[1], {"caso": "Júri", "perguntas": perguntas})
    assert r.status_code == 200, r.text
    assert r.json() | {"ids": None} == {"ids": None, "editadas": 2, "criadas": 1, "removidas": 1}
    dados = edicao(cliente, ids[0])
    assert [p["tema"] for p in dados["perguntas"]] == ["Pergunta 3", "Pergunta 1", "Pergunta nova"]
    lista = {s["tema"]: s for s in cliente.get("/api/admin/sessoes", auth=ADMIN).json()}
    assert lista["Pergunta 3"]["pergunta"] == 1 and lista["Pergunta nova"]["total_perguntas"] == 3
    assert "Pergunta 2" not in lista
    assert len(eventos("sessao_criada")) == 4 and len(eventos("sessao_apagada")) == 1

def test_questionario_que_perde_a_primeira_pergunta_continua_um_grupo(cliente):
    ids = questionario(cliente, n=3)
    r = editar(cliente, ids[1], {"caso": "Júri", "perguntas": [
        {"id": ids[1], "tema": "Pergunta 2", "opcoes": OPCOES}, {"id": ids[2], "tema": "Pergunta 3", "opcoes": OPCOES}]})
    assert r.status_code == 200, r.text
    grupos = {r[0] for r in db.execute(f"SELECT grupo_id FROM sessoes WHERE id IN ({ids[1]}, {ids[2]})")}
    assert grupos == {ids[1]}

def test_sessao_avulsa_vira_questionario_e_volta(cliente):
    sid = criar(cliente)
    r = editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": "Edição", "opcoes": OPCOES},
                                                       {"tema": "Segunda", "opcoes": OPCOES}]})
    nova = r.json()["ids"][1]
    assert edicao(cliente, sid)["perguntas"][1]["id"] == nova
    editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": "Edição", "opcoes": OPCOES}]})
    assert db.execute("SELECT grupo_id FROM sessoes WHERE id = ?", (sid,)).fetchone()[0] is None

def test_questionario_comecado_trava_a_estrutura_mas_nao_as_proximas(cliente, urna):
    ids = questionario(cliente, n=2)
    abrir_com_voto(cliente, ids[0], urna)
    dados = edicao(cliente, ids[0])
    assert dados["estrutura_livre"] is False
    assert [p["livre"] for p in dados["perguntas"]] == [False, True]
    # incluir ou tirar pergunta: recusado
    r = editar(cliente, ids[0], {"caso": "Júri", "perguntas": [{"id": ids[0], "tema": "Pergunta 1", "opcoes": OPCOES}]})
    assert r.status_code == 409
    # a pergunta 2 ainda não abriu: as opções dela mudam
    outras = [{"rotulo": "Sim", "cor": "#00aa00"}, {"rotulo": "Não", "cor": "#aa0000"}]
    r = editar(cliente, ids[0], {"caso": "Júri", "perguntas": [{"id": ids[0], "tema": "Pergunta 1", "opcoes": OPCOES},
                                                              {"id": ids[1], "tema": "Pergunta 2", "opcoes": outras}]})
    assert r.status_code == 200, r.text
    assert sem_chave(edicao(cliente, ids[0])["perguntas"][1]["opcoes"]) == outras

def test_pergunta_de_outra_sessao_recusa(cliente):
    sid = criar(cliente)
    outra = criar(cliente, tema="Outra")
    r = editar(cliente, sid, {"caso": "", "perguntas": [{"id": outra, "tema": "Outra", "opcoes": OPCOES}]})
    assert r.status_code == 400

def test_nao_tira_a_pergunta_em_cena(cliente):
    ids = questionario(cliente, n=2)
    cliente.post(f"/api/admin/sessoes/{ids[0]}/ativar", auth=ADMIN)
    r = editar(cliente, ids[0], {"caso": "Júri", "perguntas": [{"id": ids[1], "tema": "Pergunta 2", "opcoes": OPCOES}]})
    assert r.status_code == 409

def test_inexistente_e_sem_login(cliente):
    corpo = {"caso": "", "perguntas": [{"tema": "X", "opcoes": OPCOES}]}
    assert cliente.put("/api/admin/sessoes/9999", json=corpo, auth=ADMIN).status_code == 404
    assert cliente.get("/api/admin/sessoes/9999/edicao", auth=ADMIN).status_code == 404
    assert cliente.put("/api/admin/sessoes/1", json=corpo).status_code == 401

def test_sessao_em_cena_avisa_o_telao(cliente):
    sid = criar(cliente)
    cliente.post(f"/api/admin/sessoes/{sid}/ativar", auth=ADMIN)
    with cliente.websocket_connect("/ws/telao") as ws:
        assert ws.receive_json()["tipo"] == "snapshot"
        novas = [{"rotulo": "Sim", "cor": "#00aa00"}, {"rotulo": "Não", "cor": "#aa0000"}]
        editar(cliente, sid, {"caso": "", "perguntas": [{"id": sid, "tema": "No telão", "opcoes": novas}]})
        m = ws.receive_json()
        while m["tipo"] != "estado":
            m = ws.receive_json()
        assert m["sessao"]["tema"] == "No telão"
        assert [o["rotulo"] for o in m["sessao"]["opcoes"]] == ["Sim", "Não"]
