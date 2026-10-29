"""Modo teste no painel: criar sessão de teste, ver as marcas nas telas e limpar."""
import uuid

from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)

def test_sessao_de_teste_do_painel_ao_limpar(painel: Page, browser, admin):  # noqa: F811
    tema = f"E2E ensaio {uuid.uuid4().hex[:6]}"
    painel.get_by_role("tab", name="Nova sessão").click()
    painel.get_by_placeholder("tema ou pergunta").fill(tema)
    painel.get_by_label("Marcar como teste").check()
    painel.get_by_role("button", name="Criar sessão").click()

    linha = painel.locator(".sessao", has_text=tema)
    expect(linha.locator(".selo.teste")).to_have_text("TESTE")
    limpar = painel.locator("#limpar-testes")
    expect(limpar).to_be_visible()

    linha.get_by_role("button", name="Ativar").click()
    expect(painel.locator("#selo-teste")).to_be_visible()

    # o telão avisa que é teste
    telao = painel.context.new_page()
    telao.goto("/telao/")
    expect(telao.locator("#faixa-teste")).to_be_visible()

    mensagens = []
    painel.on("dialog", lambda d: mensagens.append(d.message))
    limpar.click()
    expect(painel.locator(".sessao", has_text=tema)).to_have_count(0)
    expect(limpar).to_be_hidden()
    expect(telao.locator("#faixa-teste")).to_be_hidden()
    assert any("Testes apagados" in m for m in mensagens)
    assert all(s["tema"] != tema for s in admin.http.get("/api/admin/sessoes?arquivadas=true").json())
    telao.close()
