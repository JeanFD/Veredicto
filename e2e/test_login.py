"""Tela de login do mesário. Bloqueio e tentativas restantes vêm de respostas
simuladas: errar a senha de verdade 10 vezes bloquearia o IP dos outros testes."""
import pytest
from playwright.sync_api import Page, Route, expect

from e2e.conftest import SENHA

LOGIN = "**/api/admin/sessoes"

@pytest.fixture
def login(page: Page):
    page.goto("/mesario/")
    return page

def responder(page: Page, status: int, cabecalhos: dict):
    def tratar(route: Route):
        route.fulfill(status=status, headers=cabecalhos, json={"detail": "x"})
    page.route(LOGIN, tratar)

def test_mostrar_e_ocultar_senha(login: Page):
    campo = login.locator("#senha")
    campo.fill("segredo")
    expect(campo).to_have_attribute("type", "password")
    login.get_by_role("button", name="Mostrar senha").click()
    expect(campo).to_have_attribute("type", "text")
    login.get_by_role("button", name="Ocultar senha").click()
    expect(campo).to_have_attribute("type", "password")

def test_aviso_de_caps_lock(login: Page):
    aviso = login.locator("#caps")
    expect(aviso).to_be_hidden()
    login.locator("#senha").evaluate("""(campo) => campo.dispatchEvent(
        new KeyboardEvent("keydown", { key: "A", modifierCapsLock: true }))""")
    expect(aviso).to_have_text("Caps Lock está ligado")
    login.locator("#senha").evaluate("""(campo) => campo.dispatchEvent(
        new KeyboardEvent("keyup", { key: "a", modifierCapsLock: false }))""")
    expect(aviso).to_be_hidden()

def test_enter_envia_e_avisa_tentativas_restantes(login: Page):
    responder(login, 401, {"X-Tentativas-Restantes": "2"})
    login.locator("#senha").fill("errada")
    login.locator("#senha").press("Enter")
    expect(login.locator("#erro-login")).to_have_text(
        "Senha incorreta. Restam 2 tentativas antes do bloqueio temporário.")

def test_bloqueio_mostra_o_tempo_e_trava_o_botao(login: Page):
    responder(login, 429, {"Retry-After": "75"})
    login.locator("#senha").fill("qualquer")
    login.get_by_role("button", name="Entrar").click()
    expect(login.locator("#erro-login")).to_contain_text("Tente de novo em 1:1")
    expect(login.get_by_role("button", name="Entrar")).to_be_disabled()

def test_sem_conexao(login: Page):
    login.route(LOGIN, lambda route: route.abort())
    login.locator("#senha").fill(SENHA)
    login.get_by_role("button", name="Entrar").click()
    expect(login.locator("#erro-login")).to_contain_text("Sem conexão com o servidor")

def test_sair_volta_ao_login_e_esquece_a_senha(login: Page):
    login.locator("#senha").fill(SENHA)
    login.get_by_role("button", name="Entrar").click()
    expect(login.locator("#painel")).to_be_visible()
    login.get_by_role("button", name="Sair").click()
    expect(login.locator("#login")).to_be_visible()
    assert login.evaluate("sessionStorage.getItem('senha')") is None
    # o monitoramento, que usa a mesma senha, também pede login de novo
    login.goto("/monitor/")
    expect(login.locator("#login")).to_be_visible()
