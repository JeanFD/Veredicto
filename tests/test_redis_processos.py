"""Três processos uvicorn de verdade, um banco SQLite e um Redis de verdade.

Roda no CI (serviço Redis); localmente, só com REDIS_TESTE_URL=redis://... definido.
"""
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import httpx
import pytest

REDIS = os.getenv("REDIS_TESTE_URL")
pytestmark = pytest.mark.skipif(not REDIS, reason="precisa de um Redis de verdade: defina REDIS_TESTE_URL")

SENHA = "senha-processos"

def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def subir(ambiente) -> tuple[subprocess.Popen, str]:
    porta = porta_livre()
    processo = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(porta)],
        env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{porta}"
    for _ in range(100):
        try:
            httpx.get(f"{url}/api/sessao/ativa", timeout=1)
            return processo, url
        except httpx.TransportError:
            time.sleep(0.1)
    processo.kill()
    pytest.fail("processo não subiu")

@pytest.fixture
def processos(tmp_path):
    import redis
    r = redis.Redis.from_url(REDIS)
    for chave in r.scan_iter("veredicto:*"):
        r.delete(chave)
    ambiente = {**os.environ, "ADMIN_SENHA": SENHA, "DB_PATH": str(tmp_path / "compartilhado.db"),
                "SESSOES_PATH": "tests/sessoes_teste.json", "REDIS_URL": REDIS}
    # o primeiro cria o banco sozinho; em produção o deploy migra antes de subir os processos
    rodando = [subir(ambiente)]
    rodando += [subir(ambiente) for _ in range(2)]
    yield rodando
    for processo, _ in rodando:
        processo.terminate()
        processo.wait(timeout=10)

def admin(url, metodo, caminho, **kwargs):
    r = httpx.request(metodo, f"{url}{caminho}", auth=("mesario", SENHA), timeout=10, **kwargs)
    r.raise_for_status()
    return r.json()

def votar(url, token):
    httpx.post(f"{url}/api/votos", headers={"X-Urna-Token": token}, timeout=10, json={
        "id": str(uuid.uuid4()), "sessao_id": 1, "opcao": "defesa",
        "votado_em": datetime.now(timezone.utc).isoformat(),
    }).raise_for_status()

def esperar_total(ws, total, segundos=5):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            m = json.loads(ws.recv(timeout=limite - time.monotonic()))
        except TimeoutError:
            break
        if m.get("tipo") == "total" and m["total"] == total:
            return
    pytest.fail(f"o telão não recebeu total={total}")

@pytest.fixture
def sessao_aberta(processos):
    (_, a), (_, b), _ = processos
    token = admin(a, "POST", "/api/admin/urnas", json={"id": "urna1", "nome": "Urna 1"})["token"]
    admin(b, "POST", "/api/admin/sessoes/1/ativar")
    admin(a, "POST", "/api/admin/sessoes/1/avancar")
    return token

@contextmanager
def conectar_telao(url):
    from websockets.sync.client import connect
    with connect(url.replace("http", "ws") + "/ws/telao") as ws:
        assert json.loads(ws.recv(timeout=5))["tipo"] == "snapshot"
        yield ws

def test_voto_recebido_por_um_processo_chega_ao_telao_de_outro(processos, sessao_aberta):
    (_, a), (_, b), (_, c) = processos
    with conectar_telao(a) as telao_a, conectar_telao(c) as telao_c:
        votar(b, sessao_aberta)
        esperar_total(telao_a, 1)
        esperar_total(telao_c, 1)

def test_queda_de_um_processo_nao_interrompe_os_outros(processos, sessao_aberta):
    (_, a), (processo_b, b), (processo_c, c) = processos
    with conectar_telao(a) as telao_a:
        processo_c.kill()
        votar(b, sessao_aberta)
        esperar_total(telao_a, 1)
        processo_b.kill()
        votar(a, sessao_aberta)
        esperar_total(telao_a, 2)

def test_estado_compartilhado_entre_processos(processos, sessao_aberta):
    (_, a), (_, b), (_, c) = processos
    # heartbeat num processo, grade de urnas em outro
    httpx.post(f"{a}/api/urnas/heartbeat", headers={"X-Urna-Token": sessao_aberta}, json={"pendentes": 2}, timeout=10)
    [urna] = admin(b, "GET", "/api/admin/urnas")
    assert urna["online"] and urna["pendentes"] == 2
    # métricas somadas: votos recebidos por processos diferentes aparecem juntos
    votar(a, sessao_aberta)
    votar(b, sessao_aberta)
    assert admin(c, "GET", "/api/admin/metricas")["votos_total"] == {"urna": 2}
    # estado da sessão: avançado num processo, visto nos outros
    admin(c, "POST", "/api/admin/sessoes/1/avancar")
    assert admin(a, "GET", "/api/sessao/ativa")["sessao"]["estado"] == "ENCERRADA"
