import hashlib
import hmac
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.i18n import msg
from app.compartilhado import falhas
from app.config import ADMIN_SENHA
from app.contas import PAPEIS, conta_do_token, conta_por_senha, hash_token  # noqa: F401 (hash_token reexportado)
from app.db import db, responsavel

basic = HTTPBasic(auto_error=False)


def bloqueado(ip: str) -> bool:
    return falhas.bloqueado(ip)


def registrar_falha(ip: str):
    falhas.registrar(ip)


def recusar_senha(ip: str):
    """Senha errada: conta para o bloqueio. A tela de login avisa quantas tentativas
    faltam e, ao bloquear, por quanto tempo."""
    registrar_falha(ip)
    cabecalhos = {"X-Tentativas-Restantes": str(falhas.restantes(ip))}
    if falhas.bloqueado(ip):
        cabecalhos["Retry-After"] = str(falhas.espera(ip))
    raise HTTPException(401, msg("nao_autorizado"), headers=cabecalhos)


def conta_com_senha(ip: str, usuario: str, senha: str):
    if bloqueado(ip):
        raise HTTPException(429, msg("muitas_tentativas"), headers={"Retry-After": str(falhas.espera(ip))})
    conta = conta_por_senha(usuario, senha)
    if not conta:
        recusar_senha(ip)
    return conta


def exigir(papel: str):
    """Acesso a partir do papel dado. O navegador manda o token do login (Bearer);
    scripts podem mandar usuário e senha (HTTP Basic). Token vencido não conta para o
    bloqueio: uma aba esquecida aberta não pode trancar o IP de todo mundo."""
    async def checar(request: Request, cred: HTTPBasicCredentials | None = Depends(basic)):
        cabecalho = request.headers.get("Authorization", "")
        if cabecalho.startswith("Bearer "):
            conta = conta_do_token(cabecalho.removeprefix("Bearer "))
            if not conta:
                raise HTTPException(401, msg("login_expirado"))
        elif cred:
            conta = conta_com_senha(request.client.host, cred.username, cred.password)
        else:
            raise HTTPException(401, msg("nao_autorizado"))
        if PAPEIS[conta["papel"]] < PAPEIS[papel]:
            raise HTTPException(403, msg("sem_permissao"))
        responsavel.set(conta["usuario"])
        return conta
    return checar


exigir_monitor = exigir("monitor")
exigir_mesario = exigir("mesario")
exigir_admin = exigir("admin")


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