# Veredicto

*English: [README.en.md](README.en.md)*

Votação ao vivo para júri simulado: urnas em tela de toque, voto pelo celular por QR
code, um telão com o total ao vivo e a revelação, e um painel do mesário que conduz a
sessão. As urnas continuam funcionando sem rede e reenviam os votos quando a conexão
volta; nenhum voto se perde nem é contado duas vezes.

A interface está em português e inglês (segue o idioma do navegador; há um seletor
PT/EN no canto de cada tela).

## Telas

| Endereço | Quem usa | O que faz |
|---|---|---|
| `/urna/` | eleitores | Urna. Abra no dispositivo e toque em "Pedir para virar urna": aparece um código de 4 letras que o mesário aprova no painel (ou configure por link/QR gerado no painel). Instalável como app (PWA); guarda os votos numa fila quando está sem rede. |
| `/telao/` | a plateia | Telão: tema, contagem de votos ao vivo, revelação com 3·2·1 e um cartão por opção — a vencedora preenchida em verde-limão, com porcentagem, votos e barra —, QR code do voto por celular, o cronômetro das falas que o mesário inicia (vermelho, contando o tempo excedido, quando o tempo acaba) e os cartões que ele põe na tela — pano de fundo do caso, notícias, laudos. Com pesos de voto (1 a 10 por urna, e por sessão para os celulares), barras e vencedora seguem os pontos, e cada opção mostra também quantos votos teve. O admin configura cores, textos e o jeito da revelação no painel. |
| `/celular/` | eleitores | Voto pelo celular, aberto pelo QR code do telão; um voto por celular em cada pergunta. Desligado por padrão: o mesário liga por sessão ("Permitir voto por celular", ou a chave na barra da sessão ativa). |
| `/mesario/` | mesário | Painel com contas individuais: criar e editar sessões e questionários, abrir/encerrar/revelar, cadastrar urnas e acompanhar o estado delas, importar uma fila offline, gerenciar contas, conduzir o cronômetro das falas e os cartões do telão (escritos ali, ou buscados de um link de notícia que o servidor lê por você). |
| `/monitor/` | mesário | Votos por minuto, latência do voto (p50/p95) e urnas online. |
| `/auditoria/` | qualquer pessoa | Auditoria pública das sessões reveladas: contagem por urna e linha do tempo dos eventos. |

## Como uma sessão funciona

`AGUARDANDO` → `ABERTA` → `ENCERRADA` → `REVELADA`.

- Só a sessão ativa recebe votos. Votos dados sem rede antes do encerramento ainda
  são aceitos por 10 minutos depois dele (passado isso, o mesário importa a fila
  exportada pela urna).
- Antes de revelar, o painel lista as pendências (urna que nunca conectou, urna sem
  sinal, votos ainda na fila) e pede confirmação.
- Um questionário é uma sequência de perguntas: cada uma é aberta e revelada
  separadamente, e o mesário libera a próxima depois de revelar a anterior.
- Cada voto tem um UUID gerado no cliente, então reenviar não duplica.
- Modo teste: sessões e urnas podem ser criadas como *teste*. Elas não aparecem na
  auditoria pública, uma urna de teste não vota em sessão real, e **Limpar testes** no
  painel apaga tudo o que elas produziram (votos, cédulas, eventos), deixando o banco
  como estava. Os scripts de carga e de caos usam esse modo.

## Rodando localmente

Requer Python 3.12.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
ADMIN_SENHA=segredo .venv/bin/uvicorn app.main:app --reload
```

Abra http://127.0.0.1:8000/mesario/, entre como `admin` com essa senha, abra /urna/ em
outra aba, peça para virar urna e aprove o código na aba Urnas. O banco (`veredicto.db`)
é criado e migrado na inicialização. No Docker, as variáveis vêm do `.env` (veja o
[.env.example](.env.example)).

### Configuração

| Variável | Padrão | Para que serve |
|---|---|---|
| `ADMIN_SENHA` | (obrigatória) | Senha da primeira conta `admin`, criada quando ainda não há contas (troque depois no painel). Também assina a chave do telão e os códigos do celular. |
| `AMBIENTE` | `desenvolvimento` | `producao` esconde o `/docs` e o esquema OpenAPI. |
| `DB_PATH` | `veredicto.db` | Arquivo SQLite. |
| `SESSOES_PATH` | `sessoes.json` | Sessões prontas mostradas no painel, cada uma com seu caso. |
| `CARTOES_PATH` | `cartoes.json` | Cartões do telão carregados na primeira vez que o painel não tem nenhum. |
| `REDIS_URL` | (vazio) | Liga vários processos compartilhando o estado pelo Redis ([deploy/ESCALA.md](deploy/ESCALA.md)). |
| `WORKERS` | `1` | Workers do Uvicorn no container; mais de um só com `REDIS_URL`. |

### Conduzindo uma sessão

As sessões são agrupadas por **caso** (o júri), o mesmo nome usado pelos cartões do
telão, então o seletor de caso no alto do painel filtra os dois de uma vez. Um
questionário aparece como um bloco só, com as perguntas numeradas em ordem. A barra do
alto é o palco: mostra o que está no ar, a trilha de quatro passos (aguardando → aberta
→ encerrada → revelada) e um único botão, o próximo passo. As linhas só escolhem o que
vai para o palco; arquivar, zerar a contagem e mover a sessão para outro caso ficam em
"Ações".

"Editar" (em "Ações") reabre a sessão no formulário de criação. As regras, conferidas
no servidor e pergunta por pergunta num questionário:

- **Aguardando e sem votos:** tudo muda — tema, caso, opções (rótulo, cor, quantas) e,
  enquanto nenhuma pergunta do questionário foi aberta, incluir, tirar ou reordenar
  perguntas.
- **Já aberta alguma vez** (aberta, encerrada ou revelada) **ou com votos:** as opções
  ficam travadas, porque cada voto aponta para a chave de uma opção. Só o texto do tema
  e o caso mudam, depois de uma confirmação; a edição fica registrada e, numa pergunta
  já aberta, aparece na auditoria pública.

Toda edição vai para o registro do painel como "Sessão editada", e editar a sessão que
está no palco atualiza o telão na hora.

### Contas

Cada pessoa entra com o próprio usuário e senha; o navegador guarda só um token de 12
horas, nunca a senha. Papéis: **admin** (tudo, inclusive contas, zerar contagem e
limpar testes), **mesário** (conduz as sessões, cadastra urnas) e **monitor** (só o
`/monitor/`: estado das urnas e métricas). A auditoria interna (`/api/admin/eventos`)
registra quem fez cada ação, e o registro do painel mostra também quando cada conta
entrou. Esqueceu a senha do admin?

```bash
docker compose exec veredicto python -m app.contas redefinir admin
```

## Testes

```bash
pytest                    # backend, incluindo as verificações de carga e de caos (kill -9)
pytest e2e                # ponta a ponta com Playwright: veja e2e/README.md
```

## Carga, caos e ensaio

- `python -m scripts.carga --url URL --senha SENHA --urnas 20 --votos 50`: N urnas
  votando ao mesmo tempo, com reenvios; no fim revela a sessão, baixa o CSV e confere
  que cada voto está lá exatamente uma vez.
- `python -m scripts.caos`: a mesma carga enquanto o servidor é derrubado e
  reiniciado; contra a VPS, `--falha` roda o seu comando para derrubá-lo e
  `--vigiar URL` confere que os outros serviços da máquina continuam no ar.

O roteiro completo (caos na VPS e ensaio no local) está em
[deploy/ENSAIO.md](deploy/ENSAIO.md).

## Deploy

Docker Compose com o Caddy como proxy HTTPS ([docker-compose.yml](docker-compose.yml),
[deploy/Caddyfile](deploy/Caddyfile)). Todo push no `main` que passa nos testes é
publicado pelo GitHub Actions via SSH: build, backup do banco e migrações
(`python -m app.migrar`, Alembic), e então o container é trocado. Backups:
[deploy/backup.sh](deploy/backup.sh). Depois de cada deploy, recarregue as urnas
abertas: elas só pegam a versão nova ao recarregar.

## Organização do projeto

```
app/          app FastAPI: rotas (main.py), banco, migrações, segurança,
              distribuição pelo WebSocket, métricas, mensagens do servidor (i18n.py)
static/       as telas (JS puro, sem etapa de build) e o i18n.js, com as traduções
tests/        testes do backend (pytest)
e2e/          testes no navegador (Playwright)
scripts/      scripts de carga e de caos
deploy/       Caddy, backup e documentos de escala e de ensaio
```
