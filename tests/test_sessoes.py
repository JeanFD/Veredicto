from tests.auxiliares import ADMIN, novo_voto

NOVA = {
    "tema": "Inteligência artificial no judiciário",
    "opcoes": [
        {"rotulo": "Acusação", "cor": "#dc2626"},
        {"rotulo": "Defesa", "cor": "#2563eb"},
    ],
}

def criar(cliente, dados=NOVA):
    return cliente.post("/api/admin/sessoes", json=dados, auth=ADMIN)

def test_cria_sessao_e_lista(cliente):
    r = criar(cliente)
    assert r.status_code == 201
    sessoes = cliente.get("/api/admin/sessoes", auth=ADMIN).json()
    assert any(s["id"] == r.json()["id"] and s["estado"] == "AGUARDANDO" for s in sessoes)

def test_sessao_criada_recebe_votos_e_revela(cliente, urna):
    sid = criar(cliente).json()["id"]
    cliente.post(f"/api/admin/sessoes/{sid}/ativar", auth=ADMIN)
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)
    r = cliente.post("/api/votos", json=novo_voto("acusacao", sessao_id=sid), headers=urna)
    assert r.status_code == 200
    cliente.post(f"/api/admin/sessoes/{sid}/avancar", auth=ADMIN)
    r = cliente.post(f"/api/admin/sessoes/{sid}/avancar?forcar=true", auth=ADMIN)
    assert r.json()["estado"] == "REVELADA"

def test_tema_repetido_recusa(cliente):
    criar(cliente)
    assert criar(cliente, {**NOVA, "tema": "  inteligência ARTIFICIAL no judiciário "}).status_code == 409

def test_opcoes_vazias_ou_insuficientes_recusam(cliente):
    assert criar(cliente, {**NOVA, "opcoes": NOVA["opcoes"][:1]}).status_code == 422
    vazia = [{"rotulo": "  ", "cor": "#000000"}, NOVA["opcoes"][1]]
    assert criar(cliente, {**NOVA, "opcoes": vazia}).status_code == 422

def test_opcoes_repetidas_recusam(cliente):
    assert criar(cliente, {**NOVA, "opcoes": [NOVA["opcoes"][0]] * 2}).status_code == 400

def test_presets_vem_do_arquivo(cliente):
    [preset] = cliente.get("/api/admin/presets", auth=ADMIN).json()
    assert preset["tema"] == "Sessão de teste"

def test_criar_exige_mesario(cliente):
    assert cliente.post("/api/admin/sessoes", json=NOVA).status_code == 401

def test_presets_aceita_arquivo_com_bom(cliente, tmp_path, monkeypatch):
    arquivo = tmp_path / "sessoes.json"
    arquivo.write_text('[{"tema": "Com BOM", "opcoes": []}]', encoding="utf-8-sig")
    monkeypatch.setattr("app.db.SESSOES_PATH", str(arquivo))
    assert cliente.get("/api/admin/presets", auth=ADMIN).json()[0]["tema"] == "Com BOM"

def test_arquivar_a_sessao_revelada_em_cena(cliente):
    """Revelada, a sessão em cena é guardada sem precisar ativar outra antes."""
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    assert cliente.post("/api/admin/sessoes/1/arquivar", auth=ADMIN).status_code == 409
    for _ in range(3):
        cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN)
    assert cliente.post("/api/admin/sessoes/1/arquivar", auth=ADMIN).status_code == 200
    assert cliente.get("/api/sessao/ativa").json()["sessao"] is None

def test_mover_sessao_de_caso(cliente):
    ids = cliente.post("/api/admin/questionarios", auth=ADMIN, json={"caso": "Antigo", "perguntas": [
        {"tema": "Q1", "opcoes": NOVA["opcoes"]}, {"tema": "Q2", "opcoes": NOVA["opcoes"]}]}).json()["ids"]
    assert cliente.patch(f"/api/admin/sessoes/{ids[1]}", json={"caso": "Soberania"}, auth=ADMIN).json() == {
        "id": ids[1], "caso": "Soberania"}
    # o questionário inteiro acompanha, para não quebrar o bloco na lista
    casos = {s["id"]: s["caso"] for s in cliente.get("/api/admin/sessoes", auth=ADMIN).json()}
    assert [casos[i] for i in ids] == ["Soberania", "Soberania"]
    assert cliente.patch("/api/admin/sessoes/999", json={"caso": "x"}, auth=ADMIN).status_code == 404
    assert cliente.patch(f"/api/admin/sessoes/{ids[0]}", json={"caso": "x"}).status_code == 401

def test_caso_do_preset_e_contagem_na_lista(cliente):
    sessoes = cliente.get("/api/admin/sessoes", auth=ADMIN).json()
    assert {s["caso"] for s in sessoes} == {"Ensaio"}
    assert all(s["votos"] == 0 for s in sessoes)
