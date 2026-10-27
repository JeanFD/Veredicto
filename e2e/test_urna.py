import json
import time

from playwright.sync_api import Page, Route, expect

def abrir_urna(page: Page, urna):
    uid, token = urna
    page.goto(f"/urna/#id={uid}&token={token}")
    return uid

def votar(page: Page, opcao="Defesa"):
    page.get_by_role("button", name=opcao).click()
    page.get_by_role("button", name="Confirmar").click()

def esperar(condicao, segundos=20):
    limite = time.monotonic() + segundos
    while not condicao():
        assert time.monotonic() < limite, "condição não atingida a tempo"
        time.sleep(0.25)

def test_voto_completo(page: Page, admin, urna, sessao_aberta):
    uid = abrir_urna(page, urna)
    expect(page.locator("#tema")).not_to_have_text("Votação fechada")
    page.get_by_role("button", name="Defesa").click()
    expect(page.locator("#tema")).to_have_text("Confirmar voto em Defesa?")
    page.get_by_role("button", name="Confirmar").click()
    expect(page.locator("#tema")).to_contain_text("Voto registrado")
    assert admin.votos_da_urna(uid) == 1
    # volta sozinha para a cédula do próximo eleitor
    expect(page.get_by_role("button", name="Defesa")).to_be_visible(timeout=5000)

def test_corrigir_volta_para_as_opcoes(page: Page, admin, urna, sessao_aberta):
    uid = abrir_urna(page, urna)
    page.get_by_role("button", name="Acusação").click()
    page.get_by_role("button", name="Corrigir").click()
    expect(page.get_by_role("button", name="Defesa")).to_be_visible()
    assert admin.votos_da_urna(uid) == 0

def test_so_confirma_depois_da_resposta_do_servidor(page: Page, urna, sessao_aberta):
    """#35: o ✓ só aparece quando o servidor aceitou o voto."""
    respostas = []
    def atrasar(route: Route):
        time.sleep(1)
        respostas.append(route.request.url)
        route.continue_()
    abrir_urna(page, urna)
    page.route("**/api/votos", atrasar)
    votar(page)
    expect(page.locator("#tema")).to_have_text("Enviando voto…")
    expect(page.locator("#tema")).to_contain_text("Voto registrado")
    assert respostas

def test_recusa_do_servidor_avisa_o_eleitor(page: Page, urna, sessao_aberta):
    """#36: voto recusado não mostra ✓; a tela de recusa fica até o "Entendi"."""
    abrir_urna(page, urna)
    page.route("**/api/votos", lambda route: route.fulfill(
        status=409, content_type="application/json",
        body=json.dumps({"detail": {"motivo": "sessao_encerrada", "mensagem": "Sessão encerrada"}}),
    ))
    votar(page)
    expect(page.locator("body")).to_have_class("recusa")
    expect(page.locator("#tema")).to_contain_text("Voto NÃO computado: a votação já foi encerrada")
    page.get_by_role("button", name="Entendi").click()
    expect(page.get_by_role("button", name="Defesa")).to_be_visible()

def test_voto_offline_fica_na_fila_e_e_reenviado(page: Page, admin, urna, sessao_aberta):
    uid = abrir_urna(page, urna)
    expect(page.locator("#rede")).to_have_text("online")
    page.context.set_offline(True)
    votar(page)
    expect(page.locator("#tema")).to_contain_text("Sem conexão: voto guardado")
    fila = page.evaluate("JSON.parse(localStorage.getItem('fila'))")
    assert len(fila) == 1
    assert admin.votos_da_urna(uid) == 0

    page.context.set_offline(False)
    esperar(lambda: admin.votos_da_urna(uid) == 1)
    esperar(lambda: page.evaluate("JSON.parse(localStorage.getItem('fila')).length") == 0)
