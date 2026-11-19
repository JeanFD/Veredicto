import uuid
from datetime import datetime, timezone

import httpx
from playwright.sync_api import Page, expect

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

def test_auditoria_publica_mostra_quem_conduziu(page: Page, admin, sessao_aberta):
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)
    page.goto(f"/auditoria/#{sessao_aberta}")
    expect(page.locator("#eventos tr").first).to_contain_text("Sessão ativada")
    expect(page.locator("#eventos td.quem").first).to_have_text("admin")

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
