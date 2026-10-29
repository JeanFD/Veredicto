"""Carga: N urnas votando ao mesmo tempo, com reenvios, e conferência voto a voto.

Cria uma sessão de teste própria ("Carga ..."), cadastra urnas de teste, abre a
votação e faz cada urna votar como a de verdade: repete o envio até o servidor
aceitar e, de vez em quando, reenvia um voto já aceito (resposta perdida no
caminho). No fim encerra, revela, baixa o CSV e confere que cada voto enviado
está lá exatamente uma vez. As urnas de carga são desativadas ao terminar, e
"Limpar testes" no painel do mesário apaga tudo o que a carga criou.

    python -m scripts.carga --url http://127.0.0.1:8000 --senha SENHA --urnas 20 --votos 50

Não rode durante uma votação de verdade: o script se recusa se houver uma
sessão aberta ou encerrada ainda não revelada.
"""
import argparse
import asyncio
import csv
import io
import random
import statistics
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

OPCOES = [{"rotulo": "Alfa", "cor": "#dc2626"}, {"rotulo": "Beta", "cor": "#2563eb"}]
# um voto que o servidor não aceita nesse prazo (rede ou servidor fora) é dado como perdido
PRAZO_ENTREGA = 120
# respostas que valem nova tentativa: proxy sem o servidor atrás ou servidor reiniciando
TRANSITORIOS = {502, 503, 504}


@dataclass
class Relatorio:
    enviados: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (urna, opcao)
    tentativas: int = 0
    reenvios: int = 0
    falhas_de_rede: int = 0
    latencias: list[float] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)
    segundos: float = 0.0

    def resumo(self) -> str:
        ms = sorted(self.latencias) or [0]
        linhas = [
            f"votos únicos:      {len(self.enviados)}",
            f"envios:            {self.tentativas} ({self.reenvios} reenvios de voto já aceito, "
            f"{self.falhas_de_rede} falhas de rede repetidas)",
            f"duração:           {self.segundos:.1f}s ({len(self.enviados) / max(self.segundos, 0.001):.1f} votos/s)",
            f"latência:          p50 {statistics.median(ms):.0f}ms · p95 {ms[min(len(ms) - 1, int(len(ms) * 0.95))]:.0f}ms"
            f" · máx {ms[-1]:.0f}ms",
        ]
        if self.problemas:
            linhas += ["", f"PROBLEMAS ({len(self.problemas)}):"] + [f"  - {p}" for p in self.problemas[:30]]
        else:
            linhas += ["", "OK: todo voto enviado está no servidor exatamente uma vez."]
        return "\n".join(linhas)


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def pedir(http: httpx.AsyncClient, metodo: str, caminho: str, prazo: float = PRAZO_ENTREGA, **kwargs):
    """Chamada do mesário, repetida enquanto o servidor estiver fora do ar."""
    limite = time.monotonic() + prazo
    while True:
        try:
            r = await http.request(metodo, caminho, **kwargs)
            if r.status_code not in TRANSITORIOS:
                r.raise_for_status()
                return r
        except httpx.TransportError:
            pass
        if time.monotonic() > limite:
            raise RuntimeError(f"{metodo} {caminho}: servidor fora do ar por mais de {prazo:.0f}s")
        await asyncio.sleep(0.5)


async def entregar(http, token: str, voto: dict, rel: Relatorio):
    """Como a fila da urna: tenta de novo até o servidor responder."""
    espera = 0.2
    limite = time.monotonic() + PRAZO_ENTREGA
    while True:
        rel.tentativas += 1
        inicio = time.perf_counter()
        try:
            r = await http.post("/api/votos", json=voto, headers={"X-Urna-Token": token})
            if r.status_code == 200:
                rel.latencias.append((time.perf_counter() - inicio) * 1000)
                return
            if r.status_code not in TRANSITORIOS:
                rel.problemas.append(f"voto {voto['id']} recusado: {r.status_code} {r.text[:120]}")
                return
        except httpx.TransportError:
            pass
        rel.falhas_de_rede += 1
        if time.monotonic() > limite:
            rel.problemas.append(f"voto {voto['id']} não entregue em {PRAZO_ENTREGA}s")
            return
        await asyncio.sleep(espera)
        espera = min(espera * 2, 2)


async def votar_pela_urna(http, uid, token, sid, chaves, votos, reenvio, intervalo, rnd, rel):
    aceitos = []
    for _ in range(votos):
        voto = {"id": str(uuid.uuid4()), "sessao_id": sid, "opcao": rnd.choice(chaves), "votado_em": agora()}
        rel.enviados[voto["id"]] = (uid, voto["opcao"])
        await entregar(http, token, voto, rel)
        aceitos.append(voto)
        if rnd.random() < reenvio:
            rel.reenvios += 1
            await entregar(http, token, rnd.choice(aceitos), rel)
        await asyncio.sleep(rnd.uniform(0, 2 * intervalo))


def conferir(csv_texto: str, rel: Relatorio):
    linhas = list(csv.DictReader(io.StringIO(csv_texto)))
    contagem = Counter(l["id"] for l in linhas)
    for vid, n in contagem.items():
        if n > 1:
            rel.problemas.append(f"voto {vid} duplicado ({n}x)")
        if vid not in rel.enviados:
            rel.problemas.append(f"voto {vid} no servidor, mas não foi enviado pela carga")
    for vid in rel.enviados.keys() - contagem.keys():
        rel.problemas.append(f"voto {vid} perdido")
    for l in linhas:
        esperado = rel.enviados.get(l["id"])
        if esperado and esperado != (l["urna_id"], l["opcao"]):
            rel.problemas.append(f"voto {l['id']} gravado como {l['urna_id']}/{l['opcao']}, enviado como {esperado}")


async def executar(http: httpx.AsyncClient, urnas=10, votos=30, reenvio=0.2, intervalo=0.05,
                   semente=None, votando: asyncio.Event | None = None) -> Relatorio:
    """`http` já autenticado como mesário. `votando` é sinalizado quando a votação abre."""
    rnd = random.Random(semente)
    rel = Relatorio()

    ativa = (await pedir(http, "GET", "/api/sessao/ativa")).json()["sessao"]
    if ativa and ativa["estado"] in ("ABERTA", "ENCERRADA"):
        raise SystemExit(f'Há uma votação em andamento ("{ativa["tema"]}", {ativa["estado"]}): carga cancelada.')

    marca = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    sid = (await pedir(http, "POST", "/api/admin/sessoes",
                       json={"tema": f"Carga {marca}", "opcoes": OPCOES, "teste": True})).json()["id"]
    cadastradas = []
    for i in range(urnas):
        uid = f"carga-{marca[-4:]}-{i:03d}"
        token = (await pedir(http, "POST", "/api/admin/urnas",
                             json={"id": uid, "nome": f"Carga {i}", "reserva": True, "teste": True})).json()["token"]
        cadastradas.append((uid, token))
    try:
        await pedir(http, "POST", f"/api/admin/sessoes/{sid}/ativar")
        await pedir(http, "POST", f"/api/admin/sessoes/{sid}/avancar")  # ABERTA
        chaves = [o["chave"] for o in (await pedir(http, "GET", "/api/sessao/ativa")).json()["sessao"]["opcoes"]]
        if votando:
            votando.set()

        inicio = time.monotonic()
        await asyncio.gather(*(
            votar_pela_urna(http, uid, token, sid, chaves, votos, reenvio, intervalo,
                            random.Random(rnd.random()), rel)
            for uid, token in cadastradas
        ))
        rel.segundos = time.monotonic() - inicio

        await pedir(http, "POST", f"/api/admin/sessoes/{sid}/avancar")  # ENCERRADA
        await pedir(http, "POST", f"/api/admin/sessoes/{sid}/avancar", params={"forcar": "true"})  # REVELADA
        conferir((await pedir(http, "GET", f"/api/admin/sessoes/{sid}/votos.csv")).text, rel)
    finally:
        for uid, _ in cadastradas:
            await pedir(http, "POST", f"/api/admin/urnas/{uid}/desativar")
    return rel


def argumentos(parser: argparse.ArgumentParser):
    parser.add_argument("--urnas", type=int, default=10, help="urnas votando ao mesmo tempo (padrão 10)")
    parser.add_argument("--votos", type=int, default=30, help="votos por urna (padrão 30)")
    parser.add_argument("--reenvio", type=float, default=0.2,
                        help="chance de reenviar um voto já aceito após cada voto (padrão 0.2)")
    parser.add_argument("--intervalo", type=float, default=0.05, help="pausa média entre votos de uma urna, em s")
    parser.add_argument("--semente", type=int, help="semente aleatória, para repetir uma execução")


def cliente(url: str, senha: str) -> httpx.AsyncClient:
    limites = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    return httpx.AsyncClient(base_url=url, auth=("mesario", senha), timeout=10, limits=limites)


async def principal(args) -> int:
    async with cliente(args.url, args.senha) as http:
        rel = await executar(http, args.urnas, args.votos, args.reenvio, args.intervalo, args.semente)
    print(rel.resumo())
    return 1 if rel.problemas else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="endereço do Veredicto, ex.: https://veredicto.exemplo")
    parser.add_argument("--senha", required=True, help="senha do mesário")
    argumentos(parser)
    sys.exit(asyncio.run(principal(parser.parse_args())))
