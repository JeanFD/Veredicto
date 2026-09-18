import sqlite3
import sys

estado = sys.argv[1] if len(sys.argv) > 1 else "ABERTA"
db = sqlite3.connect("veredicto.db")
db.execute("UPDATE sessoes SET estado = ?, encerrada_em = NULL WHERE ativa = 1", (estado,))
db.commit()
print(db.execute("SELECT id, estado, ativa FROM sessoes").fetchall())