"""Cronômetro das falas: o mesário comanda e o telão acompanha pelo WebSocket."""
import pytest

import app.cronometro
from tests.auxiliares import ADMIN

@pytest.fixture
def relogio(monkeypatch):
    """Relógio parado: andar(30) avança meio minuto sem o teste esperar."""
    atual = [1000.0]
    monkeypatch.setattr(app.cronometro, "agora_s", lambda: atual[0])
    return lambda segundos: atual.__setitem__(0, atual[0] + segundos)

def iniciar(cliente, titulo="Tréplica — Defesa", minutos=2):
    return cliente.post("/api/admin/cronometro", json={"titulo": titulo, "minutos": minutos}, auth=ADMIN)

def estado(cliente):
    """O estado como o telão o recebe."""
    with cliente.websocket_connect("/ws/telao") as ws:
        return ws.receive_json()["cronometro"]

def test_contagem_corre_e_passa_do_zero(cliente, relogio):
    assert iniciar(cliente).json() == {"titulo": "Tréplica — Defesa", "restante": 120, "rodando": True, "visivel": True}
    relogio(30)
    assert estado(cliente)["restante"] == 90
    # esgotado o tempo o relógio não para: segue contando quanto passou
    relogio(100)
    assert estado(cliente) == {"titulo": "Tréplica — Defesa", "restante": -10, "rodando": True, "visivel": True}

def test_pausar_segura_e_retomar_continua(cliente, relogio):
    iniciar(cliente)
    relogio(30)
    assert cliente.post("/api/admin/cronometro/pausar", auth=ADMIN).json() == {
        "titulo": "Tréplica — Defesa", "restante": 90, "rodando": False, "visivel": True}
    relogio(60)
    assert estado(cliente)["restante"] == 90
    assert cliente.post("/api/admin/cronometro/retomar", auth=ADMIN).json()["rodando"] is True
    relogio(15)
    assert estado(cliente)["restante"] == 75

def test_ajustar_com_o_relogio_correndo_e_parado(cliente, relogio):
    iniciar(cliente)
    assert cliente.post("/api/admin/cronometro/ajustar", json={"segundos": 60}, auth=ADMIN).json()["restante"] == 180
    cliente.post("/api/admin/cronometro/pausar", auth=ADMIN)
    assert cliente.post("/api/admin/cronometro/ajustar", json={"segundos": -60}, auth=ADMIN).json() == {
        "titulo": "Tréplica — Defesa", "restante": 120, "rodando": False, "visivel": True}
    relogio(10)
    assert estado(cliente)["restante"] == 120

def test_encerrar_tira_do_telao(cliente, relogio):
    iniciar(cliente)
    assert cliente.delete("/api/admin/cronometro", auth=ADMIN).json() == {
        "titulo": "Tréplica — Defesa", "restante": 0, "rodando": False, "visivel": False}
    assert estado(cliente)["visivel"] is False

def test_nova_contagem_troca_a_anterior(cliente, relogio):
    iniciar(cliente)
    relogio(30)
    assert iniciar(cliente, "Perícia", 20).json() == {
        "titulo": "Perícia", "restante": 1200, "rodando": True, "visivel": True}

def test_telao_e_painel_recebem_a_mudanca(cliente, relogio):
    with cliente.websocket_connect("/ws/telao") as ws:
        assert ws.receive_json()["cronometro"]["visivel"] is False
        iniciar(cliente)
        m = ws.receive_json()
        assert m["tipo"] == "cronometro" and m["cronometro"]["titulo"] == "Tréplica — Defesa"

@pytest.mark.parametrize("dados", [
    {"titulo": "", "minutos": 2}, {"titulo": "Fala", "minutos": 0}, {"titulo": "Fala", "minutos": 181},
])
def test_titulo_e_minutos_invalidos(cliente, dados):
    assert cliente.post("/api/admin/cronometro", json=dados, auth=ADMIN).status_code == 422

def test_cronometro_exige_mesario(cliente):
    assert cliente.post("/api/admin/cronometro", json={"titulo": "Fala", "minutos": 2}).status_code == 401
    assert cliente.post("/api/admin/cronometro/pausar").status_code == 401
    assert cliente.delete("/api/admin/cronometro").status_code == 401
    cliente.post("/api/admin/contas", auth=ADMIN,
                 json={"usuario": "joao", "nome": "João", "papel": "monitor", "senha": "senha-boa-1"})
    monitor = ("joao", "senha-boa-1")
    assert cliente.post("/api/admin/cronometro", json={"titulo": "Fala", "minutos": 2}, auth=monitor).status_code == 403
