"""Voto por celular escolhido por sessão no painel: desligado por padrão, chave na barra da sessão ativa."""
import uuid

from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)

def test_ligar_e_desligar_o_celular_pelo_painel(painel: Page, admin):  # noqa: F811
    tema = f"E2E celular {uuid.uuid4().hex[:6]}"
    painel.get_by_role("tab", name="Nova sessão").click()
    painel.get_by_placeholder("tema ou pergunta").fill(tema)
    expect(painel.get_by_label("Permitir voto por celular")).not_to_be_checked()
    painel.get_by_role("button", name="Criar sessão").click()

    linha = painel.locator(".sessao", has_text=tema)
    expect(linha.locator(".selo.celular")).to_have_count(0)
    linha.get_by_role("button", name="Ativar").click()

    chave = painel.locator("#alternar-celular")
    expect(chave).not_to_be_checked()
    painel.locator("#chave-celular").click()
    expect(linha.locator(".selo.celular")).to_have_text("CELULAR")
    assert admin.http.get("/api/sessao/ativa").json()["sessao"]["celular"] is True

    painel.locator("#chave-celular").click()
    expect(linha.locator(".selo.celular")).to_have_count(0)
    expect(chave).not_to_be_checked()
