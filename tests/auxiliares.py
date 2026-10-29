import uuid
from datetime import datetime, timezone

ADMIN = ("admin", "senha-teste")

def login(cliente, usuario="admin", senha="senha-teste") -> str:
    """Token de login, como o navegador recebe."""
    return cliente.post("/api/login", json={"usuario": usuario, "senha": senha}).json()["token"]

def novo_voto(opcao="defesa", sessao_id=1, votado_em=None):
    return {
        "id": str(uuid.uuid4()),
        "sessao_id": sessao_id,
        "opcao": opcao,
        "votado_em": (votado_em or datetime.now(timezone.utc)).isoformat(),
    }