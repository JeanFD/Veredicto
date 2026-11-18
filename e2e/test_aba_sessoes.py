"""Aba Sessões: blocos por caso, questionário em passos e a barra conduzindo o ciclo."""
import re
import uuid

from playwright.sync_api import Page, expect

from e2e.conftest import OPCOES
from e2e.test_mesario import painel  # noqa: F401 (fixture)

def bloco_do_caso(painel: Page, caso: str):
    """Pelo título: o nome do caso também aparece no seletor "Mover para" de cada linha."""
    return painel.locator(".caso").filter(has=painel.get_by_role("heading", name=caso, exact=True))

def questionario(admin, caso: str, n: int = 3) -> tuple[str, list[int]]:
    marca = uuid.uuid4().hex[:6]
    perguntas = [{"tema": f"E2E {marca} pergunta {i}", "opcoes": OPCOES} for i in range(1, n + 1)]
    return marca, admin.post("/api/admin/questionarios", json={"caso": caso, "perguntas": perguntas})["ids"]

def test_cada_caso_e_um_bloco_com_as_perguntas_em_passos(painel: Page, admin):  # noqa: F811
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    marca, _ = questionario(admin, caso)
    painel.reload()

    bloco = bloco_do_caso(painel, caso)
    expect(bloco.locator(".questionario")).to_have_text("Questionário · 3 perguntas")
    expect(bloco.locator(".sessao")).to_have_count(3)
    expect(bloco.locator(".sessao .passo")).to_have_text(["1", "2", "3"])
    # só a primeira pode entrar em cena; as outras esperam a revelação da anterior
    expect(bloco.locator(".sessao").nth(0).get_by_role("button", name="Ativar")).to_be_visible()
    expect(bloco.locator(".sessao").nth(1)).to_contain_text("aguarda a revelação da pergunta anterior")
    assert marca in bloco.inner_text()

def test_a_barra_conduz_o_ciclo_com_um_botao_de_cada_vez(painel: Page, admin):  # noqa: F811
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    questionario(admin, caso, n=2)
    painel.reload()
    barra = painel.locator("#estado-atual")
    bloco_do_caso(painel, caso).locator(".sessao").first.get_by_role("button", name="Ativar").click()

    for passo, estado in (("Abrir votação", "ABERTA"), ("Encerrar votação", "ENCERRADA"),
                          ("Revelar resultado", "REVELADA")):
        expect(barra.get_by_role("button")).to_have_count(1)
        expect(barra.locator(".trilha li.agora")).to_have_count(1)
        barra.get_by_role("button", name=passo).click()
        expect(painel.locator("#selo-estado")).to_have_text(estado)
    # revelada, o próximo passo é a pergunta seguinte, com o mesmo verbo da lista
    expect(barra.locator(".trilha li.feito")).to_have_count(3)
    expect(barra.get_by_role("button")).to_have_count(1)
    barra.get_by_role("button", name="Ativar pergunta 2").click()
    expect(painel.locator("#ativa")).to_contain_text("pergunta 2")

def test_arquivar_a_sessao_revelada_sem_ativar_outra(painel: Page, admin):  # noqa: F811
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": f"E2E avulsa {caso}", "opcoes": OPCOES, "caso": caso})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    for _ in range(3):
        admin.post(f"/api/admin/sessoes/{sid}/avancar", params={"forcar": "true"})
    painel.reload()

    linha = painel.locator(".sessao", has_text=f"E2E avulsa {caso}")
    expect(linha.locator(".em-cena")).to_be_visible()
    linha.locator("summary").click()
    linha.get_by_role("button", name="Arquivar").click()
    expect(painel.locator("#ativa")).to_have_text("nenhuma")
    expect(painel.locator("#trilha")).to_be_hidden()

def test_zerar_so_aparece_com_votos(painel: Page, admin, urna):  # noqa: F811
    _, token = urna
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": f"E2E votos {caso}", "opcoes": OPCOES, "caso": caso})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/ativar")
    painel.reload()
    linha = painel.locator(".sessao", has_text=f"E2E votos {caso}")
    linha.locator("summary").click()
    expect(linha.get_by_role("button", name="Zerar")).to_have_count(0)

    admin.avancar(sid)
    painel.request.post("/api/votos", headers={"X-Urna-Token": token}, data={
        "id": str(uuid.uuid4()), "sessao_id": sid, "opcao": "defesa",
        "votado_em": "2026-11-18T12:00:00+00:00"})
    painel.reload()
    linha = painel.locator(".sessao", has_text=f"E2E votos {caso}")
    linha.locator("summary").click()
    expect(linha.get_by_role("button", name="Zerar")).to_be_visible()

def test_filtro_de_caso_vale_para_sessoes_e_cartoes(painel: Page, admin):  # noqa: F811
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    outro = f"E2E outro {uuid.uuid4().hex[:6]}"
    admin.post("/api/admin/sessoes", json={"tema": f"E2E a {caso}", "opcoes": OPCOES, "caso": caso})
    admin.post("/api/admin/sessoes", json={"tema": f"E2E b {outro}", "opcoes": OPCOES, "caso": outro})
    admin.post("/api/admin/cartoes", json={"pasta": caso, "titulo": f"E2E cartão {caso}", "texto": "Pano de fundo."})
    painel.reload()

    painel.locator("#filtro-caso").select_option(caso)
    expect(bloco_do_caso(painel, caso)).to_be_visible()
    expect(bloco_do_caso(painel, outro)).to_have_count(0)
    # a aba Cartões acompanha o mesmo caso
    painel.get_by_role("tab", name="Cartões").click()
    expect(painel.locator("#filtro-caso-cartoes")).to_have_value(caso)
    expect(painel.locator("#lista-cartoes h2")).to_have_text([caso])

def test_atalho_nova_sessao_leva_o_caso(painel: Page, admin):  # noqa: F811
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    admin.post("/api/admin/sessoes", json={"tema": f"E2E c {caso}", "opcoes": OPCOES, "caso": caso})
    painel.reload()
    painel.locator("#filtro-caso").select_option(caso)
    painel.get_by_role("button", name="+ Nova sessão").click()
    expect(painel.get_by_label("Caso (júri)")).to_have_value(caso)
    expect(painel.locator("[data-painel=nova]")).to_be_visible()

def test_aba_volta_com_o_botao_do_navegador(painel: Page):  # noqa: F811
    painel.get_by_role("tab", name="Urnas").click()
    expect(painel).to_have_url(re.compile(r"#urnas$"))
    painel.get_by_role("tab", name="Cartões").click()
    painel.go_back()
    expect(painel.locator("[data-painel=urnas]")).to_be_visible()

def test_clonar_sessao_arquivada_abre_o_formulario_preenchido(painel: Page, admin):  # noqa: F811
    caso = f"E2E caso {uuid.uuid4().hex[:6]}"
    tema = f"E2E repetir {uuid.uuid4().hex[:6]}"
    sid = admin.post("/api/admin/sessoes", json={"tema": tema, "opcoes": OPCOES, "caso": caso})["id"]
    admin.post(f"/api/admin/sessoes/{sid}/arquivar")
    painel.reload()
    painel.get_by_label("mostrar arquivadas").check()

    linha = painel.locator(".sessao", has_text=tema)
    linha.locator("summary").click()
    linha.get_by_role("button", name="Clonar").click()

    # o formulário abre pronto para editar, com o tema já livre
    expect(painel.locator("[data-painel=nova]")).to_be_visible()
    expect(painel.locator(".pergunta > input")).to_have_value(f"{tema} (2)")
    expect(painel.get_by_label("Caso (júri)")).to_have_value(caso)
    expect(painel.locator(".opcao input:not([type=color])").first).to_have_value("Acusação")

    painel.locator(".pergunta > input").fill(f"{tema} segunda rodada")
    painel.get_by_role("button", name="Criar sessão").click()
    nova = painel.locator(".sessao", has_text=f"{tema} segunda rodada")
    expect(nova.locator(".selo").first).to_have_text("AGUARDANDO")
    assert [s["votos"] for s in admin.http.get("/api/admin/sessoes").json()
            if s["tema"] == f"{tema} segunda rodada"] == [0]
