import re

import httpx
import pytest
from playwright.sync_api import Page, expect

from e2e.conftest import SENHA

def confirmar(page: Page, acao: str, digitando: str | None = None) -> None:
    """Confirma a pergunta do painel; `digitando` preenche o campo que ela pedir."""
    dialogo = page.locator("dialog.pergunta-modal")
    expect(dialogo).to_be_visible()
    if digitando is not None:
        dialogo.locator("input").fill(digitando)
    dialogo.get_by_role("button", name=acao, exact=True).click()
    expect(dialogo).to_have_count(0)

def desistir(page: Page) -> None:
    dialogo = page.locator("dialog.pergunta-modal")
    expect(dialogo).to_be_visible()
    dialogo.get_by_role("button", name="Cancelar", exact=True).click()
    expect(dialogo).to_have_count(0)

def entrar(page: Page):
    page.goto("/mesario/")
    page.get_by_placeholder("Usuário").fill("admin")
    page.get_by_placeholder("Senha").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    expect(page.locator("#painel")).to_be_visible()
    return page

@pytest.fixture
def painel(page: Page):
    return entrar(page)

def test_senha_errada_nao_entra(page: Page):
    page.goto("/mesario/")
    page.get_by_placeholder("Usuário").fill("admin")
    page.get_by_placeholder("Senha").fill("errada")
    page.get_by_role("button", name="Entrar").click()
    expect(page.locator("#erro-login")).to_have_text("Usuário ou senha incorretos")
    expect(page.locator("#painel")).to_be_hidden()

def test_ciclo_completo_da_sessao(painel: Page, admin):
    sid = admin.post("/api/admin/sessoes", json={
        "tema": "E2E ciclo do mesário",
        "opcoes": [{"rotulo": "Sim", "cor": "#16a34a"}, {"rotulo": "Não", "cor": "#dc2626"}],
    })["id"]
    painel.reload()  # sessão criada pela API: a lista só é lida ao abrir o painel
    linha = painel.locator(".sessao", has_text="E2E ciclo do mesário")
    linha.get_by_role("button", name="Ativar").click()

    cabecalho = painel.locator("#estado-atual")
    selo = painel.locator("#selo-estado")
    expect(painel.locator("#ativa")).to_have_text("E2E ciclo do mesário")
    expect(selo).to_have_text("AGUARDANDO")

    for acao, estado in (("Abrir votação", "ABERTA"), ("Encerrar votação", "ENCERRADA"),
                         ("Revelar resultado", "REVELADA")):
        cabecalho.get_by_role("button", name=acao).click()
        confirmar(painel, acao)
        expect(selo).to_have_text(estado)
        expect(selo).to_have_class(re.compile(estado))
    expect(cabecalho.get_by_role("button")).to_have_count(0)
    assert painel.request.get(f"/api/auditoria/sessoes/{sid}").ok

def test_criar_questionario_pelo_formulario(painel: Page):
    painel.get_by_role("tab", name="Nova sessão").click()
    painel.get_by_role("button", name="+ pergunta").click()
    perguntas = painel.locator("#perguntas fieldset")
    expect(perguntas).to_have_count(2)
    perguntas.nth(0).get_by_placeholder("tema ou pergunta").fill("E2E primeira")
    perguntas.nth(1).get_by_placeholder("tema ou pergunta").fill("E2E segunda")
    painel.get_by_role("button", name="Criar sessão").click()

    primeira = painel.locator(".sessao", has_text="E2E primeira")
    expect(primeira.locator(".passo")).to_have_text("1")
    segunda = painel.locator(".sessao", has_text="E2E segunda")
    expect(segunda).to_contain_text("aguarda a revelação da pergunta anterior")
    expect(segunda.get_by_role("button", name="Ativar")).to_have_count(0)

def test_painel_avisa_quando_a_conexao_cai(page: Page):
    """#122: um total parado por queda de rede parecia um total parado por falta de votos."""
    tomadas = []

    def interceptar(ws):
        tomadas.append(ws)
        ws.connect_to_server()

    page.route_web_socket("**/ws/mesario", interceptar)
    painel = entrar(page)
    expect(painel.locator("#sem-rede")).to_be_hidden()

    tomadas[0].close()
    expect(painel.locator("#sem-rede")).to_be_visible()
    # o painel religa sozinho e a marca some
    expect(painel.locator("#sem-rede")).to_be_hidden(timeout=15000)

def test_urna_offline_mostra_os_votos_presos(painel: Page, base_url, admin):
    """#122: offline é justo quando o número de pendentes decide ir buscar o arquivo."""
    uid, token = admin.nova_urna()
    httpx.post(f"{base_url}/api/urnas/heartbeat", headers={"X-Urna-Token": token},
               json={"pendentes": 3, "recusados": 0}).raise_for_status()
    cartao = painel.locator(".urna", has_text=uid)
    expect(cartao).to_contain_text("3 pendentes", timeout=15000)

    # passados 15s sem sinal a urna conta como offline, e o número não pode sumir
    expect(cartao).to_contain_text("offline há", timeout=30000)
    expect(cartao.locator(".presos")).to_have_text("3 votos presos na urna")
