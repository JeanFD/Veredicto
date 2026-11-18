"""Cadastro de urna por pedido: a urna mostra um código, o mesário aprova no painel e a urna passa a votar."""
import re
import uuid

from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)

def test_urna_pede_e_mesario_aprova(painel: Page, browser):  # noqa: F811
    urna = browser.new_context(locale="pt-BR").new_page()
    urna.goto(f"{painel.url.split('/mesario')[0]}/urna/")
    urna.get_by_role("button", name="Pedir para virar urna").click()
    codigo = urna.locator("#tema.codigo-pedido")
    expect(codigo).to_have_text(re.compile(r"^[A-Z2-9]{4}$"))

    painel.get_by_role("tab", name="Urnas").click()
    pedido = painel.locator(f".pedido[data-codigo='{codigo.inner_text()}']")
    expect(pedido).to_be_visible()
    id_urna = pedido.locator(".id-urna").input_value()
    pedido.get_by_role("button", name="Aprovar").click()
    expect(pedido).to_have_count(0)
    expect(painel.locator("#urnas")).to_contain_text(id_urna)

    # aprovada, a urna recarrega configurada: rodapé com o id e fora da tela de pedido
    expect(urna.locator("#urna-id")).to_have_text(id_urna, timeout=10000)
    expect(urna.locator("#tema.codigo-pedido")).to_have_count(0)
    urna.context.close()

def test_pedido_recusado_avisa_a_urna(painel: Page, browser):  # noqa: F811
    urna = browser.new_context(locale="pt-BR").new_page()
    urna.goto(f"{painel.url.split('/mesario')[0]}/urna/")
    urna.get_by_role("button", name="Pedir para virar urna").click()
    codigo = urna.locator("#tema.codigo-pedido")
    expect(codigo).to_have_text(re.compile(r"^[A-Z2-9]{4}$"))

    painel.get_by_role("tab", name="Urnas").click()
    painel.locator(f".pedido[data-codigo='{codigo.inner_text()}']").get_by_role("button", name="Recusar").click()
    expect(urna.locator("#pergunta")).to_have_text("O pedido foi recusado ou expirou. Peça de novo.")
    expect(urna.get_by_role("button", name="Pedir para virar urna")).to_be_visible()
    urna.context.close()

def test_admin_apaga_urna_desativada(painel: Page, admin):  # noqa: F811
    uid = f"velha{uuid.uuid4().hex[:6]}"
    admin.post("/api/admin/urnas", json={"id": uid, "nome": "Para apagar"})
    painel.get_by_role("tab", name="Urnas").click()
    cartao = painel.locator("#urnas .urna", has_text=uid)
    cartao.locator("summary").click()
    cartao.get_by_role("button", name="Desativar").click()

    # a grade se redesenha sozinha e o bloco de ações continua aberto
    cartao = painel.locator("#urnas .urna", has_text=uid)
    expect(cartao).to_contain_text("desativada")
    expect(cartao.get_by_role("button", name="Gerar novo link")).to_have_count(0)
    cartao.get_by_role("button", name="Apagar urna").click()
    expect(painel.locator("#urnas .urna", has_text=uid)).to_have_count(0)
    assert all(u["id"] != uid for u in admin.http.get("/api/admin/urnas").json())
