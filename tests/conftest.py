import os

os.environ.update(
    ADMIN_SENHA="senha-teste",
    DB_PATH=":memory:",
    SESSOES_PATH="tests/sessoes_teste.json"
)

import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app, ultimo_sinal
from tests.auxiliares import ADMIN

@pytest.fixture
def cliente():
    with db:
        db.execute("DELETE FROM votos")
        db.execute("DELETE FROM urnas")
        db.execute("UPDATE sessoes SET estado = 'AGUARDANDO', ativa = 0, encerrada_em = NULL")
        ultimo_sinal.clear()
    with TestClient(app) as c:
        yield c

@pytest.fixture
def urna(cliente):
    r = cliente.post("/api/admin/urnas", json={"id": "urna-teste", "nome": "Teste"}, auth=ADMIN)
    return {"X-Urna-Token": r.json()["token"]}

@pytest.fixture
def sessao_aberta(cliente):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    with db:
        db.execute("UPDATE sessoes SET estado = 'ABERTA' WHERE id = 1")
    return 1
