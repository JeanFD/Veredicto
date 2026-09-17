import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import ADMIN_SENHA
from app.db import db

basic = HTTPBasic(auto_error=False)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def senha_correta(senha: str) -> bool:
    return secrets.compare_digest(senha.encode(), ADMIN_SENHA.encode())

async def exigir_admin(cred: HTTPBasicCredentials | None = Depends(basic)):
    if cred is None or not senha_correta(cred.password):
        raise HTTPException(status_code=401, detail="Não autorizado")

async def exigir_urna(x_urna_token: str = Header(...)) -> str:
    linha = db.execute(
        "SELECT id FROM urnas WHERE token_hash = ? AND ativa = 1",
        (hash_token(x_urna_token),),
    ).fetchone()
    if not linha:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return linha["id"]