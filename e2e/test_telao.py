import uuid
from datetime import datetime, timezone

import httpx
from playwright.sync_api import Page, expect

def votar_pela_api(base_url, token, sid, opcao):
    httpx.post(f"{base_url}/api/votos", headers={"X-Urna-Token": token}, json={
        "id": str(uuid.uuid4()), "sessao_id": sid, "opcao": opcao,
        "votado_em": datetime.now(timezone.utc).isoformat(),
    }).raise_for_status()

def test_total_ao_vivo_e_revelacao(page: Page, base_url, admin, urna, sessao_aberta):
    _, token = urna
    page.goto("/telao/")
    expect(page.locator("#legenda")).to_have_text("votos registrados")
    expect(page.locator("#total")).to_have_text("0")

    # o total chega pelo WebSocket, sem recarregar
    votar_pela_api(base_url, token, sessao_aberta, "defesa")
    expect(page.locator("#total")).to_have_text("1")
    votar_pela_api(base_url, token, sessao_aberta, "defesa")
    votar_pela_api(base_url, token, sessao_aberta, "acusacao")
    expect(page.locator("#total")).to_have_text("3")

    admin.avancar(sessao_aberta)
    expect(page.locator("#legenda")).to_contain_text("votação encerrada")
    expect(page.locator("#resultado")).to_be_hidden()

    admin.avancar(sessao_aberta)
    resultado = page.locator("#resultado")
    expect(resultado).to_be_visible()
    expect(page.locator("#contagem")).to_be_hidden()
    expect(resultado.locator(".barra")).to_have_count(2)
    expect(resultado.locator(".barra").nth(0)).to_contain_text("Acusação")
    expect(resultado.locator(".barra strong").nth(0)).to_have_text("1")
    expect(resultado.locator(".barra strong").nth(1)).to_have_text("2")

def test_telao_aberto_depois_da_revelacao_mostra_resultado(page: Page, admin, sessao_aberta):
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)
    page.goto("/telao/")
    expect(page.locator("#resultado")).to_be_visible()
    expect(page.locator("#regressiva")).to_be_hidden()
