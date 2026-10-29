"""Contas com papéis: login com token, permissões de admin, mesário e monitor, e gestão das contas."""
import time

import pytest

import app.contas
from app.db import db
from tests.auxiliares import ADMIN, login

def bearer(token):
    return {"Authorization": f"Bearer {token}"}

def nova_conta(cliente, usuario, papel, senha="senha-boa-1"):
    r = cliente.post("/api/admin/contas", auth=ADMIN,
                     json={"usuario": usuario, "nome": usuario.title(), "papel": papel, "senha": senha})
    assert r.status_code == 201, r.text
    return login(cliente, usuario, senha)

# ---------- login ----------
def test_admin_inicial_vem_da_admin_senha(cliente):
    r = cliente.post("/api/login", json={"usuario": "Admin", "senha": "senha-teste"})
    assert r.status_code == 200
    dados = r.json()
    assert (dados["usuario"], dados["papel"]) == ("admin", "admin")
    assert dados["expira_em"] == pytest.approx(time.time() + app.contas.VALIDADE_LOGIN, abs=5)
    assert cliente.get("/api/eu", headers=bearer(dados["token"])).json()["nome"] == "Administrador"

def test_senha_errada_avisa_tentativas_e_bloqueia(cliente):
    r = cliente.post("/api/login", json={"usuario": "admin", "senha": "errada"})
    assert r.status_code == 401 and r.headers["X-Tentativas-Restantes"] == "9"
    for _ in range(9):
        cliente.post("/api/login", json={"usuario": "ninguem", "senha": "errada"})
    r = cliente.post("/api/login", json={"usuario": "admin", "senha": "senha-teste"})
    assert r.status_code == 429 and "Retry-After" in r.headers

def test_sair_encerra_o_token(cliente):
    token = login(cliente)
    assert cliente.get("/api/admin/sessoes", headers=bearer(token)).status_code == 200
    cliente.post("/api/logout", headers=bearer(token))
    r = cliente.get("/api/admin/sessoes", headers=bearer(token))
    assert r.status_code == 401 and r.json()["detail"] == "Login expirado. Entre de novo."

def test_token_vencido_nao_conta_para_o_bloqueio(cliente):
    token = login(cliente)
    with db:
        db.execute("UPDATE logins SET expira_em = ?", (time.time() - 1,))
    for _ in range(15):
        assert cliente.get("/api/admin/sessoes", headers=bearer(token)).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "admin", "senha": "senha-teste"}).status_code == 200

def test_senha_guardada_com_scrypt(cliente):
    guardado = db.execute("SELECT senha_hash FROM contas WHERE usuario = 'admin'").fetchone()[0]
    assert guardado.startswith("scrypt$") and "senha-teste" not in guardado
    assert db.execute("SELECT COUNT(*) FROM logins").fetchone()[0] == 0
    login(cliente)
    assert db.execute("SELECT token_hash FROM logins").fetchone()[0] != login(cliente)

# ---------- papéis ----------
def test_mesario_conduz_mas_nao_faz_acoes_de_admin(cliente):
    h = bearer(nova_conta(cliente, "maria", "mesario"))
    assert cliente.post("/api/admin/sessoes/1/ativar", headers=h).status_code == 200
    proibidas = [
        ("post", "/api/admin/testes/limpar", None),
        ("post", "/api/admin/sessoes/1/zerar", {"confirmacao": "x"}),
        ("get", "/api/admin/contas", None),
        ("post", "/api/admin/contas", {"usuario": "x1", "nome": "X", "papel": "admin", "senha": "senha-boa-1"}),
    ]
    for metodo, caminho, corpo in proibidas:
        r = getattr(cliente, metodo)(caminho, headers=h, **({"json": corpo} if corpo else {}))
        assert r.status_code == 403, caminho
        assert r.json()["detail"] == "Sua conta não tem permissão para isso"

def test_monitor_so_ve_urnas_e_metricas(cliente):
    h = bearer(nova_conta(cliente, "joao", "monitor"))
    assert cliente.get("/api/admin/urnas", headers=h).status_code == 200
    assert cliente.get("/api/admin/metricas", headers=h).status_code == 200
    assert cliente.get("/api/admin/sessoes", headers=h).status_code == 403
    assert cliente.post("/api/admin/sessoes/1/ativar", headers=h).status_code == 403
    assert cliente.get("/api/admin/pedidos", headers=h).status_code == 403

def test_monitor_nao_entra_no_websocket_do_painel(cliente):
    token = nova_conta(cliente, "joao", "monitor")
    with cliente.websocket_connect("/ws/mesario") as ws:
        ws.send_json({"token": token})
        assert ws.receive()["code"] == 4401

def test_auditoria_registra_quem_fez(cliente):
    h = bearer(nova_conta(cliente, "maria", "mesario"))
    cliente.post("/api/admin/sessoes/1/ativar", headers=h)
    ativada = [e for e in cliente.get("/api/admin/eventos", auth=ADMIN).json() if e["tipo"] == "sessao_ativada"]
    assert ativada[-1]["detalhe"] == "sessao=1 por=maria"
    # a auditoria pública não mostra quem
    assert all("maria" not in str(e) for e in cliente.get("/api/auditoria/sessoes/1").json().get("eventos", []))

# ---------- gestão de contas ----------
def test_admin_lista_e_cria_contas(cliente):
    nova_conta(cliente, "maria", "mesario")
    contas = cliente.get("/api/admin/contas", auth=ADMIN).json()
    assert [(c["usuario"], c["papel"], c["ativa"]) for c in contas] == [("admin", "admin", True), ("maria", "mesario", True)]
    assert all("senha_hash" not in c for c in contas)
    r = cliente.post("/api/admin/contas", auth=ADMIN,
                     json={"usuario": "maria", "nome": "Outra", "papel": "monitor", "senha": "senha-boa-1"})
    assert r.status_code == 409

@pytest.mark.parametrize("campo, valor", [("usuario", "A B"), ("papel", "dono"), ("senha", "curta")])
def test_conta_invalida(cliente, campo, valor):
    dados = {"usuario": "nova", "nome": "Nova", "papel": "mesario", "senha": "senha-boa-1", campo: valor}
    assert cliente.post("/api/admin/contas", auth=ADMIN, json=dados).status_code == 422

def test_desativar_derruba_o_acesso_na_hora(cliente):
    token = nova_conta(cliente, "maria", "mesario")
    r = cliente.patch("/api/admin/contas/maria", auth=ADMIN, json={"ativa": False})
    assert r.json()["ativa"] is False
    assert cliente.get("/api/admin/sessoes", headers=bearer(token)).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "maria", "senha": "senha-boa-1"}).status_code == 401

def test_mudar_papel_vale_ja(cliente):
    token = nova_conta(cliente, "maria", "mesario")
    cliente.patch("/api/admin/contas/maria", auth=ADMIN, json={"papel": "monitor"})
    assert cliente.get("/api/admin/sessoes", headers=bearer(token)).status_code == 401
    novo = login(cliente, "maria", "senha-boa-1")
    assert cliente.get("/api/admin/sessoes", headers=bearer(novo)).status_code == 403

def test_admin_nao_tira_o_proprio_acesso(cliente):
    for mudanca in ({"ativa": False}, {"papel": "mesario"}):
        r = cliente.patch("/api/admin/contas/admin", auth=ADMIN, json=mudanca)
        assert r.status_code == 409 and r.json()["detail"] == "Você não pode tirar o próprio acesso de admin"

def test_outro_admin_pode_ser_rebaixado(cliente):
    nova_conta(cliente, "ana", "admin")
    r = cliente.patch("/api/admin/contas/admin", auth=("ana", "senha-boa-1"), json={"papel": "mesario"})
    assert r.status_code == 200 and r.json()["papel"] == "mesario"

def test_trocar_a_propria_senha(cliente):
    outra_aba = nova_conta(cliente, "maria", "mesario")
    esta = login(cliente, "maria", "senha-boa-1")
    r = cliente.post("/api/eu/senha", headers=bearer(esta), json={"atual": "errada", "nova": "senha-nova-2"})
    assert r.status_code == 400
    r = cliente.post("/api/eu/senha", headers=bearer(esta), json={"atual": "senha-boa-1", "nova": "senha-nova-2"})
    assert r.status_code == 200
    # quem trocou continua; os outros logins da conta caem
    assert cliente.get("/api/eu", headers=bearer(esta)).status_code == 200
    assert cliente.get("/api/eu", headers=bearer(outra_aba)).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "maria", "senha": "senha-nova-2"}).status_code == 200
    assert cliente.post("/api/login", json={"usuario": "maria", "senha": "senha-boa-1"}).status_code == 401

def test_admin_redefine_senha(cliente):
    token = nova_conta(cliente, "maria", "mesario")
    assert cliente.post("/api/admin/contas/maria/senha", auth=ADMIN, json={"nova": "senha-nova-2"}).status_code == 200
    assert cliente.get("/api/eu", headers=bearer(token)).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "maria", "senha": "senha-nova-2"}).status_code == 200
    assert cliente.post("/api/admin/contas/ninguem/senha", auth=ADMIN, json={"nova": "senha-nova-2"}).status_code == 404

def test_redefinir_pela_linha_de_comando(cliente, monkeypatch, capsys):
    nova_conta(cliente, "maria", "mesario")
    cliente.patch("/api/admin/contas/maria", auth=ADMIN, json={"ativa": False})
    monkeypatch.setattr(app.contas.getpass, "getpass", lambda _: "recuperada-3")
    app.contas.principal(["redefinir", "maria"])
    assert "redefinida" in capsys.readouterr().out
    assert cliente.post("/api/login", json={"usuario": "maria", "senha": "recuperada-3"}).status_code == 200
