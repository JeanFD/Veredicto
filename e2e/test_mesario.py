import re

import pytest
from playwright.sync_api import Page, expect

from e2e.conftest import SENHA

@pytest.fixture
def painel(page: Page):
    # confirmações do mesário (abrir, encerrar, revelar) são aceitas
    page.on("dialog", lambda d: d.accept())
    page.goto("/mesario/")
    page.get_by_placeholder("Senha").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    expect(page.locator("#painel")).to_be_visible()
    return page

def test_senha_errada_nao_entra(page: Page):
    page.goto("/mesario/")
    page.get_by_placeholder("Senha").fill("errada")
    page.get_by_role("button", name="Entrar").click()
    expect(page.locator("#erro-login")).to_have_text("Senha incorreta")
    expect(page.locator("#painel")).to_be_hidden()

def test_ciclo_completo_da_sessao(painel: Page, admin):
    sid = admin.post("/api/admin/sessoes", json={
        "tema": "E2E ciclo do mesário",
        "opcoes": [{"rotulo": "Sim", "cor": "#16a34a"}, {"rotulo": "Não", "cor": "#dc2626"}],
    })["id"]
    painel.reload()  # sessão criada pela API: a lista só é lida ao abrir o painel
    linha = painel.locator(".sessao", has_text="E2E ciclo do mesário")
    linha.get_by_role("button", name="Ativar").click()

    cabecalho = painel.locator("#estado-atual")
    selo = painel.locator("#selo-estado")
    expect(painel.locator("#ativa")).to_have_text("E2E ciclo do mesário")
    expect(selo).to_have_text("AGUARDANDO")

    for acao, estado in (("Abrir votação", "ABERTA"), ("Encerrar votação", "ENCERRADA"),
                         ("Revelar resultado", "REVELADA")):
        cabecalho.get_by_role("button", name=acao).click()
        expect(selo).to_have_text(estado)
        expect(selo).to_have_class(re.compile(estado))
    expect(cabecalho.get_by_role("button")).to_have_count(0)
    assert painel.request.get(f"/api/auditoria/sessoes/{sid}").ok

def test_criar_questionario_pelo_formulario(painel: Page):
    painel.locator("#configuracao > summary").click()
    painel.get_by_role("button", name="+ pergunta").click()
    perguntas = painel.locator("#perguntas fieldset")
    expect(perguntas).to_have_count(2)
    perguntas.nth(0).get_by_placeholder("tema ou pergunta").fill("E2E primeira")
    perguntas.nth(1).get_by_placeholder("tema ou pergunta").fill("E2E segunda")
    painel.get_by_role("button", name="Criar sessão").click()

    expect(painel.locator(".sessao", has_text="Pergunta 1 de 2 · E2E primeira")).to_be_visible()
    segunda = painel.locator(".sessao", has_text="Pergunta 2 de 2 · E2E segunda")
    expect(segunda).to_contain_text("aguarda a revelação da pergunta anterior")
    expect(segunda.get_by_role("button", name="Ativar")).to_have_count(0)
