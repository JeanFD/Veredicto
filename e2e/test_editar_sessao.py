"""Editar sessão pelo painel: livre antes de abrir, só o texto depois, e o telão acompanha."""
import uuid

from playwright.sync_api import Page, expect

from e2e.conftest import OPCOES
from e2e.test_mesario import confirmar, painel  # noqa: F401 (fixture)

def abrir_edicao(painel: Page, tema: str):
    linha = painel.locator(".sessao", has_text=tema)
    linha.locator("summary").click()
    linha.get_by_role("button", name="Editar").click()
    expect(painel.locator("[data-painel=nova]")).to_be_visible()
    expect(painel.locator("#nova-sessao h2")).to_have_text("Editar sessão")

def test_edita_sessao_em_cena_e_o_telao_acompanha(painel: Page, admin, browser, browser_context_args):  # noqa: F811
    tema = f"E2E editar {uuid.uuid4().hex[:6]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    telao = browser.new_context(**browser_context_args).new_page()
    telao.goto("/telao/")
    expect(telao.locator("#tema")).to_have_text(tema)

    painel.reload()
    abrir_edicao(painel, tema)
    # celular, teste e modelos prontos são da criação; aqui só o conteúdo
    expect(painel.locator("#nova-teste")).to_be_hidden()
    expect(painel.locator("#presets")).to_be_hidden()
    painel.locator(".pergunta > input").fill(f"{tema} corrigido")
    painel.locator(".opcao input:not([type=color])").nth(1).fill("Réu")
    painel.get_by_role("button", name="Salvar alterações").click()

    expect(painel.locator("[data-painel=sessoes]")).to_be_visible()
    expect(painel.locator(".sessao", has_text=f"{tema} corrigido")).to_be_visible()
    expect(telao.locator("#tema")).to_have_text(f"{tema} corrigido")
    opcoes = admin.http.get(f"/api/admin/sessoes/{sid}/edicao").json()["perguntas"][0]["opcoes"]
    assert [o["rotulo"] for o in opcoes] == ["Acusação", "Réu"]

    # o formulário volta a ser de criação
    painel.locator("[data-aba=nova]").click()
    expect(painel.locator("#nova-sessao h2")).to_have_text("Criar sessão")
    expect(painel.locator(".pergunta > input")).to_have_value("")

    painel.locator("[data-aba=registro]").click()
    expect(painel.locator("#lista-registro tr", has_text="Sessão editada").first).to_contain_text(f"sessao: {sid}")
    telao.context.close()

def test_sessao_aberta_trava_as_opcoes_e_pede_confirmacao(painel: Page, admin, sessao_aberta):  # noqa: F811
    tema = admin.http.get("/api/sessao/ativa").json()["sessao"]["tema"]
    painel.reload()
    abrir_edicao(painel, tema)

    pergunta = painel.locator(".pergunta")
    expect(pergunta.locator(".aviso-travada")).to_contain_text("só o texto do tema muda")
    for campo in pergunta.locator(".opcao input").all():
        expect(campo).to_be_disabled()
    # sem tirar nem pôr opção: os botões existem, mas ficam escondidos
    expect(pergunta.locator(".opcao button")).to_have_count(2)
    for botao in pergunta.locator(".opcao button").all():
        expect(botao).to_be_hidden()
    expect(painel.locator("#mais-pergunta")).to_be_hidden()

    pergunta.locator("> input").fill(f"{tema} ajustado")
    painel.get_by_role("button", name="Salvar alterações").click()
    dialogo = painel.locator("dialog.pergunta-modal")
    expect(dialogo).to_contain_text("Já foram abertas")
    expect(dialogo).to_contain_text("auditoria pública")
    confirmar(painel, "Salvar alterações")

    expect(painel.locator("#ativa")).to_have_text(f"{tema} ajustado")
    assert admin.http.get(f"/api/admin/sessoes/{sessao_aberta}/edicao").json()["perguntas"][0]["estado"] == "ABERTA"

def test_cancelar_edicao_nao_muda_nada(painel: Page, admin):  # noqa: F811
    tema = f"E2E cancelar {uuid.uuid4().hex[:6]}"
    admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "caso": "E2E caso edição"})
    painel.reload()
    abrir_edicao(painel, tema)
    expect(painel.get_by_label("Caso (júri)")).to_have_value("E2E caso edição")
    painel.locator(".pergunta > input").fill("não salvar")
    painel.get_by_role("button", name="Cancelar edição").click()
    expect(painel.locator("[data-painel=sessoes]")).to_be_visible()
    expect(painel.locator(".sessao", has_text=tema)).to_be_visible()
    painel.locator("[data-aba=nova]").click()
    expect(painel.get_by_label("Caso (júri)")).to_have_value("")
    expect(painel.locator("#nova-teste")).to_be_visible()
