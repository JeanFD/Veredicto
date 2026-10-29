# Veredicto

Live voting for a mock jury: touchscreen ballot boxes, voting by phone through a
QR code, a big screen with the live total and the reveal, and a poll-worker panel
that runs the session. Ballot boxes keep working offline and resend their votes
when the network comes back; no vote is lost or counted twice.

The interface is in Portuguese and English (it follows the browser language;
there is a PT/EN switch in the corner of every screen).

## Screens

| Path | Who uses it | What it does |
|---|---|---|
| `/urna/` | voters | Ballot box. Configured by a link/QR from the panel; installable as an app (PWA); queues votes offline. |
| `/telao/` | the room | Big screen: topic, live vote count, 3·2·1 reveal with the result bars, QR code for phone voting. |
| `/celular/` | voters | Phone voting, opened from the QR code on the big screen; one vote per phone per question. |
| `/mesario/` | poll worker | Password-protected panel: create sessions and questionnaires, open/close/reveal, register ballot boxes, watch their status, import an offline queue. |
| `/monitor/` | poll worker | Votes per minute, vote latency (p50/p95) and ballot boxes online. |
| `/auditoria/` | anyone | Public audit of revealed sessions: per-box counts and the event log. |

## How a session works

`AGUARDANDO` (waiting) → `ABERTA` (open) → `ENCERRADA` (closed) → `REVELADA` (revealed).

- Only the active session receives votes. Votes cast offline before the close are
  still accepted for 10 minutes after it (later than that, the poll worker imports
  the exported queue).
- Before revealing, the panel lists pending issues (a box that never connected, a
  box offline, votes still queued) and asks for confirmation.
- A questionnaire is a chain of questions: each one is opened and revealed on its
  own, and the poll worker releases the next one after revealing the previous.
- Each vote has a client-generated UUID, so resending is idempotent.
- Test mode: sessions and ballot boxes can be created as *test*. They are hidden
  from the public audit, a test ballot box cannot vote in a real session, and
  **Clear tests** in the panel deletes everything they produced (votes, ballots,
  events), leaving the database as it was. The load and chaos scripts use it.

## Running locally

Requires Python 3.12.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
ADMIN_SENHA=secret .venv/bin/uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/mesario/, sign in with the password, register a ballot
box and open its link. The database (`veredicto.db`) is created and migrated on
startup. In Docker the variables come from `.env` (see [.env.example](.env.example)).

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ADMIN_SENHA` | (required) | Poll-worker password (user `mesario`). |
| `AMBIENTE` | `desenvolvimento` | `producao` hides `/docs` and the OpenAPI schema. |
| `DB_PATH` | `veredicto.db` | SQLite file. |
| `SESSOES_PATH` | `sessoes.json` | Session presets shown in the panel. |
| `REDIS_URL` | (empty) | Enables several processes sharing state through Redis ([deploy/ESCALA.md](deploy/ESCALA.md)). |
| `WORKERS` | `1` | Uvicorn workers in the container; more than one only with `REDIS_URL`. |

## Tests

```bash
pytest                    # backend, including load and chaos (kill -9) checks
pytest e2e                # end to end with Playwright: see e2e/README.md
```

## Load, chaos and rehearsal

- `python -m scripts.carga --url URL --senha PASSWORD --urnas 20 --votos 50`: N
  ballot boxes voting at once, with resends; at the end it reveals the session,
  downloads the CSV and checks every vote is there exactly once.
- `python -m scripts.caos`: the same load while the server is killed and
  restarted; against the VPS, `--falha` runs your command to take it down and
  `--vigiar URL` checks the other services on the machine stay up.

The full checklist (VPS chaos runs and the on-site rehearsal) is in
[deploy/ENSAIO.md](deploy/ENSAIO.md) (Portuguese).

## Deploy

Docker Compose with Caddy as the HTTPS proxy ([docker-compose.yml](docker-compose.yml),
[deploy/Caddyfile](deploy/Caddyfile)). Every push to `main` that passes the tests is
deployed by GitHub Actions over SSH: build, database backup and migrations
(`python -m app.migrar`, Alembic), then the container is swapped. Backups:
[deploy/backup.sh](deploy/backup.sh).

## Project layout

```
app/          FastAPI app: routes (main.py), database, migrations, security,
              WebSocket fan-out, metrics, server messages (i18n.py)
static/       the screens (vanilla JS, no build step) and i18n.js, the translations
tests/        backend tests (pytest)
e2e/          browser tests (Playwright)
scripts/      load and chaos scripts
deploy/       Caddy, backup, scaling and rehearsal docs
```
