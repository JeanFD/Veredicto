"""Contas do painel: cada pessoa entra com usuário e senha próprios.

Papéis, do menor para o maior:
- monitor: só acompanha o status das urnas e as métricas;
- mesario: conduz as sessões e cadastra urnas;
- admin: tudo, inclusive contas, zerar contagem e limpar testes.

A primeira conta, "admin", nasce da ADMIN_SENHA quando ainda não há nenhuma; depois
a senha é trocada pelo painel. Esqueceu a senha do admin? No servidor:

    docker compose exec veredicto python -m app.contas redefinir admin
"""
import getpass
import hashlib
import secrets
import sys
import time

from app.config import ADMIN_SENHA
from app.db import agora, db

PAPEIS = {"monitor": 1, "mesario": 2, "admin": 3}
VALIDADE_LOGIN = 12 * 3600
SENHA_MINIMA = 8
# scrypt com 16 MiB de memória: caro para quem tenta adivinhar, ~50 ms para quem entra
CUSTO = {"n": 2**14, "r": 8, "p": 1}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    return f"scrypt${sal.hex()}${hashlib.scrypt(senha.encode(), salt=sal, **CUSTO).hex()}"


def confere(senha: str, guardado: str) -> bool:
    _, sal, esperado = guardado.split("$")
    calculado = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), **CUSTO).hex()
    return secrets.compare_digest(calculado, esperado)


# usuário inexistente custa o mesmo tempo que senha errada: o tempo não revela quem existe
_HASH_FALSO = gerar_hash(secrets.token_urlsafe(16))
# senhas já conferidas neste processo (por HTTP Basic, a cada pedido de scripts):
# vale enquanto o hash guardado for o mesmo, isto é, até a senha ser trocada
_conferidas: dict[tuple[str, str], str] = {}


def conta_por_senha(usuario: str, senha: str):
    conta = db.execute("SELECT * FROM contas WHERE usuario = ? AND ativa = 1", (usuario.lower(),)).fetchone()
    if not conta:
        confere(senha, _HASH_FALSO)
        return None
    chave = (conta["usuario"], hash_token(senha))
    if _conferidas.get(chave) != conta["senha_hash"]:
        if not confere(senha, conta["senha_hash"]):
            return None
        if len(_conferidas) > 1000:
            _conferidas.clear()
        _conferidas[chave] = conta["senha_hash"]
    return conta


def abrir_login(usuario: str) -> tuple[str, float]:
    token = secrets.token_urlsafe(32)
    expira = time.time() + VALIDADE_LOGIN
    with db:
        db.execute("DELETE FROM logins WHERE expira_em < ?", (time.time(),))
        db.execute("INSERT INTO logins (token_hash, usuario, expira_em) VALUES (?, ?, ?)",
                   (hash_token(token), usuario, expira))
    return token, expira


def conta_do_token(token: str):
    return db.execute(
        "SELECT c.* FROM logins l JOIN contas c ON c.usuario = l.usuario "
        "WHERE l.token_hash = ? AND l.expira_em > ? AND c.ativa = 1",
        (hash_token(token), time.time()),
    ).fetchone()


def encerrar_login(token: str):
    with db:
        db.execute("DELETE FROM logins WHERE token_hash = ?", (hash_token(token),))


def encerrar_logins(usuario: str, exceto: str | None = None):
    """Derruba os logins da conta (senha trocada, conta desativada), menos o de quem trocou."""
    with db:
        db.execute("DELETE FROM logins WHERE usuario = ? AND token_hash IS NOT ?",
                   (usuario, hash_token(exceto) if exceto else None))


def trocar_senha(usuario: str, nova: str, exceto: str | None = None):
    with db:
        db.execute("UPDATE contas SET senha_hash = ? WHERE usuario = ?", (gerar_hash(nova), usuario))
    encerrar_logins(usuario, exceto)


def criar_conta(usuario: str, nome: str, papel: str, senha: str):
    with db:
        db.execute(
            "INSERT INTO contas (usuario, nome, papel, senha_hash, criada_em) VALUES (?, ?, ?, ?, ?)",
            (usuario.lower(), nome, papel, gerar_hash(senha), agora()),
        )


def admins_ativos() -> int:
    return db.execute("SELECT COUNT(*) FROM contas WHERE papel = 'admin' AND ativa = 1").fetchone()[0]


def criar_admin_inicial():
    if ADMIN_SENHA and not db.execute("SELECT 1 FROM contas").fetchone():
        criar_conta("admin", "Administrador", "admin", ADMIN_SENHA)


criar_admin_inicial()


def principal(argv: list[str]):
    if len(argv) != 2 or argv[0] != "redefinir":
        sys.exit("uso: python -m app.contas redefinir <usuario>")
    usuario = argv[1].lower()
    if not db.execute("SELECT 1 FROM contas WHERE usuario = ?", (usuario,)).fetchone():
        sys.exit(f"conta {usuario!r} não existe")
    nova = getpass.getpass("Nova senha: ")
    if len(nova) < SENHA_MINIMA:
        sys.exit(f"a senha precisa de pelo menos {SENHA_MINIMA} caracteres")
    if getpass.getpass("Repita a senha: ") != nova:
        sys.exit("as senhas não conferem")
    with db:
        db.execute("UPDATE contas SET ativa = 1 WHERE usuario = ?", (usuario,))
    trocar_senha(usuario, nova)
    print(f"senha de {usuario} redefinida; os logins abertos foram encerrados")


if __name__ == "__main__":
    principal(sys.argv[1:])
