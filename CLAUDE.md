# Danish News Reader: Project Brief for Claude Code

## Goal

A private web app, hosted on my own domain, that collects Danish news articles (starting with DR) and shows them in a clean reading view. **The core feature:** clicking any paragraph reveals its English translation directly underneath it. Clicking again hides it. I want to keep reading in Danish, with English one tap away.

Build it in the phases below. Finish each phase and confirm it works before starting the next. Ask me before adding dependencies or features not described here.

---

## User experience (what "done" looks like)

### Feed page (`/`)
- A list of the latest articles, newest first: title, source (e.g. "DR"), section if available, published time (relative, in Danish or English, your choice), and a short teaser.
- Each item links to the reading view on my site, not to dr.dk.
- Simple filter by source. Add a filter by section if the data supports it.
- Mark articles I've opened as read (dimmed in the list).

### Reading view (`/article/<id>`)
- Title, source, published time, and a small link to the original article.
- Body text split into paragraphs. **Every paragraph is clickable.**
- Click a paragraph:
  - The English translation appears directly below it, visually distinct (smaller, muted colour, left border).
  - Show a small loading state while the translation is fetched.
  - Click again to hide it. The second open is instant, because the result is cached client-side.
- A "Show all translations" toggle at the top.
- The title is translatable the same way.
- Optional, phase 4: double-click or long-press a single word to see its meaning.

### General
- **Mobile-first.** I'll mostly read on my phone. Comfortable reading typography: max width ~65ch, readable font size, good line height.
- Light and dark mode via `prefers-color-scheme`.
- Set `lang="da"` on Danish text and `lang="en"` on translations.
- No ads, images optional (the lead image only, if easy).

---

## Tech stack

Keep it simple and boring. One server, one database file.

- **Backend:** Python 3.12+, FastAPI, Jinja2 templates (server-rendered HTML)
- **Frontend:** plain HTML, CSS, and a small vanilla JS file for click-to-translate. No React, no build step.
- **Database:** SQLite (via `sqlite3` or SQLModel; keep it light)
- **Feeds:** `feedparser`
- **Article extraction:** `trafilatura`, with `httpx` for fetching
- **Scheduling:** APScheduler running inside the app, or a separate cron container. Pick one and document it.
- **Translation:** DeepL API (Free tier, `https://api-free.deepl.com/v2/translate`, header `Authorization: DeepL-Auth-Key <key>`). Source `DA`, target `EN-GB` or `EN-US`. Check DeepL's current API docs for exact parameters. Hide the provider behind a small interface (`translate(text, context) -> str`) so I can swap in Claude or another API later.
- **Deployment:** Docker + Docker Compose, with Caddy as reverse proxy (automatic HTTPS via Let's Encrypt).

---

## Data model (starting point)

```
sources:       id, name, feed_url, enabled
articles:      id, source_id, url (unique), title, teaser, section,
               published_at, fetched_at, lead_image_url, read_at
paragraphs:    id, article_id, position, text_da
translations:  id, paragraph_id (or hash of text), text_en, provider, created_at
```

Cache translations keyed by a **hash of the Danish text**, so identical paragraphs are never translated twice.

---

## Fetching pipeline

1. Every 30 minutes, read each enabled RSS feed.
2. For each new URL (dedupe on URL), fetch the page and extract the main text with trafilatura.
3. Split into paragraphs. Drop empty ones, bylines, "Læs også"-style links, and other boilerplate. Use saved HTML fixtures to tune this.
4. Store the article and its paragraphs. **Do not translate at fetch time.** Translation happens on demand when I click.
5. Be polite: a custom User-Agent naming the project, a small delay between requests, and a timeout. Skip and log any article that fails extraction. Don't crash the job.
6. Delete articles older than 30 days (configurable).

### Sources
- Start with DR's RSS feeds. A likely starting point is `https://www.dr.dk/nyheder/service/feeds/senestenyt`, plus section feeds. **Verify the current feed URLs** before hard-coding them, and keep them in config or the database, not in code.
- Phase 3 adds more sources, such as TV2 and Information. Each must be verified to extract cleanly. Skip paywalled articles; don't try to bypass paywalls.

---

## API

- `GET /`: feed page
- `GET /article/{id}`: reading view (marks the article as read)
- `POST /api/translate`: body `{ "paragraph_id": int }` or `{ "article_id": int, "field": "title" }`. Returns `{ "text_en": "..." }`. Checks the cache first, then calls the provider and stores the result.
- `GET /healthz`: simple health check

Translate one paragraph per click. For "show all", call the endpoint per paragraph with limited concurrency, or add a batch endpoint.

---

## Security and privacy (important)

The site is on the public internet, but **it is for me only**:
- Protect the whole site with HTTP basic auth at the Caddy level, using a hashed password in the Caddyfile. This keeps scraped content private and protects my DeepL quota.
- Add `X-Robots-Tag: noindex` / `robots.txt` disallowing everything.
- Keep all secrets (DeepL key, basic-auth hash) in `.env`. Commit a `.env.example`, never `.env`.
- Rate-limit `/api/translate` modestly as a safety net.

---

## Project structure (suggested)

```
app/
  main.py            # FastAPI app, routes
  db.py              # schema + queries
  fetcher.py         # RSS + extraction + paragraph splitting
  translate.py       # provider interface + DeepL implementation + cache
  scheduler.py
  templates/         # base.html, feed.html, article.html
  static/            # style.css, reader.js
tests/
  fixtures/          # saved article HTML from DR for extraction tests
Dockerfile
docker-compose.yml   # app + caddy, with a volume for the SQLite file
Caddyfile
.env.example
README.md            # local run + deploy instructions
```

---

## Build phases

### Phase 1: Local MVP (DR only)
- Fetch DR feeds, extract articles, store them in SQLite.
- Feed page and reading view working locally (`uvicorn` or `docker compose up`).
- Click-to-translate working through DeepL, with server-side caching.
- **Done when:** I can run it locally, open a DR article, and tap paragraphs to see English.

### Phase 2: Deploy to my domain
- Dockerfile, docker-compose with Caddy, HTTPS, basic auth, persistent volume for the database.
- README section with step-by-step deploy instructions for a small Linux VPS (e.g. Hetzner, around €4/month):
  - install Docker
  - clone the repo
  - create `.env`
  - point the domain's DNS A record to the server
  - run `docker compose up -d`
- Explain how to update the deployment (git pull + rebuild) and how to back up the SQLite file.
- **Done when:** visiting `https://<my-domain>` asks for a password and then shows the reader.

### Phase 3: More sources and polish
- Add TV2, Information, and other free sources, each verified with an extraction test.
- Source and section filters, read/unread state, "show all translations" toggle, dark mode polish.

### Phase 4: Learning extras (optional; ask me first)
- Tap a single word for its meaning, in the context of its sentence.
- Save words or phrases to a vocabulary list with the sentence they came from.
- Export the vocabulary list as CSV (e.g. for Anki).

---

## Conventions
- Write small, readable code with type hints. Add docstrings only where the code isn't self-explanatory.
- Add tests for paragraph extraction (using saved fixtures) and for the translation cache. Mock DeepL in tests.
- Log fetch results (new articles, failures) to stdout so `docker compose logs` shows what happened.
- Don't commit scraped content or the database file.

## Out of scope for now
- User accounts or multi-user support
- Native apps
- Bypassing paywalls
- Publishing the articles publicly