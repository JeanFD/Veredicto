"""Cronômetro das falas, exibido no telão.

O mesário dá um título ("Tréplica — Defesa") e os minutos. O estado fica numa linha
só do banco e vai pelo WebSocket ao telão e ao painel, que contam os segundos
localmente entre uma mensagem e outra; o servidor reenvia a cada poucos segundos,
então uma tela recarregada no meio da fala pega o tempo certo.

Esgotado o tempo, o relógio não para: `restante` fica negativo e as telas mostram
quanto passou, em vermelho, até o mesário encerrar.
"""
import time

from app.db import db


def agora_s() -> float:
    return time.time()


def ler() -> dict:
    c = db.execute("SELECT * FROM cronometro WHERE id = 1").fetchone()
    restante = c["fim_em"] - agora_s() if c["rodando"] else c["restante"]
    return {
        "titulo": c["titulo"],
        "restante": round(restante, 1),
        "rodando": bool(c["rodando"]),
        "visivel": bool(c["visivel"]),
    }


def gravar(**campos) -> dict:
    with db:
        db.execute(f"UPDATE cronometro SET {', '.join(f'{c} = ?' for c in campos)} WHERE id = 1",
                   tuple(campos.values()))
    return ler()


def iniciar(titulo: str, minutos: float) -> dict:
    segundos = minutos * 60
    return gravar(titulo=titulo, restante=segundos, fim_em=agora_s() + segundos, rodando=1, visivel=1)


def pausar() -> dict:
    atual = ler()
    return gravar(restante=atual["restante"], rodando=0) if atual["rodando"] else atual


def retomar() -> dict:
    atual = ler()
    return atual if atual["rodando"] else gravar(fim_em=agora_s() + atual["restante"], rodando=1)


def ajustar(segundos: int) -> dict:
    """Soma (ou tira) tempo da contagem, parada ou correndo."""
    restante = ler()["restante"] + segundos
    return gravar(restante=restante, fim_em=agora_s() + restante)


def encerrar() -> dict:
    return gravar(rodando=0, visivel=0, restante=0)
