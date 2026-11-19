"""Auditoria pública: agrupada por caso, e quem operou só para quem entrou."""
import uuid

from playwright.sync_api import Page, expect

from e2e.conftest import OPCOES
from e2e.test_mesario import painel  # noqa: F401 (fixture)

def revelar(admin, caso: str, tema: str) -> int:
    sid = admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "caso": caso})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    for _ in range(3):  # ABERTA, ENCERRADA, REVELADA
        admin.avancar(sid)
    return sid

def test_auditoria_agrupa_por_caso_e_nao_diz_quem_para_a_rua(page: Page, admin):
    """#136: a lista era plana e o nome do operador saía para qualquer visitante."""
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    tema = f"E2E auditoria {uuid.uuid4().hex[:6]}"
    sid = revelar(admin, caso, tema)

    page.goto(f"/auditoria/#{sid}")
    expect(page.locator("#sessoes h3", has_text=caso)).to_be_visible()
    expect(page.locator("#caso-detalhe")).to_have_text(caso)
    expect(page.locator("#eventos tr").first).to_be_visible()

    expect(page.locator("#col-quem")).to_be_hidden()
    expect(page.locator("#eventos td.quem")).to_have_count(0)
    assert "admin" not in page.locator("#eventos").inner_text()

def test_auditoria_diz_quem_fez_para_quem_entrou(painel: Page, admin):  # noqa: F811
    """#136: na mesa o nome de quem operou cada passo é o que interessa."""
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    sid = revelar(admin, caso, f"E2E auditoria {uuid.uuid4().hex[:6]}")

    # mesma aba, mesmo sessionStorage: o login do painel vale na auditoria
    painel.goto(f"/auditoria/#{sid}")
    expect(painel.locator("#col-quem")).to_be_visible()
    expect(painel.locator("#eventos td.quem").first).to_have_text("admin")
    expect(painel.get_by_role("button", name="Sair")).to_be_visible()
