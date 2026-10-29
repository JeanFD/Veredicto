"""Telas em inglês: pelo idioma do navegador e pelo seletor PT/EN."""
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect

from e2e.conftest import SENHA

def textos():
    fonte = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")
    return json.loads(fonte.split("/* textos:inicio */")[1].split("/* textos:fim */")[0])

# textos em português que não existem em inglês: nenhum deles pode sobrar na tela.
# Só as partes fixas (sem {campos}) e com mais de uma palavra, para não confundir
# com rótulos curtos iguais nos dois idiomas.
SO_EM_PORTUGUES = sorted({
    trecho.strip()
    for chave, pt in textos()["pt"].items() if pt != textos()["en"][chave]
    for trecho in re.split(r"\{\w+\}", pt) if " " in trecho.strip()
})

def sem_portugues(page: Page):
    tela = page.locator("body").inner_text()
    sobrando = [t for t in SO_EM_PORTUGUES if t in tela]
    assert sobrando == [], sobrando

@pytest.fixture
def pagina_en(browser: Browser, browser_context_args):
    contexto = browser.new_context(**{**browser_context_args, "locale": "en-US"})
    yield contexto.new_page()
    contexto.close()

def test_urna_em_ingles_pelo_navegador(pagina_en: Page, admin, urna, sessao_aberta):
    uid, token = urna
    pagina_en.goto(f"/urna/#id={uid}&token={token}")
    expect(pagina_en.locator("html")).to_have_attribute("lang", "en")
    pagina_en.get_by_role("button", name="Defesa").click()
    expect(pagina_en.locator("#tema")).to_have_text("Confirm vote for Defesa?")
    sem_portugues(pagina_en)
    pagina_en.get_by_role("button", name="Confirm").click()
    expect(pagina_en.locator("#tema")).to_contain_text("Vote recorded")
    assert admin.votos_da_urna(uid) == 1

def test_telao_em_ingles(pagina_en: Page, sessao_aberta):
    pagina_en.goto("/telao/")
    expect(pagina_en.locator("#legenda")).to_have_text("votes recorded")
    sem_portugues(pagina_en)

def test_mesario_em_ingles_sem_texto_em_portugues(pagina_en: Page, sessao_aberta):
    pagina_en.goto("/mesario/")
    pagina_en.get_by_placeholder("Username").fill("admin")
    pagina_en.get_by_placeholder("Password").fill(SENHA)
    pagina_en.get_by_role("button", name="Sign in").click()
    expect(pagina_en.get_by_role("heading", name="Sessions")).to_be_visible()
    expect(pagina_en.locator("#selo-estado")).to_have_text("OPEN")
    sem_portugues(pagina_en)
    # cada aba, já que as escondidas não entram no texto da tela
    for aba in ("New session", "Ballot boxes", "Display and links"):
        pagina_en.get_by_role("tab", name=aba).click()
        sem_portugues(pagina_en)
    pagina_en.get_by_role("tab", name="New session").click()
    expect(pagina_en.locator(".opcao input:not([type=color])").first).to_have_value("Prosecution")

@pytest.mark.parametrize("caminho", ["/", "/auditoria/", "/monitor/"])
def test_paginas_gerais_em_ingles(pagina_en: Page, caminho):
    pagina_en.goto(caminho)
    expect(pagina_en.locator("html")).to_have_attribute("lang", "en")
    expect(pagina_en.get_by_role("link", name="Audit", exact=True)).to_be_visible()
    sem_portugues(pagina_en)

def test_mensagem_do_servidor_no_idioma_da_tela(pagina_en: Page, sessao_aberta):
    pagina_en.goto("/mesario/")
    pagina_en.get_by_placeholder("Username").fill("admin")
    pagina_en.get_by_placeholder("Password").fill(SENHA)
    pagina_en.get_by_role("button", name="Sign in").click()
    pagina_en.get_by_role("tab", name="New session").click()
    # um tema que já existe: o servidor recusa e o alerta vem em inglês
    tema = pagina_en.locator("#ativa").inner_text()
    pagina_en.locator(".pergunta > input").fill(tema)
    with pagina_en.expect_event("dialog") as alerta:
        pagina_en.locator("#nova-sessao").get_by_role("button", name="Create session").click()
    assert alerta.value.message == "A session with this topic already exists"
    alerta.value.dismiss()

def test_seletor_troca_e_lembra_o_idioma(page: Page):
    page.goto("/mesario/")
    expect(page.get_by_role("button", name="Entrar")).to_be_visible()
    page.get_by_role("button", name="Mudar para inglês").click()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    page.reload()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()
    # a escolha vale para as outras telas do mesmo navegador
    page.goto("/telao/")
    expect(page.locator("html")).to_have_attribute("lang", "en")
    page.get_by_role("button", name="Switch to Portuguese").click()
    expect(page.locator("html")).to_have_attribute("lang", "pt-BR")
