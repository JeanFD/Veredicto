"""Testes de ponta a ponta: um servidor uvicorn de verdade, num banco temporário,
dirigido por um Chromium headless via Playwright.

Rodar: pip install -r requirements-e2e.txt && playwright install chromium && pytest e2e
"""
import os
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest

SENHA = "senha-e2e"
OPCOES = [{"rotulo": "Acusação", "cor": "#dc2626"}, {"rotulo": "Defesa", "cor": "#2563eb"}]

def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    porta = porta_livre()
    pasta = tmp_path_factory.mktemp("servidor")
    ambiente = {
        **os.environ,
        "ADMIN_SENHA": SENHA,
        "DB_PATH": str(pasta / "e2e.db"),
        "SESSOES_PATH": "tests/sessoes_teste.json",
    }
    processo = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(porta)],
        env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{porta}"
    for _ in range(100):
        try:
            httpx.get(f"{url}/api/sessao/ativa", timeout=1)
            break
        except httpx.TransportError:
            time.sleep(0.1)
    else:
        processo.kill()
        pytest.fail("servidor E2E não subiu")
    yield url
    processo.terminate()
    processo.wait(timeout=10)

@pytest.fixture(scope="session")
def base_url(servidor):
    return servidor

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # sem animações: o telão mostra números finais na hora e não faz o 3·2·1
    return {**browser_context_args, "reduced_motion": "reduce"}

class Admin:
    """Atalhos do mesário pela API, para preparar o cenário de cada teste."""

    def __init__(self, url):
        self.http = httpx.Client(base_url=url, auth=("mesario", SENHA), timeout=10)

    def post(self, caminho, **kwargs):
        r = self.http.post(caminho, **kwargs)
        r.raise_for_status()
        return r.json()

    def nova_sessao(self) -> int:
        # tema único por teste: o banco é compartilhado pela execução inteira
        sid = self.post("/api/admin/sessoes", json={"tema": f"E2E {uuid.uuid4().hex[:8]}", "opcoes": OPCOES})["id"]
        self.post(f"/api/admin/sessoes/{sid}/ativar")
        return sid

    def avancar(self, sid):
        return self.post(f"/api/admin/sessoes/{sid}/avancar", params={"forcar": "true"})

    def nova_urna(self) -> tuple[str, str]:
        uid = f"u{uuid.uuid4().hex[:8]}"
        # reserva: urna de teste que nunca conecta não vira pendência na revelação
        return uid, self.post("/api/admin/urnas", json={"id": uid, "nome": uid, "reserva": True})["token"]

    def votos_da_urna(self, uid) -> int:
        """Votos que o servidor recebeu da urna na sessão ativa."""
        return next(u["votos_sessao"] for u in self.http.get("/api/admin/urnas").json() if u["id"] == uid)

@pytest.fixture(scope="session")
def admin(servidor):
    return Admin(servidor)

@pytest.fixture
def urna(admin):
    return admin.nova_urna()

@pytest.fixture
def sessao_aberta(admin):
    sid = admin.nova_sessao()
    admin.avancar(sid)
    return sid
