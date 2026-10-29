"""O mesmo celular vota em sessões diferentes, e de novo numa sessão que teve a contagem zerada."""
import uuid

from playwright.sync_api import Page, expect

from e2e.conftest import OPCOES

def abrir_com_celular(admin) -> tuple[int, str]:
    tema = f"E2E cel {uuid.uuid4().hex[:6]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "celular": True})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    admin.post(f"/api/admin/sessoes/{sid}/avancar")
    return sid, tema

def escanear(page: Page, admin, sid):
    chave = admin.http.get("/api/admin/telao").json()["chave"]
    codigo = admin.http.get("/api/telao/codigo", headers={"X-Telao-Chave": chave}).json()["codigo"]
    page.goto(f"/celular/#s={sid}&c={codigo}")

def votar(page: Page):
    page.get_by_role("button", name="Defesa").click()
    page.get_by_role("button", name="Confirmar").click()
    expect(page.locator("#tema")).to_contain_text("Voto registrado")

def test_mesmo_celular_vota_em_outra_sessao(page: Page, admin):
    a, _ = abrir_com_celular(admin)
    escanear(page, admin, a)
    votar(page)
    b, _ = abrir_com_celular(admin)
    escanear(page, admin, b)
    votar(page)

def test_vota_de_novo_depois_de_zerar(page: Page, admin):
    sid, tema = abrir_com_celular(admin)
    escanear(page, admin, sid)
    votar(page)
    admin.post(f"/api/admin/sessoes/{sid}/zerar", json={"confirmacao": tema})
    admin.post(f"/api/admin/sessoes/{sid}/avancar")
    escanear(page, admin, sid)
    votar(page)

def test_numero_de_sessao_reaproveitado(page: Page, admin):
    tema = f"E2E ensaio {uuid.uuid4().hex[:6]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "celular": True, "teste": True})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    admin.post(f"/api/admin/sessoes/{sid}/avancar")
    escanear(page, admin, sid)
    votar(page)
    admin.post("/api/admin/testes/limpar")
    nova, _ = abrir_com_celular(admin)
    assert nova == sid  # o SQLite reaproveita o maior id apagado
    escanear(page, admin, nova)
    votar(page)

def test_avisa_quando_outra_votacao_abre(page: Page, admin):
    a, _ = abrir_com_celular(admin)
    escanear(page, admin, a)
    votar(page)
    abrir_com_celular(admin)
    expect(page.locator("#tema")).to_have_text("Nova votação aberta. Escaneie o QR code do telão para votar.")
