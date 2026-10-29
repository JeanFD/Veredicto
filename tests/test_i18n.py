"""Traduções: as chaves faltantes aparecem aqui, não na tela de quem vota."""
import json
import re
from pathlib import Path

import pytest

from app.i18n import IDIOMAS, MENSAGENS, idioma_do_cabecalho
from tests.auxiliares import ADMIN, novo_voto

STATIC = Path(__file__).resolve().parent.parent / "static"
TELAS = ["urna", "telao", "celular", "mesario", "auditoria", "monitor", "."]
ESTADOS = ["AGUARDANDO", "ABERTA", "ENCERRADA", "REVELADA"]

# chaves montadas em tempo de execução (t(`estado.${...}`) etc.)
DINAMICAS = (
    [f"estado.{e}" for e in ESTADOS]
    + [f"telao.legenda.{e}" for e in ESTADOS if e != "REVELADA"]
    + [f"urna.recusa.{m}" for m in ("sessao_encerrada", "sessao_nao_aberta", "outra")]
    + [f"celular.motivo.{m}" for m in
       ("codigo_expirado", "sessao_fechada", "sessao_inexistente", "cedula_invalida", "ja_votou", "cedula_usada")]
    + [f"mesario.motivo.{m}" for m in
       ("sessao_encerrada", "sessao_nao_aberta", "sessao_inexistente", "opcao_invalida", "urna_de_teste")]
)

def textos():
    fonte = (STATIC / "i18n.js").read_text(encoding="utf-8")
    trecho = fonte.split("/* textos:inicio */")[1].split("/* textos:fim */")[0]
    return json.loads(trecho)

def campos(texto):
    return sorted(re.findall(r"\{(\w+)\}", texto))

def chaves_usadas(citadas=False):
    """Chaves passadas a t() e nos atributos data-i18n; com citadas=True, também
    as que aparecem como texto no código (ex.: t(fechada ? "urna.fechada" : ...))."""
    usadas = set()
    for tela in TELAS:
        for arquivo in (STATIC / tela).glob("*.*"):
            # o próprio dicionário não conta: nele toda chave aparece entre aspas
            if arquivo.suffix not in (".js", ".html") or arquivo.name == "i18n.js":
                continue
            fonte = arquivo.read_text(encoding="utf-8")
            usadas |= set(re.findall(r'\bt\(\s*"([\w.]+)"', fonte))
            usadas |= set(re.findall(r'data-i18n(?:-placeholder)?="([\w.]+)"', fonte))
            if citadas:
                usadas |= set(re.findall(r'"([a-z]+\.[\w.]+)"', fonte))
    return usadas

# ---------- frontend ----------
def test_mesmas_chaves_em_todos_os_idiomas():
    t = textos()
    assert set(t) == {"pt", "en"}
    assert set(t["pt"]) - set(t["en"]) == set(), "faltam em inglês"
    assert set(t["en"]) - set(t["pt"]) == set(), "faltam em português"

def test_traducoes_preenchidas_e_com_os_mesmos_campos():
    t = textos()
    for chave, pt in t["pt"].items():
        assert pt.strip() and t["en"][chave].strip(), chave
        assert campos(pt) == campos(t["en"][chave]), chave

def test_toda_chave_usada_nas_telas_existe():
    usadas = chaves_usadas()
    assert len(usadas) > 50  # o regex achou as chaves de verdade
    faltando = (usadas | set(DINAMICAS)) - set(textos()["pt"])
    assert faltando == set()

def test_nenhuma_chave_sobrando():
    sobrando = set(textos()["pt"]) - chaves_usadas(citadas=True) - set(DINAMICAS) - {"comum.trocar_idioma"}
    assert sobrando == set()

@pytest.mark.parametrize("tela", TELAS)
def test_tela_carrega_as_traducoes_antes_do_proprio_script(tela):
    html = (STATIC / tela / "index.html").read_text(encoding="utf-8")
    proprio = re.search(r'<script src="(\w+)\.js\?v=\d+"></script>', html)
    assert re.search(r'<script src="/i18n\.js\?v=\d+"></script>', html)
    if proprio:  # a página inicial não tem script próprio
        assert html.index("/i18n.js") < proprio.start()

# ---------- backend ----------
def test_mensagens_do_servidor_nos_dois_idiomas():
    for chave, textos_ in MENSAGENS.items():
        assert set(textos_) == set(IDIOMAS), chave
        assert all(textos_[i].strip() for i in IDIOMAS), chave
        assert campos(textos_["pt"]) == campos(textos_["en"]), chave

@pytest.mark.parametrize("cabecalho, idioma", [
    ("en", "en"), ("en-US,en;q=0.9", "en"), ("pt-BR,pt;q=0.9,en;q=0.8", "pt"), ("fr", "pt"), (None, "pt"),
])
def test_idioma_do_cabecalho(cabecalho, idioma):
    assert idioma_do_cabecalho(cabecalho) == idioma

def test_recusa_no_idioma_pedido_mantem_o_motivo(cliente, urna):
    voto = novo_voto()
    pt = cliente.post("/api/votos", json=voto, headers=urna).json()["detail"]
    en = cliente.post("/api/votos", json=voto, headers={**urna, "Accept-Language": "en"}).json()["detail"]
    assert pt == {"motivo": "sessao_nao_aberta", "mensagem": "Sessão ainda não foi aberta"}
    assert en == {"motivo": "sessao_nao_aberta", "mensagem": "Session not open yet"}

def test_erro_de_autenticacao_traduzido(cliente):
    r = cliente.get("/api/admin/sessoes", auth=("mesario", "errada"), headers={"Accept-Language": "en"})
    assert r.status_code == 401 and r.json()["detail"] == "Unauthorized"

def test_pendencias_traduzidas_e_auditoria_em_portugues(cliente, urna):
    from app.db import db
    cliente.post("/api/admin/sessoes/1/ativar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN)
    cliente.post("/api/urnas/heartbeat", json={"pendentes": 2}, headers=urna)
    en = {"Accept-Language": "en"}
    r = cliente.post("/api/admin/sessoes/1/avancar", auth=ADMIN, headers=en)
    assert r.status_code == 409
    assert r.json()["detail"]["mensagem"] == "There are pending issues"
    assert r.json()["detail"]["problemas"][0].endswith(": 2 pending votes")

    assert cliente.post("/api/admin/sessoes/1/avancar?forcar=true", auth=ADMIN, headers=en).status_code == 200
    [detalhe] = db.execute("SELECT detalhe FROM eventos WHERE tipo = 'revelacao_forcada'").fetchone()
    assert detalhe.endswith(": 2 votos pendentes")
