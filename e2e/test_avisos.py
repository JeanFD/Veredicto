"""Avisos do painel, no lugar dos alertas que travavam a tela."""
from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)

def test_aviso_de_erro_fica_e_o_de_sucesso_some(painel: Page):  # noqa: F811
    """#130: erro no meio da sessão precisa poder ser lido com calma."""
    painel.evaluate("avisarFeito('E2E deu certo'); avisarErro('E2E deu errado')")
    expect(painel.locator(".aviso.ok p")).to_have_text("E2E deu certo")
    expect(painel.locator(".aviso.erro p")).to_have_text("E2E deu errado")

    expect(painel.locator(".aviso.ok")).to_have_count(0, timeout=10000)
    expect(painel.locator(".aviso.erro")).to_have_count(1)
    expect(painel.locator(".aviso.erro")).to_have_attribute("role", "alert")

    painel.locator(".aviso.erro button").click()
    expect(painel.locator(".aviso.erro")).to_have_count(0)

def test_o_mesmo_aviso_repetido_vira_contador(painel: Page):  # noqa: F811
    """#130: a reconexão em laço não pode virar parede de avisos."""
    painel.evaluate("for (let i = 0; i < 3; i++) avisarErro('E2E repetido')")
    expect(painel.locator(".aviso.erro")).to_have_count(1)
    expect(painel.locator(".aviso.erro .vezes")).to_have_text("3×")

def test_queda_de_rede_avisa_na_lingua_da_tela(painel: Page):  # noqa: F811
    """#130: antes isso chegava ao mesário como 'Failed to fetch'."""
    painel.route("**/api/admin/eventos", lambda route: route.abort())
    painel.get_by_role("tab", name="Registro").click()
    expect(painel.locator(".aviso.erro p")).to_have_text(
        "Sem conexão com o servidor. Confira a rede e tente de novo.")
