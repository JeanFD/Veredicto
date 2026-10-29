from tests.auxiliares import ADMIN, novo_voto


def test_forca_bruta_bloqueia(cliente):
    for _ in range(10):
        assert cliente.get("/api/admin/sessoes", auth=("x", "errada")).status_code == 401
    assert cliente.get("/api/admin/sessoes", auth=ADMIN).status_code == 429


def test_rotas_admin_exigem_senha(cliente):
    rotas = [
        ("get", "/api/admin/sessoes"),
        ("get", "/api/admin/urnas"),
        ("post", "/api/admin/sessoes/1/ativar"),
        ("post", "/api/admin/sessoes/1/avancar"),
        ("post", "/api/admin/urnas/qualquer/desativar"),
        ("get", "/api/admin/eventos")
    ]
    for metodo, rota in rotas:
        assert getattr(cliente, metodo)(rota).status_code == 401, rota


def test_voto_sem_token(cliente, sessao_aberta):
    assert cliente.post("/api/votos", json=novo_voto()).status_code == 422


def test_heartbeat_sem_token(cliente):
    assert cliente.post("/api/urnas/heartbeat", json={"pendentes": 0}).status_code == 422


def test_urna_nao_escolhe_identidade(cliente, urna, sessao_aberta):
    voto = novo_voto() | {"urna_id": "outra-urna"}
    cliente.post("/api/votos", json=voto, headers=urna)
    urnas = cliente.get("/api/admin/urnas", auth=ADMIN).json()
    assert urnas[0]["id"] == "urna-teste" and urnas[0]["votos_sessao"] == 1

def test_login_informa_tentativas_restantes_e_tempo_de_bloqueio(cliente):
    from app.compartilhado import JANELA_SEGUNDOS, MAX_FALHAS
    r = cliente.get("/api/admin/sessoes", auth=("x", "errada"))
    assert r.headers["X-Tentativas-Restantes"] == str(MAX_FALHAS - 1)
    assert "Retry-After" not in r.headers
    for _ in range(MAX_FALHAS - 2):
        cliente.get("/api/admin/sessoes", auth=("x", "errada"))
    ultima = cliente.get("/api/admin/sessoes", auth=("x", "errada"))
    assert ultima.status_code == 401 and ultima.headers["X-Tentativas-Restantes"] == "0"
    assert 0 < int(ultima.headers["Retry-After"]) <= JANELA_SEGUNDOS
    bloqueada = cliente.get("/api/admin/sessoes", auth=ADMIN)
    assert bloqueada.status_code == 429
    assert 0 < int(bloqueada.headers["Retry-After"]) <= JANELA_SEGUNDOS
