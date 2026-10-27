# Vários processos com Redis

Por padrão o Veredicto roda com **um processo e sem Redis**: WebSocket, heartbeat
das urnas, bloqueio de login e métricas ficam em memória. É assim que roda em
produção hoje.

Com `REDIS_URL` definido, a app passa a aceitar vários processos:

- **Eventos de WebSocket** (voto, mudança de estado) são publicados no Redis
  (`veredicto:ws`) e cada processo entrega aos seus clientes: o telão conectado
  num processo vê o voto que chegou por outro.
- **Estado efêmero** compartilhado no Redis: heartbeat das urnas, tentativas de
  login e métricas do `/monitor/`.
- **Estado das sessões** continua no SQLite, já compartilhado. As transições são
  atômicas (`UPDATE ... WHERE estado = ?`): dois cliques simultâneos em processos
  diferentes não avançam a sessão duas vezes.
- Se o Redis cair, cada processo continua entregando os eventos aos seus próprios
  clientes e tenta reconectar a cada segundo.

## Ligar

No `.env` da VPS:

```
REDIS_URL=redis://redis:6379/0
WORKERS=2
```

E subir com o perfil `escala`, que inclui o container do Redis (até 64 MB de RAM,
sem persistência em disco):

```bash
docker compose --profile escala up -d --build
```

O deploy automático (`docker compose up -d veredicto`) não sobe o Redis: com o
perfil ligado, suba o Redis uma vez com o comando acima antes do próximo deploy.

## Desligar

Remova `REDIS_URL` e `WORKERS` do `.env` e rode `docker compose up -d veredicto`;
depois `docker compose --profile escala stop redis`.

## Limites conhecidos

- Os processos precisam compartilhar o mesmo arquivo SQLite, ou seja, rodar no
  mesmo host (`--workers` do uvicorn ou réplicas com o mesmo volume `./data`).
- Um banco **novo** deve ser criado antes de subir vários processos
  (`python -m app.migrar`, que o deploy já roda); senão os processos disputam a
  criação das tabelas.
- Um cliente conectado a um processo que cai perde a conexão e reconecta sozinho
  (telão e mesário tentam de novo a cada 2s) em outro processo.

## Testes

`tests/test_distribuido.py` cobre a lógica com fakeredis. `tests/test_redis_processos.py`
sobe três processos de verdade com um Redis de verdade: roda no CI e, localmente,
com `REDIS_TESTE_URL=redis://localhost:6379/0 pytest tests/test_redis_processos.py`.
