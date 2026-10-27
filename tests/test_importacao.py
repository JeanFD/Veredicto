from datetime import datetime, timedelta, timezone

from app.db import db
from tests.auxiliares import ADMIN, novo_voto

def arquivo_exportado(votos, urna_id="urna-teste"):
    # mesmo formato gerado pelo botão "Exportar fila" da urna
    return {"formato": "veredicto-fila", "versao": 1, "urna_id": urna_id,
            "exportado_em": datetime.now(timezone.utc).isoformat(), "votos": votos}

def importar(cliente, dados):
    return cliente.post("/api/admin/importar", json=dados, auth=ADMIN)

def contar_votos():
    return db.execute("SELECT COUNT(*) FROM votos").fetchone()[0]

def encerrar(cliente):
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)

def test_importa_e_reimporta_sem_duplicar(cliente, urna, sessao_aberta):
    arquivo = arquivo_exportado([novo_voto(), novo_voto("acusacao")])
    assert importar(cliente, arquivo).json() == {"aceitos": 2, "existentes": 0, "recusados": []}
    assert importar(cliente, arquivo).json() == {"aceitos": 0, "existentes": 2, "recusados": []}
    assert contar_votos() == 2

def test_voto_ja_enviado_pela_urna_conta_como_existente(cliente, urna, sessao_aberta):
    voto = novo_voto()
    cliente.post("/api/votos", json=voto, headers=urna)
    assert importar(cliente, arquivo_exportado([voto])).json()["existentes"] == 1

def test_importacao_aceita_voto_anterior_ao_encerramento_fora_da_tolerancia(cliente, urna, sessao_aberta):
    encerrar(cliente)
    encerrada = datetime.now(timezone.utc) - timedelta(hours=2)
    with db:
        db.execute("UPDATE sessoes SET encerrada_em = ? WHERE id = 1", (encerrada.isoformat(),))
    voto = novo_voto(votado_em=encerrada - timedelta(minutes=5))
    assert cliente.post("/api/votos", json=voto, headers=urna).status_code == 409
    assert importar(cliente, arquivo_exportado([voto])).json()["aceitos"] == 1

def test_importacao_recusa_voto_posterior_ao_encerramento(cliente, urna, sessao_aberta):
    encerrar(cliente)
    voto = novo_voto(votado_em=datetime.now(timezone.utc) + timedelta(minutes=1))
    [recusado] = importar(cliente, arquivo_exportado([voto])).json()["recusados"]
    assert recusado["motivo"] == "sessao_encerrada"

def test_importacao_recusa_apos_revelar(cliente, urna, sessao_aberta):
    voto = novo_voto()
    encerrar(cliente)
    cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN)
    assert importar(cliente, arquivo_exportado([voto])).json()["aceitos"] == 0
    assert contar_votos() == 0

def test_importacao_mostra_motivo_por_voto(cliente, urna, sessao_aberta):
    arquivo = arquivo_exportado([novo_voto("culpado"), novo_voto(sessao_id=99), novo_voto()])
    r = importar(cliente, arquivo).json()
    assert r["aceitos"] == 1
    assert [v["motivo"] for v in r["recusados"]] == ["opcao_invalida", "sessao_inexistente"]

def test_importacao_de_urna_inexistente(cliente, sessao_aberta):
    assert importar(cliente, arquivo_exportado([novo_voto()], "fantasma")).status_code == 404

def test_arquivo_invalido(cliente, urna):
    assert importar(cliente, {"qualquer": "coisa"}).status_code == 422
    assert importar(cliente, arquivo_exportado([{"id": "nao-e-uuid"}])).status_code == 422

def test_importacao_registra_auditoria(cliente, urna, sessao_aberta):
    importar(cliente, arquivo_exportado([novo_voto()]))
    ultimo = cliente.get("/api/admin/eventos", auth=ADMIN).json()[-1]
    assert ultimo["tipo"] == "importacao"
    assert "aceitos=1 existentes=0" in ultimo["detalhe"]
