import hashlib
import hmac
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.i18n import msg
from app.compartilhado import falhas
from app.config import ADMIN_SENHA
from app.db import db

basic = HTTPBasic(auto_error=False)



def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def senha_correta(senha: str) -> bool:
    return secrets.compare_digest(senha.encode(), ADMIN_SENHA.encode())


def bloqueado(ip: str) -> bool:
    return falhas.bloqueado(ip)


def registrar_falha(ip: str):
    falhas.registrar(ip)


async def exigir_admin(request: Request, cred: HTTPBasicCredentials | None = Depends(basic)) -> str:
    ip = request.client.host
    if bloqueado(ip):
        raise HTTPException(429, msg("muitas_tentativas"))
    if cred is None or not senha_correta(cred.password):
        registrar_falha(ip)
        raise HTTPException(401, msg("nao_autorizado"))
    # a senha é compartilhada: o IP é o que distingue quem agiu na auditoria
    return f"{cred.username}@{ip}"


# ---------- Voto por celular ----------
# O QR do telão traz um código que muda a cada JANELA_CODIGO segundos; aceitar
# também a janela anterior evita recusar quem escaneou na virada.
JANELA_CODIGO = 30


def _assinar(texto: str) -> str:
    return hmac.new(ADMIN_SENHA.encode(), texto.encode(), hashlib.sha256).hexdigest()


def chave_telao() -> str:
    return _assinar("telao")[:32]


def janela_atual() -> int:
    return int(time.time() // JANELA_CODIGO)


def codigo_celular(sessao_id: int, janela: int) -> str:
    return _assinar(f"celular:{sessao_id}:{janela}")[:10]


def codigo_valido(sessao_id: int, codigo: str) -> bool:
    janela = janela_atual()
    return any(
        secrets.compare_digest(codigo.encode(), codigo_celular(sessao_id, j).encode())
        for j in (janela, janela - 1)
    )


async def exigir_telao(x_telao_chave: str = Header("")):
    # sem a chave, qualquer um leria o código de casa e votaria sem estar no local
    if not secrets.compare_digest(x_telao_chave.encode(), chave_telao().encode()):
        raise HTTPException(401, msg("telao_nao_autorizado"))


async def exigir_urna(x_urna_token: str = Header(...)) -> str:
    linha = db.execute(
        "SELECT id FROM urnas WHERE token_hash = ? AND ativa = 1",
        (hash_token(x_urna_token),),
    ).fetchone()
    if not linha:
        raise HTTPException(401, msg("urna_nao_autorizada"))
    return linha["id"]