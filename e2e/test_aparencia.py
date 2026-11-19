"""#146: o admin muda cores, textos e revelação do telão pelo painel, e o telão aberto troca na hora."""
from playwright.sync_api import Page, expect

from e2e.test_mesario import confirmar, painel  # noqa: F401 (fixture)


def cor(page: Page, variavel: str) -> str:
    return page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('{variavel}').trim()")


def test_admin_muda_a_aparencia_e_o_telao_troca_na_hora(painel: Page, admin):  # noqa: F811
    telao = painel.context.new_page()
    telao.goto("/telao/")
    expect(telao.locator("#texto-celular")).to_have_text("Vote pelo celular")
    try:
        painel.get_by_role("tab", name="Telão").click()
        formulario = painel.locator("#form-aparencia")
        expect(formulario).to_be_visible()
        expect(painel.locator("#ap-destaque")).to_have_value("#d7f24e")

        painel.locator("#ap-destaque").fill("#ff3366")
        painel.get_by_label("Ao lado do QR code").fill("Aponte a câmera")
        painel.get_by_label("contagem 3·2·1").uncheck()
        formulario.get_by_role("button", name="Salvar aparência").click()

        expect(telao.locator("#texto-celular")).to_have_text("Aponte a câmera")
        assert cor(telao, "--limao") == "#ff3366"
        # recarregado, o telão pega a aparência salva no snapshot
        telao.reload()
        expect(telao.locator("#texto-celular")).to_have_text("Aponte a câmera")

        painel.get_by_role("button", name="Voltar ao padrão").click()
        confirmar(painel, "Voltar ao padrão")
        expect(telao.locator("#texto-celular")).to_have_text("Vote pelo celular")
        expect(painel.locator("#ap-destaque")).to_have_value("#d7f24e")
        expect(painel.get_by_label("contagem 3·2·1")).to_be_checked()
    finally:
        admin.http.put("/api/admin/telao/aparencia", json={})
