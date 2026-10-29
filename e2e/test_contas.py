"""Contas pelo painel: o admin cria contas; mesário não vê ações de admin; monitor vai para o monitoramento."""
import re
import uuid

from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)

def entrar(page: Page, usuario, senha, tela="/mesario/"):
    page.goto(tela)
    page.get_by_placeholder("Usuário").fill(usuario)
    page.get_by_placeholder("Senha").fill(senha)
    page.get_by_role("button", name="Entrar").click()

def criar_pelo_painel(painel: Page, usuario, papel):
    painel.get_by_role("tab", name="Contas").click()
    form = painel.locator("#nova-conta")
    form.get_by_label("Usuário").fill(usuario)
    form.get_by_label("Nome").fill(usuario.title())
    form.get_by_label("Papel").select_option(papel)
    form.get_by_label("Senha inicial").fill("senha-boa-1")
    form.get_by_role("button", name="Criar conta").click()
    expect(painel.locator("#lista-contas tr", has_text=usuario)).to_be_visible()

def test_mesario_nao_ve_acoes_de_admin(painel: Page, browser, base_url):  # noqa: F811
    usuario = f"mes{uuid.uuid4().hex[:6]}"
    criar_pelo_painel(painel, usuario, "mesario")

    outra = browser.new_context(base_url=base_url, locale="pt-BR").new_page()
    entrar(outra, usuario, "senha-boa-1")
    expect(outra.locator("#painel")).to_be_visible()
    expect(outra.locator("#conta-atual")).to_contain_text("Mesário")
    expect(outra.locator("#limpar-testes")).to_be_hidden()
    outra.get_by_role("tab", name="Contas").click()
    expect(outra.locator("#nova-conta")).to_be_hidden()
    expect(outra.locator("#minha-senha")).to_be_visible()
    outra.context.close()

def test_monitor_vai_para_o_monitoramento(painel: Page, browser, base_url):  # noqa: F811
    usuario = f"mon{uuid.uuid4().hex[:6]}"
    criar_pelo_painel(painel, usuario, "monitor")

    outra = browser.new_context(base_url=base_url, locale="pt-BR").new_page()
    entrar(outra, usuario, "senha-boa-1")
    expect(outra).to_have_url(re.compile(r"/monitor/$"))
    expect(outra.locator("#painel")).to_be_visible()
    expect(outra.locator("#grade-urnas")).to_be_visible()
    outra.context.close()

def test_desativar_conta_pelo_painel(painel: Page, admin):  # noqa: F811
    usuario = f"des{uuid.uuid4().hex[:6]}"
    criar_pelo_painel(painel, usuario, "mesario")
    painel.locator("#lista-contas tr", has_text=usuario).get_by_role("button", name="Desativar").click()
    expect(painel.locator("#lista-contas tr.inativa", has_text=usuario)).to_be_visible()
    r = admin.http.post("/api/login", json={"usuario": usuario, "senha": "senha-boa-1"}, auth=None)
    assert r.status_code == 401
