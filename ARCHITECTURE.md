# How Danish News Reader works

A private web app that collects Danish news (DR), shows it in a clean reading view, and translates any paragraph to English when you tap it.

## The big picture

```mermaid
flowchart LR
    subgraph Internet
        Phone["Your phone / browser"]
        DR["dr.dk<br/>RSS feeds + article pages"]
        DeepL["DeepL API<br/>(Danish to English)"]
    end

    subgraph Hetzner["Hetzner VPS (managed by Coolify)"]
        Traefik["Traefik proxy<br/>HTTPS (Let's Encrypt)"]
        subgraph Container["app container (FastAPI, 1 worker)"]
            Auth["Basic auth<br/>middleware"]
            Routes["Routes<br/>/, /article/id,<br/>/api/translate, /api/usage"]
            Sched["Scheduler<br/>(APScheduler)"]
            Fetcher["Fetcher<br/>feeds, extraction"]
            Cache["CachedTranslator"]
        end
        DB[("SQLite<br/>/data/news.db<br/>(Docker volume)")]
    end

    Phone -->|"https://news.danishnews.online"| Traefik
    Traefik --> Auth --> Routes
    Routes <--> DB
    Routes --> Cache
    Cache <-->|"cache hit/miss"| DB
    Cache -->|"cache miss only"| DeepL
    Sched -->|"every 30 min"| Fetcher
    Fetcher -->|"read feeds, fetch pages"| DR
    Fetcher -->|"store articles + paragraphs"| DB
```

## The two main flows

### 1. Collecting articles (runs on its own, no translation)

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant F as Fetcher
    participant DR as dr.dk
    participant DB as SQLite

    S->>F: start (on boot, then every 30 min)
    loop each enabled feed
        F->>DR: GET RSS feed
        loop each entry
            F->>DB: URL already stored?
            alt new URL
                F->>DR: GET article page (after a short delay)
                F->>F: trafilatura extracts text, split into paragraphs, drop boilerplate
                F->>DB: save article + paragraphs (with SHA-256 hash of each)
            else already stored or liveblog/video
                F->>F: skip
            end
        end
    end
    F->>DB: delete articles older than 30 days
```

### 2. Tapping a paragraph to translate it

```mermaid
sequenceDiagram
    participant B as Browser (reader.js)
    participant API as POST /api/translate
    participant DB as SQLite
    participant D as DeepL

    B->>B: already in browser cache?
    alt yes
        B->>B: show English instantly
    else no
        B->>API: {paragraph_id}
        API->>DB: translation for this text hash?
        alt cached
            DB-->>API: English text
        else not cached
            API->>D: translate Danish text (DA to EN-GB)
            D-->>API: English text
            API->>DB: save by text hash
        end
        API-->>B: {text_en}
        B->>B: show under the paragraph, store in browser cache
    end
```

## Pages and API

| Route | What it does |
|---|---|
| `GET /` | Feed page: newest first, filter by source/section, read articles dimmed |
| `GET /article/{id}` | Reading view; marks the article as read |
| `POST /api/translate` | Body `{"paragraph_id": n}` or `{"article_id": n, "field": "title"}`; returns `{"text_en": "..."}` |
| `GET /api/usage` | Remaining DeepL characters (cached 60 s), shown in the page header |
| `GET /healthz` | Health check (the only path that skips the password) |
| `GET /robots.txt` | Disallows everything; every response also has `X-Robots-Tag: noindex` |

## Files

```
app/
  main.py        FastAPI app, routes, rate limit on /api/translate, middleware
  auth.py        HTTP basic auth (scrypt hash); also a CLI to generate the hash
  config.py      Settings from environment variables + default DR feeds
  db.py          SQLite schema and all queries
  fetcher.py     RSS reading, article extraction, paragraph cleaning
  translate.py   Translator interface, DeepL implementation, cache layer
  scheduler.py   Runs the fetcher on an interval inside the app
  templates/     base.html, feed.html, article.html (Jinja2, server-rendered)
  static/        style.css, reader.js (click-to-translate), usage.js (quota counter)
tests/
  fixtures/      Saved DR article HTML used by the extraction tests
Dockerfile, docker-compose.yml   Container setup for Coolify
```

## Data model

```mermaid
erDiagram
    sources ||--o{ articles : "has"
    articles ||--o{ paragraphs : "split into"
    paragraphs }o--|| translations : "text_hash"

    sources {
        int id PK
        text name "e.g. DR"
        text section "e.g. Indland"
        text feed_url UK
        int enabled
    }
    articles {
        int id PK
        int source_id FK
        text url UK
        text title
        text teaser
        text section
        text published_at
        text read_at "set when opened"
    }
    paragraphs {
        int id PK
        int article_id FK
        int position
        text text_da
        text text_hash "SHA-256 of text_da"
    }
    translations {
        text text_hash PK
        text text_en
        text provider
        text created_at
    }
```

Translations are keyed by the **hash of the Danish text**, not the paragraph id. An identical sentence in two articles is translated (and billed) only once.

## Design decisions worth knowing

- **Translate on demand.** Nothing is translated at fetch time, so DeepL characters are only spent on paragraphs you actually tap.
- **Swappable translator.** `translate(text, context)` sits behind a small interface in `translate.py`. To use Claude or another API, add a class with the same method and pass it to `CachedTranslator`. The cache layer doesn't change.
- **One process, one database file.** The scheduler runs inside the app, so there is no separate worker or cron container. This is also why the container runs a single uvicorn worker: more workers would each start their own scheduler.
- **Password in the app.** Coolify's Traefik handles HTTPS, and the app does basic auth itself (`BASIC_AUTH_USER` and `BASIC_AUTH_HASH`). If those aren't set the site is open, which is fine for local development only.
- **Polite scraping.** A custom User-Agent, a delay between requests, timeouts, and failures are logged and skipped instead of crashing the job.
- **Paywalls are never bypassed.**

## Configuration (environment variables)

| Variable | Purpose | Default |
|---|---|---|
| `DEEPL_API_KEY` | DeepL key (required to translate) | none |
| `DEEPL_TARGET` | `EN-GB` or `EN-US` | `EN-GB` |
| `BASIC_AUTH_USER` / `BASIC_AUTH_HASH` | Login; make the hash with `uv run python -m app.auth 'password'` | none (open) |
| `FETCH_INTERVAL_MINUTES` | How often to fetch feeds | 30 |
| `RETENTION_DAYS` | Delete articles older than this | 30 |
| `DB_PATH` | SQLite file location | `data/news.db` (`/data/news.db` in Docker) |

See the [README](README.md) for running locally and deploying.
