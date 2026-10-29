"""Estado que precisa valer para todos os processos quando há mais de um.

Sem REDIS_URL (o padrão, e como roda em produção hoje): um processo só e tudo
em memória, como sempre foi. Com REDIS_URL: os eventos de WebSocket passam por
Redis pub/sub (app/ws.py) e o estado abaixo fica no Redis, para que qualquer
processo veja o mesmo heartbeat de urna, o mesmo bloqueio de login e as mesmas
métricas. O estado das sessões já é compartilhado: fica no SQLite.
"""
import math
import time
from collections import defaultdict

from app.config import REDIS_URL

PREFIXO = "veredicto:"

def conectar_sync():
    import redis
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)

def conectar_async():
    import redis.asyncio
    return redis.asyncio.Redis.from_url(REDIS_URL, decode_responses=True)

redis_sync = conectar_sync() if REDIS_URL else None

# ---------- Heartbeat das urnas ----------
class SinaisMemoria:
    def __init__(self):
        self.sinais: dict[str, dict] = {}

    def registrar(self, urna: str, pendentes: int, recusados: int):
        self.sinais[urna] = {"em": time.monotonic(), "pendentes": pendentes, "recusados": recusados}

    def obter(self, urna: str) -> dict | None:
        """{"segundos": desde o último sinal, "pendentes", "recusados"} ou None."""
        s = self.sinais.get(urna)
        return s and {"segundos": time.monotonic() - s["em"], "pendentes": s["pendentes"], "recusados": s["recusados"]}

    def limpar(self):
        self.sinais.clear()

class SinaisRedis:
    TTL = 3600  # urna sem sinal há uma hora volta a aparecer como "nunca conectou"

    def __init__(self, r):
        self.r = r

    def registrar(self, urna: str, pendentes: int, recusados: int):
        # relógio de parede: processos diferentes não compartilham o monotonic
        chave = f"{PREFIXO}sinal:{urna}"
        self.r.hset(chave, mapping={"em": time.time(), "pendentes": pendentes, "recusados": recusados})
        self.r.expire(chave, self.TTL)

    def obter(self, urna: str) -> dict | None:
        s = self.r.hgetall(f"{PREFIXO}sinal:{urna}")
        if not s:
            return None
        return {"segundos": time.time() - float(s["em"]), "pendentes": int(s["pendentes"]),
                "recusados": int(s["recusados"])}

    def limpar(self):
        for chave in self.r.scan_iter(f"{PREFIXO}sinal:*"):
            self.r.delete(chave)

# ---------- Tentativas de login ----------
MAX_FALHAS = 10
JANELA_SEGUNDOS = 300

class FalhasMemoria:
    def __init__(self):
        self.falhas: dict[str, list[float]] = defaultdict(list)

    def recentes(self, ip: str) -> list[float]:
        agora = time.monotonic()
        self.falhas[ip] = [t for t in self.falhas[ip] if agora - t < JANELA_SEGUNDOS]
        return self.falhas[ip]

    def bloqueado(self, ip: str) -> bool:
        return len(self.recentes(ip)) >= MAX_FALHAS

    def restantes(self, ip: str) -> int:
        return max(0, MAX_FALHAS - len(self.recentes(ip)))

    def espera(self, ip: str) -> int:
        """Segundos até o IP voltar a poder tentar (janela deslizante)."""
        recentes = self.recentes(ip)
        if len(recentes) < MAX_FALHAS:
            return 0
        libera = recentes[len(recentes) - MAX_FALHAS]
        return math.ceil(JANELA_SEGUNDOS - (time.monotonic() - libera))

    def registrar(self, ip: str):
        self.falhas[ip].append(time.monotonic())

    def limpar(self):
        self.falhas.clear()

class FalhasRedis:
    """Janela fixa: a contagem some JANELA_SEGUNDOS depois da primeira falha."""

    def __init__(self, r):
        self.r = r

    def bloqueado(self, ip: str) -> bool:
        return int(self.r.get(f"{PREFIXO}falhas:{ip}") or 0) >= MAX_FALHAS

    def restantes(self, ip: str) -> int:
        return max(0, MAX_FALHAS - int(self.r.get(f"{PREFIXO}falhas:{ip}") or 0))

    def espera(self, ip: str) -> int:
        return max(0, self.r.ttl(f"{PREFIXO}falhas:{ip}")) if self.bloqueado(ip) else 0

    def registrar(self, ip: str):
        chave = f"{PREFIXO}falhas:{ip}"
        if self.r.incr(chave) == 1:
            self.r.expire(chave, JANELA_SEGUNDOS)

    def limpar(self):
        for chave in self.r.scan_iter(f"{PREFIXO}falhas:*"):
            self.r.delete(chave)

def criar_sinais(r=redis_sync):
    return SinaisRedis(r) if r else SinaisMemoria()

def criar_falhas(r=redis_sync):
    return FalhasRedis(r) if r else FalhasMemoria()

sinais = criar_sinais()
falhas = criar_falhas()
