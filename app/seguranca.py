import hashlib
import secrets
import time
from collections import defaultdict

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import ADMIN_SENHA
from app.db import db

basic = HTTPBasic(auto_error=False)

MAX_FALHAS = 10
JANELA_SEGUNDOS = 300
falhas: dict[str, list[float]] = defaultdict(list)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def senha_correta(senha: str) -> bool:
    return secrets.compare_digest(senha.encode(), ADMIN_SENHA.encode())


def bloqueado(ip: str) -> bool:
    agora = time.monotonic()
    falhas[ip] = [t for t in falhas[ip] if agora - t < JANELA_SEGUNDOS]
    return len(falhas[ip]) >= MAX_FALHAS


def registrar_falha(ip: str):
    falhas[ip].append(time.monotonic())


async def exigir_admin(request: Request, cred: HTTPBasicCredentials | None = Depends(basic)):
    ip = request.client.host
    if bloqueado(ip):
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    if cred is None or not senha_correta(cred.password):
        registrar_falha(ip)
        raise HTTPException(401, "Não autorizado")


async def exigir_urna(x_urna_token: str = Header(...)) -> str:
    linha = db.execute(
        "SELECT id FROM urnas WHERE token_hash = ? AND ativa = 1",
        (hash_token(x_urna_token),),
    ).fetchone()
    if not linha:
        raise HTTPException(401, "Urna não autorizada")
    return linha["id"]