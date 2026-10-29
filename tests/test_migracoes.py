import sqlite3

import app.config
from app.migrar import backup, migrar, pendente, principal

# o que a aplicação espera encontrar depois das migrações
ESQUEMA = {
    "sessoes": {"id", "tema", "estado", "ativa", "encerrada_em", "arquivada", "grupo_id", "pergunta", "teste", "celular"},
    "opcoes": {"id", "sessao_id", "chave", "rotulo", "cor", "ordem"},
    "urnas": {"id", "nome", "token_hash", "ativa", "reserva", "criada_em", "teste"},
    "votos": {"id", "sessao_id", "urna_id", "opcao_chave", "votado_em", "recebido_em"},
    "eventos": {"id", "tipo", "detalhe", "em"},
    "cedulas": {"token_hash", "sessao_id", "criada_em", "voto_id", "seguinte_emitida"},
    "pedidos_urna": {"segredo_hash", "codigo", "criado_em", "urna_id", "token"},
    "contas": {"usuario", "nome", "papel", "senha_hash", "ativa", "criada_em"},
    "logins": {"token_hash", "usuario", "expira_em"},
}

def esquema(conexao):
    tabelas = [t[0] for t in conexao.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {t: {c[1] for c in conexao.execute(f"PRAGMA table_info({t})")}
            for t in tabelas if t != "alembic_version"}

def versao(conexao):
    return conexao.execute("SELECT version_num FROM alembic_version").fetchone()[0]

def banco_antigo(caminho=":memory:"):
    """Banco criado antes do Alembic, de antes de arquivar, questionário e celular."""
    conexao = sqlite3.connect(caminho)
    conexao.executescript("""
        CREATE TABLE sessoes (id INTEGER PRIMARY KEY, tema TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'AGUARDANDO', ativa INTEGER NOT NULL DEFAULT 0, encerrada_em TEXT);
        CREATE TABLE opcoes (id INTEGER PRIMARY KEY, sessao_id INTEGER NOT NULL, chave TEXT NOT NULL,
            rotulo TEXT NOT NULL, cor TEXT NOT NULL, ordem INTEGER NOT NULL, UNIQUE (sessao_id, chave));
        CREATE TABLE urnas (id TEXT PRIMARY KEY, nome TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
            ativa INTEGER NOT NULL DEFAULT 1, reserva INTEGER NOT NULL DEFAULT 0, criada_em TEXT NOT NULL);
        CREATE TABLE votos (id TEXT PRIMARY KEY, sessao_id INTEGER NOT NULL, urna_id TEXT NOT NULL,
            opcao_chave TEXT NOT NULL, votado_em TEXT NOT NULL, recebido_em TEXT NOT NULL);
        CREATE TABLE eventos (id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, detalhe TEXT NOT NULL DEFAULT '',
            em TEXT NOT NULL);
        INSERT INTO sessoes (tema, estado, ativa) VALUES ('Sessão antiga', 'REVELADA', 1);
        INSERT INTO urnas VALUES ('u1', 'Entrada', 'hash', 1, 0, '2026-01-01');
        INSERT INTO votos VALUES ('v1', 1, 'u1', 'defesa', '2026-01-01', '2026-01-01');
    """)
    conexao.commit()
    return conexao

def test_banco_novo_fica_com_o_esquema_da_app():
    conexao = sqlite3.connect(":memory:")
    migrar(conexao)
    assert esquema(conexao) == ESQUEMA
    assert versao(conexao) == "0005"
    assert not pendente(conexao)

def test_banco_antigo_e_adotado_sem_perder_dados():
    conexao = banco_antigo()
    assert pendente(conexao)
    migrar(conexao)
    assert esquema(conexao) == ESQUEMA
    assert conexao.execute("SELECT tema, estado, arquivada, grupo_id, pergunta FROM sessoes").fetchall() == [
        ("Sessão antiga", "REVELADA", 0, None, 1),
    ]
    assert conexao.execute("SELECT id, opcao_chave FROM votos").fetchall() == [("v1", "defesa")]
    assert versao(conexao) == "0005"

def test_migrar_de_novo_nao_muda_nada():
    conexao = banco_antigo()
    migrar(conexao)
    antes = conexao.execute("SELECT * FROM votos").fetchall()
    migrar(conexao)
    assert conexao.execute("SELECT * FROM votos").fetchall() == antes
    assert not pendente(conexao)

def test_backup_copia_os_dados(tmp_path):
    caminho = tmp_path / "veredicto.db"
    conexao = banco_antigo(caminho)
    copia = sqlite3.connect(backup(conexao, str(caminho)))
    assert copia.execute("SELECT id FROM votos").fetchall() == [("v1",)]

def test_comando_do_deploy_faz_backup_so_quando_ha_migracao(tmp_path, monkeypatch, capsys):
    caminho = tmp_path / "veredicto.db"
    banco_antigo(caminho).close()
    monkeypatch.setattr(app.config, "DB_PATH", str(caminho))

    principal()
    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1
    assert sqlite3.connect(backups[0]).execute("SELECT COUNT(*) FROM votos").fetchone()[0] == 1
    assert esquema(sqlite3.connect(caminho)) == ESQUEMA

    principal()
    assert len(list((tmp_path / "backups").iterdir())) == 1
    assert "já está na última migração" in capsys.readouterr().out
