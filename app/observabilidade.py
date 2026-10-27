"""Logs estruturados em JSON e métricas de operação, sem dependência externa.

Formato do log: uma linha JSON por evento em stdout, com "ts" (UTC, ISO 8601),
"evento" e, quando aplicável, "sessao" e "urna", além de campos do próprio evento.
A opção votada nunca vai para o log: o sigilo do voto vale também aqui.

Métricas ficam em memória (a app roda com um worker só) e cobrem a última hora:
servidas em /api/admin/metricas para o painel /monitor/ e em /metrics no formato
Prometheus, caso um dia valha a pena plugar um Grafana.
"""
import json
import logging
import sys
import time
from collections import Counter, deque
from datetime import datetime, timezone

CAMPOS_FIXOS = ("ts", "evento", "sessao", "urna")

class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        campos = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                  "evento": record.getMessage(), **getattr(record, "campos", {})}
        return json.dumps(campos, ensure_ascii=False, default=str)

logger = logging.getLogger("veredicto")
if not logger.handlers:
    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(FormatoJson())
    logger.addHandler(saida)
    logger.setLevel(logging.INFO)
    logger.propagate = False

def log(evento: str, **campos):
    logger.info(evento, extra={"campos": {k: v for k, v in campos.items() if v is not None}})

def campos_do_detalhe(detalhe: str) -> dict:
    """'sessao=1 estado=ABERTA' → {'sessao': '1', 'estado': 'ABERTA'}."""
    campos = dict(p.split("=", 1) for p in detalhe.split() if "=" in p)
    return {k: int(v) if v.isdigit() else v for k, v in campos.items()}

# ---------- Métricas ----------
JANELA_MINUTOS = 60
JANELA_LATENCIA = 300  # segundos

class Metricas:
    def __init__(self):
        self.zerar()

    def zerar(self):
        self.por_minuto: Counter[int] = Counter()   # minuto (epoch // 60) → votos aceitos
        self.latencias: deque[tuple[float, float]] = deque(maxlen=5000)  # (quando, ms)
        self.votos_total: Counter[str] = Counter()   # origem → votos aceitos
        self.recusados_total: Counter[str] = Counter()  # motivo → votos recusados

    def voto_aceito(self, origem: str):
        minuto = int(time.time() // 60)
        self.por_minuto[minuto] += 1
        self.votos_total[origem] += 1
        for antigo in [m for m in self.por_minuto if m <= minuto - JANELA_MINUTOS]:
            del self.por_minuto[antigo]

    def voto_recusado(self, motivo: str):
        self.recusados_total[motivo] += 1

    def latencia(self, ms: float):
        self.latencias.append((time.monotonic(), ms))

    def votos_por_minuto(self, minutos: int = 30) -> list[int]:
        """Do mais antigo ao minuto atual (incompleto)."""
        agora = int(time.time() // 60)
        return [self.por_minuto.get(m, 0) for m in range(agora - minutos + 1, agora + 1)]

    def percentis(self) -> dict:
        limite = time.monotonic() - JANELA_LATENCIA
        recentes = sorted(ms for quando, ms in self.latencias if quando >= limite)
        if not recentes:
            return {"p50": None, "p95": None, "amostras": 0}
        def p(q):
            return round(recentes[min(len(recentes) - 1, int(q * len(recentes)))], 1)
        return {"p50": p(0.5), "p95": p(0.95), "amostras": len(recentes)}

metricas = Metricas()

def formato_prometheus(urnas_online: int, urnas_ativas: int) -> str:
    linhas = [
        "# HELP veredicto_votos_total Votos aceitos desde que a app subiu.",
        "# TYPE veredicto_votos_total counter",
        *(f'veredicto_votos_total{{origem="{o}"}} {n}' for o, n in sorted(metricas.votos_total.items())),
        "# HELP veredicto_votos_recusados_total Votos recusados desde que a app subiu.",
        "# TYPE veredicto_votos_recusados_total counter",
        *(f'veredicto_votos_recusados_total{{motivo="{m}"}} {n}'
          for m, n in sorted(metricas.recusados_total.items())),
        "# HELP veredicto_latencia_voto_ms Latência do envio de voto nos últimos 5 minutos.",
        "# TYPE veredicto_latencia_voto_ms gauge",
    ]
    for nome, valor in metricas.percentis().items():
        if nome != "amostras" and valor is not None:
            linhas.append(f'veredicto_latencia_voto_ms{{quantil="{nome[1:]}"}} {valor}')
    linhas += [
        "# HELP veredicto_urnas_online Urnas ativas com sinal nos últimos 15s.",
        "# TYPE veredicto_urnas_online gauge",
        f"veredicto_urnas_online {urnas_online}",
        "# HELP veredicto_urnas_ativas Urnas cadastradas e ativas.",
        "# TYPE veredicto_urnas_ativas gauge",
        f"veredicto_urnas_ativas {urnas_ativas}",
    ]
    return "\n".join(linhas) + "\n"
