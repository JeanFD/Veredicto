import re

from playwright.sync_api import Page, expect

from e2e.test_urna import abrir_urna, esperar, votar

def versao_do_cache(page: Page) -> str:
    """O nome do cache sobe quando a lista de arquivos muda; os testes leem do sw.js."""
    fonte = page.request.get("/urna/sw.js").text()
    return re.search(r'VERSAO = "([^"]+)"', fonte).group(1)

def esperar_service_worker(page: Page):
    # o controller aparece quando o service worker ativa e assume a página (clients.claim)
    page.wait_for_function("navigator.serviceWorker && !!navigator.serviceWorker.controller")

def test_urna_recarregada_sem_rede_continua_votando(page: Page, admin, urna, sessao_aberta):
    uid = abrir_urna(page, urna)
    expect(page.get_by_role("button", name="Defesa")).to_be_visible()
    esperar_service_worker(page)

    page.context.set_offline(True)
    page.reload()
    expect(page.locator("#rede")).to_have_text("offline")
    expect(page.locator("#urna-id")).to_have_text(uid)
    votar(page)
    expect(page.locator("#tema")).to_contain_text("Sem conexão: voto guardado")

    page.context.set_offline(False)
    esperar(lambda: admin.votos_da_urna(uid) == 1)
    esperar(lambda: page.evaluate("JSON.parse(localStorage.getItem('fila')).length") == 0)

def test_com_rede_carrega_a_versao_do_servidor(page: Page, urna):
    """Rede primeiro: o arquivo guardado é trocado pelo do servidor a cada carga."""
    abrir_urna(page, urna)
    esperar_service_worker(page)
    versao = versao_do_cache(page)
    page.evaluate("""async (versao) => {
        const c = await caches.open(versao);
        await c.put("/urna/urna.css", new Response("/* versão antiga */"));
    }""", versao)
    page.reload()
    esperar_service_worker(page)
    guardado = page.evaluate("""async (versao) =>
        (await (await caches.open(versao)).match("/urna/urna.css")).text()""", versao)
    assert "versão antiga" not in guardado

def test_api_nao_passa_pelo_cache(page: Page, urna):
    abrir_urna(page, urna)
    esperar_service_worker(page)
    chaves = page.evaluate("""async (versao) =>
        (await (await caches.open(versao)).keys()).map((r) => new URL(r.url).pathname)""",
        versao_do_cache(page))
    # só os arquivos da urna e os compartilhados que ela usa; nada de /api/
    assert chaves and all(c.startswith("/urna/") or c in ("/i18n.js", "/cores.js") for c in chaves)
