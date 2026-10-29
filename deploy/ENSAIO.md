# Carga, caos e ensaio antes do júri

Três etapas, nesta ordem. Cada uma só começa se a anterior passou.

Os scripts entram com a conta `admin`: `SENHA_ADMIN` é a senha atual dela (no
começo, a `ADMIN_SENHA` do `.env`; depois, a que foi trocada no painel).

## 1. Carga (`scripts/carga.py`)

N urnas votando ao mesmo tempo, como as de verdade: cada voto é repetido até o
servidor aceitar, e às vezes um voto já aceito é reenviado (como quando a resposta
se perde no caminho). No fim o script revela a sessão, baixa o CSV e confere voto
a voto: **nenhum perdido, nenhum duplicado, cada um com a urna e a opção enviadas**.

```bash
python -m scripts.carga --url https://veredicto.duckdns.org --senha "$SENHA_ADMIN" --urnas 20 --votos 50
```

- O script cria a própria sessão (`Carga <data>`) e urnas `carga-...`, todas
  marcadas como **teste**: não aparecem na auditoria pública, e o botão
  **Limpar testes** do painel (aba Sessões) apaga tudo o que a carga criou, votos e
  registros incluídos, e reativa a sessão real que estava ativa antes.
- O script se recusa a rodar se houver uma votação aberta ou encerrada sem revelar.
- Sai com código 1 e lista os votos com problema quando a conferência falha.
- `--intervalo 0` tira a pausa entre votos: bem acima do uso real, em que cada urna
  recebe um eleitor a cada poucos segundos. Anote votos/s e a latência (p95) do
  resumo e do `/monitor/` durante a carga.

## 2. Caos (`scripts/caos.py`)

A mesma carga enquanto o servidor é derrubado. O teste passa quando nenhum voto se
perde nem se duplica **e** os outros serviços da VPS seguem no ar o tempo todo.

Local, com `kill` no processo (é o que o CI roda, em `tests/test_carga.py`):

```bash
python -m scripts.caos --quedas 3
```

Na VPS, o comando que derruba o servidor é seu. `--vigiar` checa a cada segundo os
outros serviços da máquina (os do `deploy/Caddyfile`):

```bash
python -m scripts.caos --url https://veredicto.duckdns.org --senha "$SENHA_ADMIN" \
  --falha "ssh vps 'cd /opt/veredicto && docker compose kill veredicto && docker compose up -d veredicto'" \
  --vigiar https://despertar-das-raizes.duckdns.org --vigiar https://vibemetrics.duckdns.org
```

Outras falhas que valem rodar na VPS, uma por vez, trocando o `--falha`:

| Falha | Comando sugerido | Esperado |
|---|---|---|
| Container morto | `docker compose kill veredicto && docker compose up -d veredicto` | urnas guardam e reenviam; nada perdido |
| Proxy reiniciado | `docker compose restart caddy` | 502 por alguns segundos; nada perdido; outros serviços voltam junto |
| Deploy no meio | `docker compose up -d --build veredicto` | igual ao container morto |
| Memória no limite | carga com `--urnas 100` | `mem_limit` de 512 MB segura; o jogo e o vibemetrics não caem |

Reinicie o Caddy só fora do horário de uso do jogo e do vibemetrics: ele derruba
todos os domínios juntos por alguns segundos, e o `--vigiar` vai acusar isso.

## 3. Ensaio no local, com a rede real

Com as urnas, o telão e os celulares de verdade, no Wi-Fi do evento.

- [ ] Abrir /urna/ em cada dispositivo, pedir para virar urna e aprovar o código no painel (aba Urnas); conferir "online" na grade.
- [ ] Instalar a urna como app (PWA) em cada tablet; fechar e abrir de novo sem rede.
- [ ] Telão aberto pelo botão do mesário; QR do celular legível do fundo da sala.
- [ ] Sessão de ensaio com "Permitir voto por celular" marcado: votar em todas as urnas e em alguns celulares; total do telão bate com a grade.
- [ ] Desligar o voto por celular na barra da sessão ativa: o QR some do telão e o celular avisa para votar na urna.
- [ ] Tirar o Wi-Fi de uma urna, votar 3 vezes, devolver o Wi-Fi: os 3 votos chegam e a fila zera.
- [ ] Urna sem rede até o fim: exportar a fila e importar no painel.
- [ ] Encerrar e revelar; conferir o resultado do telão com o CSV e com a auditoria pública.
- [ ] Rodar `scripts/carga.py` pela rede do evento (de um notebook no Wi-Fi) e anotar a latência.
- [ ] Trocar o idioma de uma tela (botão PT/EN) e voltar.
- [ ] Criar as sessões e as urnas do ensaio marcadas como teste e, no fim, usar **Limpar testes**.
- [ ] Backup do banco (`deploy/backup.sh`) depois do ensaio.
