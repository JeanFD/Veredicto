"""Pesos no telão e na auditoria: barras pelos pontos, com o número de votos de cada opção."""
import uuid

from playwright.sync_api import Page, expect

from e2e.test_mesario import painel  # noqa: F401 (fixture)
from e2e.test_telao import votar_pela_api

def urna_com_peso(admin, peso):
    uid = f"p{uuid.uuid4().hex[:6]}"
    token = admin.post("/api/admin/urnas", json={"id": uid, "nome": uid, "peso": peso})["token"]
    return uid, token

def test_telao_e_auditoria_mostram_pontos_e_votos(page: Page, base_url, admin, sessao_aberta):
    _, turma = urna_com_peso(admin, 3)
    _, tecnico = urna_com_peso(admin, 1)
    for _ in range(2):
        votar_pela_api(base_url, turma, sessao_aberta, "acusacao")
    for _ in range(5):
        votar_pela_api(base_url, tecnico, sessao_aberta, "defesa")
    page.goto("/telao/")
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)

    barras = page.locator("#resultado .barra")
    expect(barras.nth(0).locator("strong")).to_have_text("6")
    expect(barras.nth(0).locator("small")).to_have_text("pontos · 2 votos")
    expect(barras.nth(1).locator("strong")).to_have_text("5")
    expect(barras.nth(1).locator("small")).to_have_text("pontos · 5 votos")

    page.goto(f"/auditoria/#{sessao_aberta}")
    expect(page.locator("#resultado .barra").nth(0).locator("strong")).to_have_text("6")
    expect(page.locator("#urnas")).to_contain_text("3")

def test_sem_pesos_o_telao_fica_como_antes(page: Page, base_url, admin, urna, sessao_aberta):
    _, token = urna
    votar_pela_api(base_url, token, sessao_aberta, "defesa")
    page.goto("/telao/")
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)
    expect(page.locator("#resultado .barra").nth(1).locator("strong")).to_have_text("1")
    expect(page.locator("#resultado small")).to_have_count(0)

def test_mudar_peso_da_urna_pelo_painel(painel: Page, admin):  # noqa: F811
    uid, _ = urna_com_peso(admin, 1)
    painel.evaluate("window.prompt = () => \"3\"")  # o painel aceita os diálogos com o valor padrão
    painel.get_by_role("tab", name="Urnas").click()
    cartao = painel.locator("#urnas .urna", has_text=uid)
    cartao.locator("summary").click()
    cartao.get_by_role("button", name="Mudar peso (atual: 1)").click()
    expect(painel.locator("#urnas .urna", has_text=uid)).to_contain_text(f"{uid} · peso 3")
    assert [u["peso"] for u in admin.http.get("/api/admin/urnas").json() if u["id"] == uid] == [3]
