"""#147: som que confirma o voto, e sons do cronômetro e da revelação no telão.

Os sons saem do Web Audio, que não dá para ouvir num teste: cada um é trocado por
um espião que anota o nome, antes de a página rodar."""
from playwright.sync_api import Page, expect

from e2e.test_telao import votar_pela_api
from e2e.test_urna import abrir_urna, votar

ESPIAO = """
Object.defineProperty(window, "Sons", {
  configurable: true,
  set(sons) {
    window.tocados = [];
    for (const nome of Object.keys(sons)) {
      if (typeof sons[nome] === "function" && !["preparar", "prepararNoToque", "pronto", "obter", "ligar"].includes(nome)) {
        sons[nome] = (...a) => window.tocados.push(nome);
      }
    }
    Object.defineProperty(window, "Sons", { value: sons, writable: true });
  },
});
"""

def tocados(page: Page) -> list[str]:
    return page.evaluate("window.tocados")

def test_urna_toca_ao_registrar_o_voto(page: Page, admin, urna, sessao_aberta):
    page.add_init_script(ESPIAO)
    abrir_urna(page, urna)
    votar(page)
    expect(page.locator(".carimbo")).to_be_visible()
    assert tocados(page) == ["voto"]

def test_revelacao_toca_regressiva_e_vencedora(page: Page, base_url, admin, urna, sessao_aberta):
    _, token = urna
    votar_pela_api(base_url, token, sessao_aberta, "defesa")
    page.add_init_script(ESPIAO)
    page.goto("/telao/")
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)
    expect(page.locator("#resultado .opcao.vencedora")).to_have_count(1)
    # os E2E rodam sem animação: sem 3·2·1 nem apuração, mas o fecho toca
    assert tocados(page) == ["vencedora"]

def test_telao_aberto_ja_revelado_fica_quieto(page: Page, admin, urna, sessao_aberta):
    admin.avancar(sessao_aberta)
    admin.avancar(sessao_aberta)
    page.add_init_script(ESPIAO)
    page.goto("/telao/")
    expect(page.locator("#resultado")).to_be_visible()
    assert tocados(page) == []

def test_cronometro_toca_no_inicio_nos_ultimos_segundos_e_no_fim(page: Page, admin):
    page.add_init_script(ESPIAO)
    page.goto("/telao/")
    try:
        admin.post("/api/admin/cronometro", json={"titulo": "E2E sons", "minutos": 0.1})  # 6 s
        expect(page.locator("#cronometro-esgotado")).to_be_visible(timeout=15000)
        assert tocados(page) == ["cronometroInicio"] + ["cronometroTique"] * 5 + ["cronometroFim"]
    finally:
        admin.http.delete("/api/admin/cronometro")

def test_mensagem_atrasada_do_servidor_nao_repete_apito_nem_tique(page: Page, admin):
    """O relógio do servidor e o do telão não batem no décimo: logo depois do zero,
    um reenvio com 0,3 s de sobra fazia o apito tocar duas vezes."""
    page.add_init_script(ESPIAO)
    page.goto("/telao/")
    try:
        admin.post("/api/admin/cronometro", json={"titulo": "E2E atraso", "minutos": 0.1})  # 6 s
        expect(page.locator("#cronometro-esgotado")).to_be_visible(timeout=15000)
        page.evaluate("mostrarCronometro({titulo: 'E2E atraso', restante: 0.3, rodando: true, visivel: true})")
        page.wait_for_timeout(1500)
        assert tocados(page) == ["cronometroInicio"] + ["cronometroTique"] * 5 + ["cronometroFim"]
    finally:
        admin.http.delete("/api/admin/cronometro")
