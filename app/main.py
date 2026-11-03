import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .auth import BasicAuth
from .config import settings
from .db import Database
from .fetcher import text_hash
from .scheduler import make_scheduler
from .translate import CachedTranslator, DeepLTranslator, TranslationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE = Path(__file__).parent
db = Database(settings.db_path)
translator = CachedTranslator(db, DeepLTranslator(settings))
templates = Jinja2Templates(directory=BASE / "templates")


def reltime(iso: str) -> str:
    secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    if secs < 3600:
        return f"{max(1, int(secs // 60))} min siden"
    if secs < 86400:
        return f"{int(secs // 3600)} t siden"
    return f"{int(secs // 86400)} d siden"


templates.env.filters["reltime"] = reltime


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    scheduler = make_scheduler(db, settings)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


auth = BasicAuth(settings.basic_auth_user, settings.basic_auth_hash) if settings.basic_auth_user and settings.basic_auth_hash else None
if auth is None:
    logging.getLogger("auth").warning("BASIC_AUTH_USER/BASIC_AUTH_HASH not set: site is NOT password protected")


@app.middleware("http")
async def require_basic_auth(request: Request, call_next):
    if auth is None or request.url.path == "/healthz" or auth.check(request.headers.get("authorization")):
        return await call_next(request)
    return Response("Authentication required", status_code=401, headers={"WWW-Authenticate": 'Basic realm="Danish News"'})


@app.middleware("http")
async def noindex(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /\n"


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def feed(request: Request, source: str | None = None, section: str | None = None):
    return templates.TemplateResponse(request, "feed.html", {
        "articles": db.list_articles(source or None, section or None),
        "sources": db.source_names(),
        "sections": db.sections(source or None),
        "cur_source": source or "",
        "cur_section": section or "",
    })


@app.get("/article/{article_id}", response_class=HTMLResponse)
def article(request: Request, article_id: int):
    art = db.get_article(article_id)
    if art is None:
        raise HTTPException(404, "Article not found")
    db.mark_read(article_id)
    return templates.TemplateResponse(request, "article.html", {
        "article": art, "paragraphs": db.get_paragraphs(article_id),
    })


_usage_cache: tuple[float, dict[str, int]] | None = None


@app.get("/api/usage")
async def usage() -> dict[str, int]:
    """DeepL quota, cached for 60s. Returns 204-style empty object if unavailable."""
    global _usage_cache
    now = time.monotonic()
    if _usage_cache and now - _usage_cache[0] < 60:
        return _usage_cache[1]
    try:
        used, limit = await run_in_threadpool(translator.provider.usage)  # type: ignore[attr-defined]
    except (TranslationError, AttributeError):
        return {}
    _usage_cache = (now, {"used": used, "limit": limit})
    return _usage_cache[1]


class TranslateRequest(BaseModel):
    paragraph_id: int | None = None
    article_id: int | None = None
    field: str | None = None


_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(key: str) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.translate_rate_limit_per_minute:
        raise HTTPException(429, "Too many translation requests")
    q.append(now)


@app.post("/api/translate")
async def translate(req: TranslateRequest, request: Request) -> dict[str, str]:
    rate_limit(request.client.host if request.client else "unknown")
    context: str | None = None
    if req.paragraph_id is not None:
        p = db.get_paragraph(req.paragraph_id)
        if p is None:
            raise HTTPException(404, "Paragraph not found")
        text, h = p["text_da"], p["text_hash"]
        art = db.get_article(p["article_id"])
        context = art["title"] if art else None
    elif req.article_id is not None and req.field == "title":
        art = db.get_article(req.article_id)
        if art is None:
            raise HTTPException(404, "Article not found")
        text = art["title"]
        h = text_hash(text)
    else:
        raise HTTPException(422, "Provide paragraph_id, or article_id with field='title'")
    try:
        text_en = await run_in_threadpool(translator.get, text, h, context)
    except TranslationError as e:
        raise HTTPException(502, str(e))
    global _usage_cache
    _usage_cache = None  # quota may have changed
    return {"text_en": text_en}
