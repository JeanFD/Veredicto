from datetime import datetime, timedelta, timezone

from app.db import db
from tests.auxiliares import ADMIN, novo_voto


def abrir_e_encerrar(cliente):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)


def test_aceita_voto_feito_antes_do_encerramento(cliente, urna):
    abrir_e_encerrar(cliente)
    antes = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert cliente.post("/api/votos", json=novo_voto(votado_em=antes), headers=urna).status_code == 200


def test_recusa_voto_feito_depois_do_encerramento(cliente, urna):
    abrir_e_encerrar(cliente)
    depois = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert cliente.post("/api/votos", json=novo_voto(votado_em=depois), headers=urna).status_code == 409


def test_recusa_atraso_acima_da_tolerancia(cliente, urna):
    abrir_e_encerrar(cliente)
    encerrada = datetime.now(timezone.utc) - timedelta(minutes=11)
    with db:
        db.execute("UPDATE sessoes SET encerrada_em = ? WHERE id = 1", (encerrada.isoformat(),))
    voto = novo_voto(votado_em=encerrada - timedelta(minutes=1))
    assert cliente.post("/api/votos", json=voto, headers=urna).status_code == 409


def test_recusa_apos_revelar(cliente, urna):
    abrir_e_encerrar(cliente)
    cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN)
    antes = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert cliente.post("/api/votos", json=novo_voto(votado_em=antes), headers=urna).status_code == 409

def test_recusa_por_encerramento_traz_motivo(cliente, urna):
    abrir_e_encerrar(cliente)
    depois = datetime.now(timezone.utc) + timedelta(seconds=30)
    r = cliente.post("/api/votos", json=novo_voto(votado_em=depois), headers=urna)
    assert r.status_code == 409
    assert r.json()["detail"]["motivo"] == "sessao_encerrada"


def test_recusa_antes_de_abrir_traz_motivo(cliente, urna):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    r = cliente.post("/api/votos", json=novo_voto(), headers=urna)
    assert r.json()["detail"]["motivo"] == "sessao_nao_aberta"


def test_importacao_lista_motivo_da_recusa(cliente, urna):
    abrir_e_encerrar(cliente)
    depois = datetime.now(timezone.utc) + timedelta(seconds=30)
    r = cliente.post("/api/admin/importar", auth=ADMIN,
                     json={"urna_id": "urna-teste", "votos": [novo_voto(votado_em=depois)]})
    assert r.json()["recusados"][0]["motivo"] == "sessao_encerrada"
