"""Cartões do telão: criar no painel, exibir para a sala e tirar da tela."""
import uuid

from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)

TEXTO = ("Em 2013, o ex-analista da NSA vazou documentos do PRISM.\n\n"
         "- Interceptação de e-mails da Presidência\n"
         "- Dados de negociações da Petrobras")

def criar_cartao(painel: Page, titulo: str, pasta: str) -> None:  # noqa: F811
    painel.get_by_role("tab", name="Cartões").click()
    painel.get_by_label("Pasta do caso").fill(pasta)
    painel.get_by_label("Título").fill(titulo)
    painel.get_by_label("Texto").fill(TEXTO)
    painel.get_by_role("button", name="Salvar cartão").click()

def test_cartao_vai_para_o_telao_e_volta(painel: Page):  # noqa: F811
    titulo = f"E2E pano de fundo {uuid.uuid4().hex[:6]}"
    pasta = f"E2E caso {uuid.uuid4().hex[:6]}"
    criar_cartao(painel, titulo, pasta)

    linha = painel.locator(".sessao", has_text=titulo)
    expect(linha).to_be_visible()
    expect(painel.locator("#lista-cartoes h2", has_text=pasta)).to_be_visible()
    # o formulário volta a ficar em branco para o próximo cartão
    expect(painel.get_by_label("Título")).to_have_value("")

    telao = painel.context.new_page()
    telao.goto("/telao/")
    expect(telao.locator("#cartao")).to_be_hidden()

    linha.get_by_role("button", name="Exibir").click()
    expect(telao.locator("#cartao-titulo")).to_have_text(titulo)
    expect(telao.locator("#cartao-texto p")).to_have_text("Em 2013, o ex-analista da NSA vazou documentos do PRISM.")
    expect(telao.locator("#cartao-texto li")).to_have_count(2)
    expect(telao.locator("#cartao-texto li").nth(1)).to_have_text("Dados de negociações da Petrobras")
    expect(telao.locator("#tema")).to_be_hidden()
    expect(painel.locator(".sessao", has_text=titulo).locator(".selo")).to_have_text("NO TELÃO")

    painel.get_by_role("button", name="Tirar cartão do telão").click()
    expect(telao.locator("#cartao")).to_be_hidden()
    expect(telao.locator("#tema")).to_be_visible()
    telao.close()

def test_editar_e_apagar_cartao(painel: Page):  # noqa: F811
    titulo = f"E2E laudo {uuid.uuid4().hex[:6]}"
    criar_cartao(painel, titulo, f"E2E caso {uuid.uuid4().hex[:6]}")

    painel.locator(".sessao", has_text=titulo).get_by_role("button", name="Editar").click()
    expect(painel.get_by_label("Título")).to_have_value(titulo)
    painel.get_by_label("Título").fill(f"{titulo} revisado")
    painel.get_by_role("button", name="Salvar cartão").click()
    expect(painel.locator(".sessao", has_text=f"{titulo} revisado")).to_be_visible()

    painel.locator(".sessao", has_text=titulo).get_by_role("button", name="Apagar").click()
    expect(painel.locator(".sessao", has_text=titulo)).to_have_count(0)
