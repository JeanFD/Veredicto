from alembic import context

# a conexão vem de app/migrar.py: a mesma que a app usa, inclusive nos testes
conexao = context.config.attributes.get("connection")
if conexao is None:
    raise SystemExit("aplique as migrações com: python -m app.migrar")
context.configure(connection=conexao, render_as_batch=True)

with context.begin_transaction():
    context.run_migrations()
