import uuid
from datetime import datetime, timezone

ADMIN = ("mesario", "senha-teste")

def novo_voto(opcao="defesa", sessao_id=1, votado_em=None):
    return {
        "id": str(uuid.uuid4()),
        "sessao_id": sessao_id,
        "opcao": opcao,
        "votado_em": (votado_em or datetime.now(timezone.utc)).isoformat(),
    }