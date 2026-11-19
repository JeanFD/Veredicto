"""Cronômetro das falas: o mesário comanda no painel e a contagem aparece no telão."""
import re

from playwright.sync_api import Page, expect

from e2e.test_mesario import confirmar, desistir, painel  # noqa: F401 (fixture)

RELOGIO = re.compile(r"^\+?\d+:\d{2}$")

def test_contagem_aparece_no_telao_e_o_mesario_comanda(painel: Page):  # noqa: F811
    telao = painel.context.new_page()
    telao.goto("/telao/")
    expect(telao.locator("#cronometro")).to_be_hidden()

    painel.get_by_role("tab", name="Telão").click()
    painel.get_by_placeholder("Tréplica").fill("E2E tréplica")
    painel.get_by_label("Minutos").fill("2")
    painel.get_by_role("button", name="Iniciar").click()

    expect(telao.locator("#cronometro-titulo")).to_have_text("E2E tréplica")
    expect(telao.locator("#cronometro-tempo")).to_have_text(re.compile(r"^(2:00|1:5\d)$"))
    expect(painel.locator("#crono-nome")).to_have_text("E2E tréplica")

    # pausado, o relógio para de andar nas duas telas
    painel.get_by_role("button", name="Pausar").click()
    expect(painel.get_by_role("button", name="Retomar")).to_be_visible()
    parado = telao.locator("#cronometro-tempo").inner_text()
    assert RELOGIO.match(parado)
    painel.wait_for_timeout(1200)
    expect(telao.locator("#cronometro-tempo")).to_have_text(parado)

    # um minuto a mais, e o telão acompanha
    painel.get_by_role("button", name="+1 min").click()
    expect(telao.locator("#cronometro-tempo")).to_have_text(re.compile(r"^(3:00|2:5\d)$"))

    painel.get_by_role("button", name="Tirar do telão").click()
    expect(telao.locator("#cronometro")).to_be_hidden()
    expect(painel.locator("#crono-ativo")).to_be_hidden()
    telao.close()

def test_telao_recarregado_continua_a_contagem(painel: Page):  # noqa: F811
    painel.get_by_role("tab", name="Telão").click()
    painel.get_by_placeholder("Tréplica").fill("E2E perícia")
    painel.get_by_label("Minutos").fill("20")
    painel.get_by_role("button", name="Iniciar").click()

    telao = painel.context.new_page()
    telao.goto("/telao/")
    expect(telao.locator("#cronometro-titulo")).to_have_text("E2E perícia")
    expect(telao.locator("#cronometro-tempo")).to_have_text(re.compile(r"^(20:00|19:5\d)$"))
    painel.get_by_role("button", name="Tirar do telão").click()
    telao.close()

def test_etapas_do_juri_em_um_clique(painel: Page):  # noqa: F811
    telao = painel.context.new_page()
    telao.goto("/telao/")
    painel.get_by_role("tab", name="Telão").click()
    painel.get_by_role("button", name="Debates e tréplicas · 20 min").click()

    expect(telao.locator("#cronometro-titulo")).to_have_text("Debates e tréplicas")
    expect(telao.locator("#cronometro-tempo")).to_have_text(re.compile(r"^(20:00|19:5\d)$"))
    # os campos acompanham o que foi iniciado
    expect(painel.locator("#crono-titulo")).to_have_value("Debates e tréplicas")
    expect(painel.locator("#crono-minutos")).to_have_value("20")

    # trocar uma contagem em andamento pede confirmação
    painel.get_by_role("button", name="Leitura da denúncia · 5 min").click()
    desistir(painel)
    expect(telao.locator("#cronometro-titulo")).to_have_text("Debates e tréplicas")
    painel.get_by_role("button", name="Leitura da denúncia · 5 min").click()
    confirmar(painel, "Trocar a contagem")
    expect(telao.locator("#cronometro-titulo")).to_have_text("Leitura da denúncia")

    painel.get_by_role("button", name="Tirar do telão").click()
    telao.close()
