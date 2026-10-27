import json
import logging
from datetime import datetime

import pytest

from app.observabilidade import FormatoJson, logger, metricas
from app.seguranca import chave_telao
from tests.auxiliares import ADMIN, novo_voto

class Coletor(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(FormatoJson())
        self.linhas = []

    def emit(self, record):
        self.linhas.append(self.format(record))

@pytest.fixture
def logs():
    coletor = Coletor()
    logger.addHandler(coletor)
    metricas.zerar()
    yield lambda: [json.loads(l) for l in coletor.linhas]
    logger.removeHandler(coletor)

def do_tipo(registros, evento):
    return [r for r in registros if r["evento"] == evento]

# ---------- formato ----------
def test_cada_linha_e_json_com_campos_minimos(cliente, logs, urna, sessao_aberta):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    registros = logs()
    assert registros
    for r in registros:
        datetime.fromisoformat(r["ts"])
        assert isinstance(r["evento"], str)

def test_voto_recebido_tem_sessao_e_urna_sem_a_opcao(cliente, logs, urna, sessao_aberta):
    voto = novo_voto("defesa")
    cliente.post("/api/votos", json=voto, headers=urna)
    [r] = do_tipo(logs(), "voto_recebido")
    assert (r["sessao"], r["urna"], r["voto"]) == (1, "urna-teste", voto["id"])
    assert "defesa" not in json.dumps(logs())

def test_voto_recusado_tem_motivo(cliente, logs, urna):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    [r] = do_tipo(logs(), "voto_recusado")
    assert (r["sessao"], r["urna"], r["motivo"]) == (1, "urna-teste", "sessao_nao_aberta")

def test_reenvio_nao_conta_duas_vezes(cliente, logs, urna, sessao_aberta):
    voto = novo_voto()
    cliente.post("/api/votos", json=voto, headers=urna)
    cliente.post("/api/votos", json=voto, headers=urna)
    assert len(do_tipo(logs(), "voto_recebido")) == 1
    assert len(do_tipo(logs(), "voto_reenviado")) == 1
    assert metricas.votos_total["urna"] == 1

def test_mudancas_de_estado_da_sessao(cliente, logs):
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    for _ in range(3):
        cliente.post("/api/admin/sessoes/1/avancar", params={"forcar": "true"}, auth=ADMIN)
    registros = logs()
    [ativada] = do_tipo(registros, "sessao_ativada")
    assert ativada["sessao"] == 1
    estados = [(r["sessao"], r["estado"]) for r in do_tipo(registros, "sessao_avancada")]
    assert estados == [(1, "ABERTA"), (1, "ENCERRADA"), (1, "REVELADA")]

def test_cadastro_e_desativacao_de_urna(cliente, logs):
    cliente.post("/api/admin/urnas", json={"id": "palco", "nome": "Palco"}, auth=ADMIN)
    cliente.post("/api/admin/urnas/palco/desativar", auth=ADMIN)
    registros = logs()
    assert do_tipo(registros, "urna_cadastrada")[0]["urna"] == "palco"
    assert do_tipo(registros, "urna_desativada")[0]["urna"] == "palco"
    assert "token" not in json.dumps(registros)

def test_voto_por_celular(cliente, logs, sessao_aberta):
    codigo = cliente.get("/api/telao/codigo", headers={"X-Telao-Chave": chave_telao()}).json()["codigo"]
    cedula = cliente.post("/api/celular/entrar", json={"sessao_id": 1, "codigo": codigo}).json()["cedula"]
    voto = {"cedula": cedula, "id": novo_voto()["id"], "opcao": "acusacao"}
    cliente.post("/api/celular/votar", json=voto)
    cliente.post("/api/celular/votar", json=voto)  # reenvio
    registros = logs()
    [r] = do_tipo(registros, "voto_recebido")
    assert (r["sessao"], r["urna"]) == (1, "celular")
    assert len(do_tipo(registros, "voto_reenviado")) == 1
    assert "acusacao" not in json.dumps(registros) and cedula not in json.dumps(registros)

# ---------- métricas ----------
def test_metricas_exigem_senha(cliente):
    assert cliente.get("/api/admin/metricas").status_code == 401
    assert cliente.get("/metrics").status_code == 401

def test_metricas_do_painel(cliente, logs, urna, sessao_aberta):
    for _ in range(3):
        cliente.post("/api/votos", json=novo_voto(), headers=urna)
    cliente.post("/api/urnas/heartbeat", json={"pendentes": 0}, headers=urna)
    m = cliente.get("/api/admin/metricas", auth=ADMIN).json()
    assert len(m["votos_por_minuto"]) == 30 and m["votos_por_minuto"][-1] == 3
    assert m["latencia_ms"]["amostras"] == 3 and m["latencia_ms"]["p95"] >= m["latencia_ms"]["p50"] > 0
    assert m["urnas"] == {"online": 1, "ativas": 1}
    assert m["sessao"]["total"] == 3
    assert m["votos_total"] == {"urna": 3}

def test_metricas_formato_prometheus(cliente, logs, urna, sessao_aberta):
    cliente.post("/api/votos", json=novo_voto(), headers=urna)
    texto = cliente.get("/metrics", auth=ADMIN).text
    assert 'veredicto_votos_total{origem="urna"} 1' in texto
    assert 'veredicto_latencia_voto_ms{quantil="95"}' in texto
    assert "veredicto_urnas_ativas 1" in texto

def test_reserva_que_nunca_conectou_nao_conta_como_fora_do_ar(cliente):
    cliente.post("/api/admin/urnas", json={"id": "reserva1", "nome": "Reserva", "reserva": True}, auth=ADMIN)
    assert cliente.get("/api/admin/metricas", auth=ADMIN).json()["urnas"] == {"online": 0, "ativas": 0}
