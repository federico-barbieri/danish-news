# Danish News Reader

Private reader for Danish news (DR first). Click a paragraph to see its English translation.

## Run locally (Phase 1)

```bash
uv sync                      # Python 3.12 + deps
cp .env.example .env         # add your DEEPL_API_KEY (DeepL API Free)
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000. The first fetch starts on boot, then every 30 min
(APScheduler runs inside the app, so no separate cron container).
Feeds are seeded into the `sources` table from `app/config.py` on first run.

## Tests

```bash
uv run pytest
```

Extraction tests use saved DR pages in `tests/fixtures/`; DeepL is mocked.

## Deploy (Phase 2): Hetzner VPS with Coolify

Coolify's built-in Traefik proxy provides HTTPS (Let's Encrypt). The app protects itself with HTTP basic auth
(`BASIC_AUTH_USER` / `BASIC_AUTH_HASH`), so there is no separate proxy container in this repo.

1. **Generate the password hash** (on your Mac, from this repo):
   ```bash
   uv run python -m app.auth 'your-password'
   ```
   It prints `scrypt:<salt>:<hash>`. It contains no `$`, so it is safe in Coolify env vars.
2. **DNS.** Point an `A` record for `news.yourdomain.com` at the Hetzner server's IPv4 address.
3. **Push this repo to GitHub**, then in Coolify: *Project → New Resource → Public/Private Repository*
   (private needs a GitHub app or deploy key), pick the repo and branch `main`.
4. **Build pack: Docker Compose**, compose file `docker-compose.yml`.
5. **Domain.** On the `app` service set the domain to `https://news.yourdomain.com:8000`
   (the `:8000` tells Traefik which container port to route to).
6. **Environment variables** (Coolify → the resource → Environment Variables):
   `DEEPL_API_KEY`, `BASIC_AUTH_USER`, `BASIC_AUTH_HASH`. Optional: `DEEPL_TARGET`, `FETCH_INTERVAL_MINUTES`, `RETENTION_DAYS`.
   The deploy fails fast if one of the three required ones is missing, so the site can't go live unprotected.
7. **Deploy.** Visit `https://news.yourdomain.com`: it asks for the username and password, then shows the reader.
   The first fetch runs on startup; give it a minute or two. Logs are in Coolify's *Logs* tab.

`/healthz` is the only path that skips the password (it returns just `{"status":"ok"}`).

### Update

Push to GitHub and click *Deploy* in Coolify (or enable auto-deploy on push / a webhook).
The database lives in the `news-data` volume, so articles, read state and translations survive redeploys.

### Back up the SQLite file

In Coolify, open the `app` container's *Terminal*, or SSH into the server and run:

```bash
docker exec <app-container> python -c "import sqlite3; s=sqlite3.connect('/data/news.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d)"
docker cp <app-container>:/data/backup.db ./news-backup-$(date +%F).db
docker exec <app-container> rm /data/backup.db
```

(`docker ps` shows the container name.) This uses SQLite's online backup, so it is safe while the app runs.
Copy the file off the server with `scp`. To restore, stop the app, copy the file over `/data/news.db` in the volume, start it again.
Coolify can also back up volumes to S3 if you prefer.

### Troubleshooting

- Deploy error "set BASIC_AUTH_HASH": add the env var in Coolify.
- 502 / Bad Gateway: the domain on the `app` service must end in `:8000`.
- Login always fails: regenerate the hash with the command above and paste it without quotes or spaces.
- Without both `BASIC_AUTH_*` vars the app runs **unprotected** (fine for local dev only); it logs a warning at startup.
