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
