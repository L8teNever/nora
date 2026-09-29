# Nora

Docker web UI that **schedules HTTP fires** against the [Claude Code Routine API](https://platform.claude.com/docs/en/api/claude-code/routines-fire). Put the UI behind **Cloudflare Zero Trust** (Tunnel + Access). Nora does not replace Claude’s own scheduler; it is a small, self-hosted trigger panel for API-triggered routines.

## Architecture

```
Browser  →  Cloudflare Access (SSO)  →  Cloudflare Tunnel  →  Nora (FastAPI :8080)
                                                                  │
                                                                  ├─ SQLite volume (schedules + encrypted tokens)
                                                                  └─ APScheduler → POST Claude /fire
```

- **Stack:** Python 3.12, FastAPI, Jinja UI, APScheduler, SQLAlchemy/SQLite, httpx.
- **Persistence:** `/data/nora.sqlite3` in the `nora-data` volume.
- **Secrets:** `.env` only. Per-job bearer tokens are Fernet-encrypted with `NORA_ENCRYPTION_KEY` before they hit SQLite. Nothing secret belongs in git.

Each Nora “schedule” maps to one Claude routine **API trigger**:

```http
POST https://api.anthropic.com/v1/claude_code/routines/{trig_…}/fire
Authorization: Bearer sk-ant-oat01-…
anthropic-version: 2023-06-01
anthropic-beta: experimental-cc-routine-2026-04-01
{"text": "optional context"}
```

Create the Claude routine (prompt, repos, connectors) at [claude.ai/code/routines](https://claude.ai/code/routines), add an **API** trigger, copy the URL and token (token is shown once).

## Local / Dockge

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste that value into NORA_ENCRYPTION_KEY in .env
```

Optional defaults (used when a job leaves URL/token blank):

```bash
CLAUDE_ROUTINE_FIRE_URL=https://api.anthropic.com/v1/claude_code/routines/trig_…/fire
CLAUDE_ROUTINE_TOKEN=sk-ant-oat01-…
```

Then:

```bash
docker compose up --build
```

Open http://127.0.0.1:8080 — list / create / edit / enable / disable / delete / run-now.

**Dockge:** create a stack from this repo’s `docker-compose.yml`, point the compose path at the cloned project, and set env vars in Dockge’s env editor (not in a committed file). Keep the published port on a private Docker network if Tunnel is the only ingress.

Health check for Tunnel / compose: `GET /health`.

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export NORA_DATABASE_URL=sqlite:///./data/nora.sqlite3
export NORA_ENCRYPTION_KEY=...   # Fernet key
uvicorn app.main:app --reload --port 8080
```

```bash
pytest
```

## Environment

| Variable | Purpose |
| --- | --- |
| `NORA_DATABASE_URL` | SQLAlchemy URL. Compose default: `sqlite:////data/nora.sqlite3` |
| `NORA_ENCRYPTION_KEY` | Fernet key; required to store per-job tokens |
| `NORA_TZ` | IANA timezone for cron (default `UTC`) |
| `CLAUDE_ROUTINE_FIRE_URL` | Default `/fire` URL |
| `CLAUDE_ROUTINE_TOKEN` | Default per-routine bearer token |
| `ANTHROPIC_VERSION` | Header, default `2023-06-01` |
| `NORA_HOST` / `NORA_PORT` | Documented for local uvicorn; the image binds `0.0.0.0:8080` |

If a job fires with neither job-level nor env credentials, Nora records a clear error on that row (`Missing Claude routine fire URL` / `Missing Claude routine token`).

## Cloudflare Zero Trust

Do **not** expose `:8080` on the public internet. Terminate TLS and identity at Cloudflare.

1. **Tunnel**  
   In Zero Trust → Networks → Tunnels, create a tunnel (cloudflared). Public hostname e.g. `nora.example.com` → HTTP `http://nora:8080` (same Docker network as this stack) or `http://host.docker.internal:8080` if Nora runs on the host.

   Example extra compose service (token only via env / Dockge secrets):

   ```yaml
   cloudflared:
     image: cloudflare/cloudflared:latest
     restart: unless-stopped
     command: tunnel --no-autoupdate run
     environment:
       TUNNEL_TOKEN: ${TUNNEL_TOKEN}
     depends_on:
       - nora
   ```

   Prefer a remotely managed tunnel (token from the Zero Trust dashboard) over baking `config.yml` with credentials into the repo.

2. **Access application**  
   Zero Trust → Access → Applications → Add Self-hosted.  
   Domain: `nora.example.com`.  
   Policy: allow your email / IdP group. Session duration as you prefer.

3. **Health**  
   Point Tunnel origin health at `http://nora:8080/health` if you use origin health checks. Access can skip `/health` if you need unauthenticated probes from Cloudflare only — otherwise protect the whole hostname.

4. **DNS**  
   CNAME the hostname to the tunnel. Confirm you hit the Access login, then Nora.

## Claude wiring recap

1. claude.ai/code/routines → New routine (prompt, repos, environment).  
2. Add trigger → **API** → copy fire URL + generate token.  
3. In Nora, New schedule → paste URL/token or rely on env defaults → cron (`0 6 * * *`) or interval (minutes/hours).  
4. Run once from the UI; confirm a session URL appears (or a 401/404 message if URL/token mismatch).

Claude rate-limits API fires (per-routine and per-account hourly caps). Nora coalesces overlapping runs (`max_instances=1`).

## Security notes

- Public repo: only `.env.example` with empty values.  
- Tokens in SQLite are encrypted; lose `NORA_ENCRYPTION_KEY` and you must re-enter tokens.  
- Nora itself has no login — **Cloudflare Access is the auth layer**.  
- Do not log bearer tokens. The UI never redisplays stored secrets.

## License

Use and modify as you like for this project.
