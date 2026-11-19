import uuid
from datetime import datetime, timezone

import httpx
from playwright.sync_api import Page, expect

from e2e.conftest import OPCOES

def votar_pela_api(base_url, token, sid, opcao):
    httpx.post(f"{base_url}/api/votos", headers={"X-Urna-Token": token}, json={
        "id": str(uuid.uuid4()), "sessao_id": sid, "opcao": opcao,
        "votado_em": datetime.now(timezone.utc).isoformat(),
    }).raise_for_status()

def test_total_ao_vivo_e_revelacao(page: Page, base_url, admin, urna, sessao_aberta):
    _, token = urna
    page.goto("/telao/")
    expect(page.locator("#legenda")).to_have_text("votos registrados")
    expect(page.locator("#total")).to_have_text("0")

    # o total chega pelo WebSocket, sem recarregar
    votar_pela_api(base_url, token, sessao_aberta, "defesa")
    expect(page.locator("#total")).to_have_text("1")
    votar_pela_api(base_url, token, sessao_aberta, "defesa")
    votar_pela_api(base_url, token, sessao_aberta, "acusacao")
    expect(page.locator("#total")).to_have_text("3")

    admin.avancar(sessao_aberta)
    expect(page.locator("#legenda")).to_contain_text("votação encerrada")
    expect(page.locator("#resultado")).to_be_hidden()

    admin.avancar(sessao_aberta)
    resultado = page.locator("#resultado")
    expect(resultado).to_be_visible()
    expect(page.locator("#contagem")).to_be_hidden()
    expect(resultado.locator(".opcao")).to_have_count(2)
    expect(resultado.locator(".opcao").nth(0)).to_contain_text("Acusação")
    # estes testes rodam sem animação (ver conftest): o resultado já entra fechado
    expect(resultado.locator(".opcao.vencedora")).to_have_count(1)
    expect(resultado.locator(".opcao.vencedora .rotulo")).to_have_text("Defesa")
    expect(resultado.locator(".opcao.vencedora .porcento")).to_have_text("67%")
    expect(resultado.locator(".opcao .pontos").nth(0)).to_have_text("1 voto")
    expect(resultado.locator(".opcao .pontos").nth(1)).to_have_text("2 votos")

def test_telao_aberto_depois_da_revelacao_mostra_resultado(page: Page, admin, sessao_aberta):
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)
    page.goto("/telao/")
    expect(page.locator("#resultado")).to_be_visible()
    expect(page.locator("#regressiva")).to_be_hidden()

def test_apuracao_corre_antes_de_coroar(browser, browser_context_args, base_url, admin, urna, sessao_aberta):
    """Com animação ligada, os votos aparecem aos poucos e a vencedora só se acende no fim."""
    _, token = urna
    for opcao in ("defesa", "defesa", "defesa", "acusacao"):
        votar_pela_api(base_url, token, sessao_aberta, opcao)
    contexto = browser.new_context(**{**browser_context_args, "reduced_motion": "no-preference"})
    page = contexto.new_page()
    page.goto("/telao/")
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)

    cartoes = page.locator("#resultado .opcao")
    expect(cartoes).to_have_count(2)
    # durante a apuração nenhum cartão está aceso e os números ainda não chegaram
    expect(page.locator("#resultado .opcao.vencedora")).to_have_count(0)
    assert page.locator("#resultado .opcao").nth(1).locator(".valor").inner_text() != "75"

    expect(page.locator("#resultado .opcao.vencedora")).to_have_count(1, timeout=20000)
    expect(cartoes.nth(1).locator(".porcento")).to_have_text("75%")
    # a divisória para onde os votos mandam: o cartão da frente fica mais largo
    larguras = cartoes.evaluate_all("cs => cs.map(c => c.getBoundingClientRect().width)")
    assert larguras[1] > larguras[0] * 1.3, larguras
    contexto.close()

def test_telao_avisa_quando_a_conexao_cai(page: Page, sessao_aberta):
    """#121: antes o telão congelava no último número sem dizer nada à sala."""
    tomadas = []

    def interceptar(ws):
        tomadas.append(ws)
        ws.connect_to_server()

    page.route_web_socket("**/ws/telao", interceptar)
    page.goto("/telao/")
    expect(page.locator("#total")).to_have_text("0")
    expect(page.locator("#sem-rede")).to_be_hidden()

    tomadas[0].close()
    expect(page.locator("#sem-rede")).to_be_visible()
    # o telão religa sozinho e a marca some
    expect(page.locator("#sem-rede")).to_be_hidden(timeout=15000)

def test_som_do_telao_fica_armado_com_um_clique(page: Page):
    """#121: contexto criado na hora do apito nasce suspenso e o apito some calado."""
    page.goto("/telao/")
    page.evaluate("som.suspend()")
    expect(page.locator("#ligar-som")).to_be_visible()

    page.get_by_role("button", name="ligar o som").click()
    expect(page.locator("#ligar-som")).to_be_hidden()
    assert page.evaluate("som.state") == "running"

PARAGRAFO = ("A plataforma não é neutra: o algoritmo escolhe ativamente o que viraliza, "
             "e a escolha tem consequências que o direito já sabe nomear.")

def cartao_no_telao(admin, texto: str) -> None:
    cartao = admin.post("/api/admin/cartoes", json={
        "pasta": f"E2E {uuid.uuid4().hex[:6]}", "titulo": "E2E pano de fundo",
        "texto": texto, "fonte": "",
    })
    admin.post(f"/api/admin/cartoes/{cartao['id']}/exibir")

def medir_cartao(page: Page) -> dict:
    return page.evaluate("""() => {
      const texto = document.getElementById('cartao-texto').getBoundingClientRect();
      const qr = document.getElementById('celular').getBoundingClientRect();
      const cartao = document.getElementById('cartao');
      return { textoDireita: texto.right, qrEsquerda: qr.left,
               sobra: cartao.scrollHeight - cartao.clientHeight };
    }""")

def test_cartao_cabe_inteiro_e_desvia_do_qr(page: Page, admin):
    """#126: em 1366x768 o QR cobria o texto e o resto do cartão era cortado calado."""
    chave = admin.http.get("/api/admin/telao").json()["chave"]
    sid = admin.post("/api/admin/sessoes", json={
        "tema": f"E2E cartão {uuid.uuid4().hex[:8]}", "opcoes": OPCOES, "celular": True})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    admin.avancar(sid)
    cartao_no_telao(admin, "\n\n".join([PARAGRAFO] * 7))

    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"/telao/#chave={chave}")
    expect(page.locator("#cartao")).to_be_visible()
    expect(page.locator("#celular")).to_be_visible()

    medidas = medir_cartao(page)
    assert medidas["textoDireita"] <= medidas["qrEsquerda"], medidas
    assert medidas["sobra"] <= 0, medidas
    expect(page.locator("#cartao.cortado")).to_have_count(0)

def test_cartao_longo_demais_avisa_que_continua(page: Page, admin):
    """#126: abaixo do piso o corte acontece, e aí a sala precisa saber."""
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto("/telao/")
    cartao_no_telao(admin, "\n\n".join([PARAGRAFO] * 25))
    expect(page.locator("#cartao.cortado")).to_have_count(1)

def test_faixa_de_teste_nao_cobre_o_cabecalho(page: Page, admin):
    """#126: a faixa é fixa no topo e escondia a marca, a situação e o pedido de som."""
    sid = admin.post("/api/admin/sessoes", json={
        "tema": f"E2E ensaio {uuid.uuid4().hex[:8]}", "opcoes": OPCOES, "teste": True})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    page.goto("/telao/")
    expect(page.locator("#faixa-teste")).to_be_visible()
    medidas = page.evaluate("""() => ({
      topo: document.querySelector('.topo').getBoundingClientRect().top,
      faixa: document.getElementById('faixa-teste').getBoundingClientRect().bottom,
    })""")
    assert medidas["topo"] >= medidas["faixa"], medidas

def test_botao_de_tela_cheia(page: Page):
    """#126: no projetor era F11 na mão, numa janela aberta por window.open."""
    page.goto("/telao/")
    page.get_by_role("button", name="tela cheia").click()
    expect(page.get_by_role("button", name="sair da tela cheia")).to_be_visible()
    assert page.evaluate("Boolean(document.fullscreenElement)")

def test_rodape_nao_repete_o_que_ja_esta_na_tela(page: Page, admin):
    """#128: situação e caso apareciam duas vezes; o tema, que o cartão cobre, nenhuma."""
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    tema = f"E2E rodapé {uuid.uuid4().hex[:8]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "caso": caso})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    admin.avancar(sid)
    admin.post("/api/admin/cartoes/ocultar")  # os testes acima deixam cartões na tela

    page.goto("/telao/")
    expect(page.locator("#situacao")).to_have_text("votação aberta")
    expect(page.locator("#caso")).to_have_text(caso)
    rodape = page.locator(".rodape")
    expect(rodape).not_to_contain_text("votação aberta")
    expect(rodape).not_to_contain_text(caso)
    expect(page.locator("#rodape-tema")).to_be_empty()

    # com o cartão cobrindo o palco, o rodapé resgata o tema — e só ele
    cartao_no_telao(admin, PARAGRAFO)
    expect(page.locator("#rodape-tema")).to_have_text(tema)
    expect(rodape).not_to_contain_text(caso)

def test_rotulo_longo_cabe_no_cartao_estreito(page: Page, admin):
    """#142: com 95 a 5 o cartão da perdedora picava o rótulo em pedaços de três letras."""
    admin.post("/api/admin/cartoes/ocultar")  # os testes acima deixam cartões na tela
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto("/telao/")
    expect(page.locator("#cartao")).to_be_hidden()
    page.evaluate("""() => mostrarResultado([
      { rotulo: "Culpado por negligência grave", chave: "a", cor: "#dc2626", votos: 19, pontos: 19 },
      { rotulo: "Inocente de todas as acusações", chave: "b", cor: "#2563eb", votos: 1, pontos: 1 },
    ])""")
    perdedora = page.locator("#resultado .opcao").nth(1)
    expect(perdedora).to_be_visible()
    medidas = perdedora.evaluate("""(cartao) => {
      const rotulo = cartao.querySelector('.rotulo');
      const linha = parseFloat(getComputedStyle(rotulo).lineHeight);
      return { transborda: cartao.scrollHeight - cartao.clientHeight,
               linhas: Math.round(rotulo.getBoundingClientRect().height / linha) };
    }""")
    assert medidas["transborda"] <= 0, medidas
    assert medidas["linhas"] <= 3, medidas
