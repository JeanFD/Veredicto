import os
import re

from playwright.sync_api import Page, expect

from e2e.conftest import SENHA
from e2e.test_telao import votar_pela_api

def test_painel_mostra_votos_urnas_e_latencia(page: Page, base_url, admin, urna, sessao_aberta):
    uid, token = urna
    for opcao in ("defesa", "defesa", "acusacao"):
        votar_pela_api(base_url, token, sessao_aberta, opcao)

    page.goto("/monitor/")
    page.get_by_placeholder("Senha do mesário").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()

    expect(page.locator("#total")).to_have_text("3 votos")
    expect(page.locator("#latencia")).to_contain_text("ms")
    expect(page.locator("#urnas")).to_have_text(re.compile(r"^\d+ / \d+$"))
    expect(page.locator("#grafico div")).to_have_count(30)
    expect(page.locator("#totais")).to_contain_text("Votos aceitos (urna)")
    if os.getenv("E2E_CAPTURA"):
        page.screenshot(path=os.environ["E2E_CAPTURA"], full_page=True)

def test_senha_errada(page: Page):
    page.goto("/monitor/")
    page.get_by_placeholder("Senha do mesário").fill("errada")
    page.get_by_role("button", name="Entrar").click()
    expect(page.locator("#erro-login")).to_have_text("Senha incorreta")
