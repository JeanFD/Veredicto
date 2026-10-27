"""Caos: a carga de scripts/carga.py rodando enquanto o servidor cai.

Local (padrão): sobe um Veredicto num banco temporário e o derruba com kill
no meio da votação, várias vezes, subindo de novo em seguida.

    python -m scripts.caos --quedas 3

Na VPS: a queda é um comando seu (rodado pelo shell), e --vigiar confere a cada
segundo que os outros serviços da máquina seguem no ar durante o teste todo.

    python -m scripts.caos --url https://veredicto.exemplo --senha SENHA \\
        --falha "ssh vps 'cd /opt/veredicto && docker compose kill veredicto && docker compose up -d veredicto'" \\
        --vigiar https://jogo.exemplo --vigiar https://vibemetrics.exemplo

Passa quando nenhum voto se perdeu nem duplicou e nenhum serviço vigiado caiu.
"""
import argparse
import asyncio
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

import httpx

from scripts import carga


@dataclass
class Vigia:
    url: str
    checagens: int = 0
    falhas: list[str] = field(default_factory=list)


async def vigiar(vigias: list[Vigia], parar: asyncio.Event):
    async with httpx.AsyncClient(timeout=5, follow_redirects=True) as http:
        while not parar.is_set():
            for v in vigias:
                v.checagens += 1
                try:
                    r = await http.get(v.url)
                    if r.status_code >= 400:
                        v.falhas.append(f"{time.strftime('%H:%M:%S')} HTTP {r.status_code}")
                except httpx.TransportError as e:
                    v.falhas.append(f"{time.strftime('%H:%M:%S')} {type(e).__name__}")
            try:
                await asyncio.wait_for(parar.wait(), 1)
            except asyncio.TimeoutError:
                pass


class ServidorLocal:
    """Um uvicorn de verdade, que pode ser morto (kill, sem desligar com calma) e subir de novo."""

    def __init__(self):
        self.pasta = tempfile.mkdtemp(prefix="veredicto-caos-")
        self.senha = secrets.token_urlsafe(12)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.porta = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.porta}"
        self.processo = None

    def subir(self):
        ambiente = {**os.environ, "ADMIN_SENHA": self.senha, "DB_PATH": os.path.join(self.pasta, "caos.db")}
        ambiente.pop("REDIS_URL", None)
        self.processo = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.porta)],
            env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(150):
            try:
                httpx.get(f"{self.url}/api/sessao/ativa", timeout=1)
                return
            except httpx.TransportError:
                time.sleep(0.1)
        raise RuntimeError("o servidor local não subiu")

    def matar(self):
        self.processo.kill()
        self.processo.wait()

    def desligar(self):
        if self.processo and self.processo.poll() is None:
            self.processo.terminate()
            self.processo.wait(timeout=10)
        shutil.rmtree(self.pasta, ignore_errors=True)


async def derrubar(falhar, quedas: int, espera: float, votando: asyncio.Event, fim: asyncio.Task) -> int:
    """Derruba o servidor `quedas` vezes enquanto a carga roda; devolve quantas aconteceram."""
    await votando.wait()
    feitas = 0
    for _ in range(quedas):
        await asyncio.sleep(espera)
        if fim.done():
            break
        print(f"[caos] {time.strftime('%H:%M:%S')} derrubando o servidor ({feitas + 1}/{quedas})", flush=True)
        await falhar()
        feitas += 1
    return feitas


async def executar(url, senha, falhar, quedas=3, espera=2.0, vigiar_urls=(), **opcoes_carga):
    votando = asyncio.Event()
    parar = asyncio.Event()
    vigias = [Vigia(u) for u in vigiar_urls]
    tarefa_vigia = asyncio.create_task(vigiar(vigias, parar))
    try:
        async with carga.cliente(url, senha) as http:
            tarefa_carga = asyncio.create_task(carga.executar(http, votando=votando, **opcoes_carga))
            feitas = await derrubar(falhar, quedas, espera, votando, tarefa_carga)
            rel = await tarefa_carga
    finally:
        parar.set()
        await tarefa_vigia
    return rel, feitas, vigias


def relatorio(rel, feitas, quedas, vigias) -> tuple[str, bool]:
    ok = not rel.problemas
    linhas = [rel.resumo(), "", f"quedas do servidor: {feitas} de {quedas}"]
    if feitas < quedas:
        linhas.append("  (a carga terminou antes; aumente --votos para caberem todas as quedas)")
    for v in vigias:
        if v.falhas:
            ok = False
            linhas.append(f"FORA DO AR: {v.url} falhou {len(v.falhas)} de {v.checagens} checagens: "
                          + ", ".join(v.falhas[:10]))
        else:
            linhas.append(f"no ar o tempo todo: {v.url} ({v.checagens} checagens)")
    return "\n".join(linhas), ok


async def principal(args) -> int:
    opcoes = dict(urnas=args.urnas, votos=args.votos, reenvio=args.reenvio,
                  intervalo=args.intervalo, semente=args.semente)
    if args.url:
        async def falhar():
            proc = await asyncio.create_subprocess_shell(args.falha)
            if await proc.wait():
                print(f"[caos] o comando de falha saiu com código {proc.returncode}", flush=True)
        rel, feitas, vigias = await executar(args.url, args.senha, falhar, args.quedas, args.espera,
                                             args.vigiar, **opcoes)
    else:
        servidor = ServidorLocal()
        servidor.subir()

        async def falhar():
            servidor.matar()
            await asyncio.sleep(args.fora)
            await asyncio.to_thread(servidor.subir)
        try:
            rel, feitas, vigias = await executar(servidor.url, servidor.senha, falhar, args.quedas, args.espera,
                                                 args.vigiar, **opcoes)
        finally:
            servidor.desligar()
    texto, ok = relatorio(rel, feitas, args.quedas, vigias)
    print(texto)
    return 0 if ok and feitas else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="Veredicto remoto; sem isto, sobe um servidor local e o derruba com kill")
    parser.add_argument("--senha", help="senha do mesário (com --url)")
    parser.add_argument("--falha", help="comando de shell que derruba o servidor remoto (com --url)")
    parser.add_argument("--vigiar", action="append", default=[], metavar="URL",
                        help="serviço que deve seguir no ar durante o teste (pode repetir)")
    parser.add_argument("--quedas", type=int, default=3, help="quantas vezes derrubar o servidor (padrão 3)")
    parser.add_argument("--espera", type=float, default=2.0, help="segundos de votação entre uma queda e outra")
    parser.add_argument("--fora", type=float, default=1.0, help="segundos fora do ar em cada queda local")
    carga.argumentos(parser)
    parser.set_defaults(votos=60, intervalo=0.1)
    args = parser.parse_args()
    if args.url and not (args.senha and args.falha):
        parser.error("com --url, informe também --senha e --falha")
    sys.exit(asyncio.run(principal(args)))
