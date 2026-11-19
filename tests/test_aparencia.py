"""#146: o admin configura cores, textos e revelação do telão pelo painel."""
from app.db import db
from tests.auxiliares import ADMIN, login


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_padrao_vai_no_snapshot_do_telao(cliente):
    with cliente.websocket_connect("/ws/telao") as ws:
        inicial = ws.receive_json()
    assert inicial["aparencia"]["cores"]["destaque"] == "#d7f24e"
    assert inicial["aparencia"]["textos"]["votos"] == ""
    assert inicial["aparencia"]["revelacao"]["regressiva"] is True


def test_admin_salva_e_o_telao_recebe_na_hora(cliente):
    nova = {"cores": {"destaque": "#ff3366"}, "textos": {"votos": "  pessoas já votaram "},
            "revelacao": {"regressiva": False, "duracao": 3}}
    with cliente.websocket_connect("/ws/telao") as ws:
        ws.receive_json()
        r = cliente.put("/api/admin/telao/aparencia", json=nova, auth=ADMIN)
        assert r.status_code == 200, r.text
        aviso = ws.receive_json()
    assert aviso["tipo"] == "aparencia"
    a = aviso["aparencia"]
    assert a["cores"]["destaque"] == "#ff3366" and a["cores"]["fundo"] == "#0b0c0a"
    assert a["textos"]["votos"] == "pessoas já votaram"
    assert a["revelacao"] == {"regressiva": False, "apuracao": True, "duracao": 3, "mostrar_votos": True}
    assert cliente.get("/api/admin/telao/aparencia", auth=ADMIN).json() == a


def test_salvar_fica_no_registro_com_o_que_mudou(cliente):
    cliente.put("/api/admin/telao/aparencia", json={"cores": {"fundo": "#000000"}}, auth=ADMIN)
    cliente.put("/api/admin/telao/aparencia", json={"cores": {"fundo": "#000000"}}, auth=ADMIN)
    eventos = [e for e in cliente.get("/api/admin/eventos", auth=ADMIN).json()
               if e["tipo"] == "telao_aparencia_alterada"]
    assert [e["detalhe"] for e in eventos] == ["campos=cores.fundo por=admin"]


def test_valores_invalidos_sao_recusados(cliente):
    for corpo in ({"cores": {"fundo": "red"}}, {"revelacao": {"duracao": 60}},
                  {"textos": {"vencedora": "x" * 31}}, {"outro": 1}):
        assert cliente.put("/api/admin/telao/aparencia", json=corpo, auth=ADMIN).status_code == 422, corpo


def test_so_admin_muda_mas_o_mesario_ve(cliente):
    cliente.post("/api/admin/contas", auth=ADMIN,
                 json={"usuario": "maria", "nome": "Maria", "papel": "mesario", "senha": "senha-boa-1"})
    token = login(cliente, "maria", "senha-boa-1")
    assert cliente.get("/api/admin/telao/aparencia", headers=bearer(token)).status_code == 200
    r = cliente.put("/api/admin/telao/aparencia", json={}, headers=bearer(token))
    assert r.status_code == 403


def test_configuracao_antiga_invalida_volta_ao_padrao(cliente):
    with db:
        db.execute("""UPDATE aparencia_telao SET config = '{"cores": {"fundo": "azul"}}'""")
    assert cliente.get("/api/admin/telao/aparencia", auth=ADMIN).json()["cores"]["fundo"] == "#0b0c0a"
