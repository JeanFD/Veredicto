import os
AMBIENTE = os.getenv("AMBIENTE", "desenvolvimento")
EM_PRODUCAO = AMBIENTE == "producao"
ADMIN_SENHA = os.getenv("ADMIN_SENHA")
DB_PATH = os.getenv("DB_PATH", "veredicto.db")
SESSOES_PATH = os.getenv("SESSOES_PATH", "sessoes.json")
CARTOES_PATH = os.getenv("CARTOES_PATH", "cartoes.json")
REDIS_URL = os.getenv("REDIS_URL")  # vazio: um processo só, tudo em memória
