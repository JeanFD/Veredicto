from playwright.sync_api import Page, expect

from e2e.test_urna import abrir_urna, esperar, votar

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
    page.evaluate("""async () => {
        const c = await caches.open("urna-v2");
        await c.put("/urna/urna.css", new Response("/* versão antiga */"));
    }""")
    page.reload()
    esperar_service_worker(page)
    guardado = page.evaluate("""async () =>
        (await (await caches.open("urna-v2")).match("/urna/urna.css")).text()""")
    assert "versão antiga" not in guardado

def test_api_nao_passa_pelo_cache(page: Page, urna):
    abrir_urna(page, urna)
    esperar_service_worker(page)
    chaves = page.evaluate("""async () =>
        (await (await caches.open("urna-v2")).keys()).map((r) => new URL(r.url).pathname)""")
    # só os arquivos da urna e as traduções; nada de /api/
    assert chaves and all(c.startswith("/urna/") or c == "/i18n.js" for c in chaves)
