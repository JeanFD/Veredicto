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

def test_toque_duplo_na_opcao_nao_confirma(page: Page, admin, urna, sessao_aberta):
    """#120: o "Confirmar" nasce onde estava a primeira opção; o segundo toque não vota."""
    uid = abrir_urna(page, urna)
    caixa = page.get_by_role("button", name="Acusação").bounding_box()
    x, y = caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2
    page.mouse.click(x, y)
    page.mouse.click(x, y)
    expect(page.locator("#tema")).to_have_text("Confirmar voto em Acusação?")
    page.wait_for_timeout(300)
    assert admin.votos_da_urna(uid) == 0
    # passada a trava, o mesmo lugar confirma
    page.get_by_role("button", name="Confirmar").click()
    expect(page.locator("#tema")).to_contain_text("Voto registrado")
    assert admin.votos_da_urna(uid) == 1

def test_cedula_volta_sozinha_se_o_eleitor_se_afastar(page: Page, admin, urna, sessao_aberta):
    """#120: voto armado na tela viraria voto do próximo eleitor."""
    page.add_init_script("window.TEMPOS_URNA = { confirmacao: 3, avisar: 3 }")
    uid = abrir_urna(page, urna)
    page.get_by_role("button", name="Defesa").click()
    expect(page.locator("#tema")).to_have_text("Confirmar voto em Defesa?")
    expect(page.locator("#aviso")).to_contain_text("A cédula volta em")
    expect(page.get_by_role("button", name="Defesa")).to_be_visible(timeout=8000)
    assert admin.votos_da_urna(uid) == 0

def test_urna_sem_autorizacao_assume_a_tela(page: Page, urna, sessao_aberta):
    """#120: recusada pelo servidor, a urna não pode seguir mostrando a pergunta guardada."""
    abrir_urna(page, urna)
    expect(page.get_by_role("button", name="Defesa")).to_be_visible()
    page.route("**/api/urnas/heartbeat", lambda route: route.fulfill(
        status=401, content_type="application/json", body="{}"))
    expect(page.locator("#tema")).to_have_text(
        "Esta urna perdeu a autorização. Chame o mesário.", timeout=15000)
    expect(page.get_by_role("button", name="Defesa")).to_have_count(0)

    # o repareamento pede uma segunda confirmação e não desconfigura sem ela
    page.get_by_role("button", name="Parear de novo").click()
    page.get_by_role("button", name="Cancelar").click()
    assert page.evaluate("localStorage.getItem('urna_token')")

    # autorizada de novo, a cédula volta sem ninguém tocar na urna
    page.unroute("**/api/urnas/heartbeat")
    expect(page.get_by_role("button", name="Defesa")).to_be_visible(timeout=15000)

def test_desconfigurar_devolve_a_urna_ao_pareamento(page: Page, urna, sessao_aberta):
    """#120: o caminho de volta quando o token da urna não vale mais."""
    abrir_urna(page, urna)
    page.route("**/api/urnas/heartbeat", lambda route: route.fulfill(
        status=401, content_type="application/json", body="{}"))
    page.get_by_role("button", name="Parear de novo").click(timeout=15000)
    page.get_by_role("button", name="Desconfigurar").click()
    expect(page.get_by_role("button", name="Pedir para virar urna")).to_be_visible()
    assert page.evaluate("localStorage.getItem('urna_token')") is None

def test_seletor_de_idioma_fica_com_os_controles_do_mesario(page: Page, urna, sessao_aberta):
    """#142: solto no canto, um toque virava a cédula inteira para inglês."""
    abrir_urna(page, urna)
    expect(page.get_by_role("button", name="Defesa")).to_be_visible()
    expect(page.locator("#idioma")).to_have_count(0)

    # o mesmo gesto que revela o exportar traz o seletor
    page.locator("#urna-id").click(click_count=5, delay=60)
    expect(page.locator("#idioma")).to_be_visible()
    expect(page.locator("#exportar")).to_be_visible()

    page.locator("#urna-id").click(click_count=5, delay=60)
    expect(page.locator("#idioma")).to_have_count(0)

def test_texto_da_opcao_acompanha_a_cor(page: Page, admin, urna):
    """#142: a cor vem de um seletor livre, e o texto era sempre branco."""
    import uuid as _uuid
    sid = admin.post("/api/admin/sessoes", json={
        "tema": f"E2E cores {_uuid.uuid4().hex[:6]}",
        "opcoes": [{"rotulo": "Amarelo claro", "cor": "#f5e642"},
                   {"rotulo": "Azul escuro", "cor": "#2563eb"}],
    })["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    admin.avancar(sid)

    abrir_urna(page, urna)
    claro = page.get_by_role("button", name="Amarelo claro")
    expect(claro).to_be_visible()
    assert claro.evaluate("b => getComputedStyle(b).color") == "rgb(11, 20, 36)"
    escuro = page.get_by_role("button", name="Azul escuro")
    assert escuro.evaluate("b => getComputedStyle(b).color") == "rgb(255, 255, 255)"
