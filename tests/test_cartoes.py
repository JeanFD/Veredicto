"""Cartões do telão: pastas por caso, exibição e importação de notícia por link."""
import pytest

import app.main
from app import noticia
from tests.auxiliares import ADMIN

PAGINA = """
<html><head><title>Portal · Notícias</title>
<meta property="og:title" content="Vazamento expõe dados de 87 milhões">
<style>.a { color: red }</style></head>
<body>
  <nav><a href="/">Início</a><p>Assine o portal e leia sem limites</p></nav>
  <article>
    <h1>Vazamento expõe dados de 87 milhões</h1>
    <p>Os dados foram usados para montar perfis psicográficos de eleitores em vários países.</p>
    <p>curto</p>
    <h2>O que diz a empresa</h2>
    <ul><li>A plataforma afirma que corrigiu as falhas apontadas pelos peritos.</li></ul>
    <script>rastrear()</script>
    <p>Os dados foram usados para montar perfis psicográficos de eleitores em vários países.</p>
  </article>
  <footer><p>Todos os direitos reservados a este portal de notícias desde 1999.</p></footer>
</body></html>
"""

def novo(cliente, pasta="Soberania digital", titulo="Pano de fundo", texto="Em 2013, Snowden vazou documentos."):
    r = cliente.post("/api/admin/cartoes", auth=ADMIN,
                     json={"pasta": pasta, "titulo": titulo, "texto": texto})
    assert r.status_code == 201, r.text
    return r.json()["id"]

def no_telao(cliente):
    """O cartão como o telão o recebe ao conectar."""
    with cliente.websocket_connect("/ws/telao") as ws:
        return ws.receive_json()["cartao"]

# ---------- pasta do caso ----------
def test_cartoes_ficam_guardados_por_pasta(cliente):
    novo(cliente, "Soberania digital", "Pano de fundo")
    novo(cliente, "Redes sociais", "Cambridge Analytica")
    cartoes = cliente.get("/api/admin/cartoes", auth=ADMIN).json()
    assert [(c["pasta"], c["titulo"], c["no_telao"]) for c in cartoes] == [
        ("Redes sociais", "Cambridge Analytica", False), ("Soberania digital", "Pano de fundo", False)]

def test_exibir_trocar_e_ocultar(cliente):
    a, b = novo(cliente, titulo="Pano de fundo"), novo(cliente, titulo="Posições em debate")
    assert cliente.post(f"/api/admin/cartoes/{a}/exibir", auth=ADMIN).json()["titulo"] == "Pano de fundo"
    assert no_telao(cliente)["titulo"] == "Pano de fundo"
    # só um por vez
    cliente.post(f"/api/admin/cartoes/{b}/exibir", auth=ADMIN)
    assert [c["no_telao"] for c in cliente.get("/api/admin/cartoes", auth=ADMIN).json()] == [False, True]
    assert cliente.post("/api/admin/cartoes/ocultar", auth=ADMIN).status_code == 200
    assert no_telao(cliente) is None

def test_editar_o_cartao_no_telao_atualiza_a_tela(cliente):
    cid = novo(cliente)
    cliente.post(f"/api/admin/cartoes/{cid}/exibir", auth=ADMIN)
    with cliente.websocket_connect("/ws/telao") as ws:
        ws.receive_json()
        r = cliente.patch(f"/api/admin/cartoes/{cid}", json={"titulo": "O Efeito Snowden"}, auth=ADMIN)
        assert r.json()["titulo"] == "O Efeito Snowden"
        assert ws.receive_json() == {"tipo": "cartao", "cartao": {
            "id": cid, "titulo": "O Efeito Snowden", "texto": "Em 2013, Snowden vazou documentos.", "fonte": ""}}

def test_apagar_o_cartao_exibido_limpa_o_telao(cliente):
    cid = novo(cliente)
    cliente.post(f"/api/admin/cartoes/{cid}/exibir", auth=ADMIN)
    assert cliente.delete(f"/api/admin/cartoes/{cid}", auth=ADMIN).status_code == 200
    assert no_telao(cliente) is None
    assert cliente.delete(f"/api/admin/cartoes/{cid}", auth=ADMIN).status_code == 404

def test_cartoes_exigem_mesario(cliente):
    cid = novo(cliente)
    assert cliente.get("/api/admin/cartoes").status_code == 401
    assert cliente.post(f"/api/admin/cartoes/{cid}/exibir").status_code == 401
    assert cliente.post("/api/admin/cartoes/importar", json={"url": "https://exemplo.org"}).status_code == 401

@pytest.mark.parametrize("dados", [
    {"pasta": "", "titulo": "T", "texto": "x"}, {"pasta": "P", "titulo": "", "texto": "x"},
    {"pasta": "P", "titulo": "T", "texto": ""}, {"pasta": "P", "titulo": "T", "texto": "x" * 4001},
])
def test_cartao_invalido(cliente, dados):
    assert cliente.post("/api/admin/cartoes", json=dados, auth=ADMIN).status_code == 422

# ---------- trazer de um link ----------
def test_importar_tira_manchete_e_texto(cliente, monkeypatch):
    async def falsa(url):
        assert url == "https://portal.exemplo/noticia"
        return PAGINA
    monkeypatch.setattr(noticia, "baixar", falsa)
    r = cliente.post("/api/admin/cartoes/importar", json={"url": "https://portal.exemplo/noticia"}, auth=ADMIN).json()
    assert r["titulo"] == "Vazamento expõe dados de 87 milhões"
    assert r["fonte"] == "https://portal.exemplo/noticia"
    assert r["texto"] == (
        "Os dados foram usados para montar perfis psicográficos de eleitores em vários países.\n\n"
        "O que diz a empresa\n\n"
        "- A plataforma afirma que corrigiu as falhas apontadas pelos peritos."
    )

def test_importar_avisa_quando_nao_acha_texto(cliente, monkeypatch):
    monkeypatch.setattr(noticia, "baixar", lambda url: _vazia())
    r = cliente.post("/api/admin/cartoes/importar", json={"url": "https://portal.exemplo/x"}, auth=ADMIN)
    assert r.status_code == 422 and "paywall" in r.json()["detail"]

async def _vazia():
    return "<html><body><h1>Assine para ler</h1></body></html>"

def test_importar_nao_busca_endereco_interno(cliente):
    for url in ("http://127.0.0.1:8000/api/admin/contas", "http://localhost/x", "file:///etc/passwd"):
        r = cliente.post("/api/admin/cartoes/importar", json={"url": url}, auth=ADMIN)
        assert r.status_code == 400, url
        assert r.json()["detail"] in ("Esse endereço é da rede interna do servidor",
                                      "Link inválido: use um endereço http ou https")

def test_importar_avisa_quando_a_pagina_nao_abre(cliente, monkeypatch):
    async def falha(url):
        raise app.main.httpx.ConnectTimeout("tempo")
    monkeypatch.setattr(noticia, "baixar", falha)
    r = cliente.post("/api/admin/cartoes/importar", json={"url": "https://portal.exemplo/x"}, auth=ADMIN)
    assert r.status_code == 400 and "copie e cole" in r.json()["detail"]

# ---------- extração ----------
def test_extrair_ignora_menu_rodape_e_repetidos():
    extraido = noticia.extrair(PAGINA, "https://portal.exemplo/noticia")
    assert "Assine o portal" not in extraido["texto"]
    assert "direitos reservados" not in extraido["texto"]
    assert extraido["texto"].count("perfis psicográficos") == 1
    assert "curto" not in extraido["texto"]

def test_extrair_sem_article_usa_a_pagina():
    html = ("<html><head><title>Laudo da perícia</title></head><body>"
            "<p>O laudo demonstra a arquitetura do programa de vigilância em massa.</p></body></html>")
    assert noticia.extrair(html) == {
        "titulo": "Laudo da perícia",
        "texto": "O laudo demonstra a arquitetura do programa de vigilância em massa.",
        "fonte": "",
    }

def test_extrair_corta_texto_muito_longo():
    paragrafo = "<p>" + "palavra " * 30 + "</p>"
    extraido = noticia.extrair(f"<html><body>{paragrafo * 50}</body></html>")
    assert len(extraido["texto"]) <= noticia.LIMITE_TEXTO
