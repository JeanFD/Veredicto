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
