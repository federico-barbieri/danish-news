import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
import trafilatura

from .config import USER_AGENT, Settings
from .db import Database

log = logging.getLogger("fetcher")

BOILERPLATE_PREFIXES = (
    "læs også", "læs mere", "se også", "se mere", "læs her", "foto:", "foto :", "video:",
    "tip os", "kontakt ", "abonnér", "del denne", "følg ", "dr nyheder", "redigeret ",
)
SKIP_URL_PARTS = ("liveblog", "focusid=", "/play/", "/drtv/", "/lyd/")


@dataclass
class Extracted:
    title: str | None
    teaser: str | None
    image: str | None
    paragraphs: list[str]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_paragraphs(raw: str) -> list[str]:
    out: list[str] = []
    for line in raw.split("\n"):
        p = re.sub(r"\s+", " ", line).strip()
        if len(p) < 2:
            continue
        if p.lower().startswith(BOILERPLATE_PREFIXES):
            continue
        out.append(p)
    return out


def extract_article(html: str) -> Extracted | None:
    """Extract title, teaser, lead image and cleaned paragraphs from article HTML."""
    body = trafilatura.extract(
        html, include_comments=False, include_tables=False, include_images=False, favor_precision=True
    )
    if not body:
        return None
    paragraphs = clean_paragraphs(body)
    if not paragraphs:
        return None
    meta = trafilatura.extract_metadata(html)
    return Extracted(
        title=meta.title if meta else None,
        teaser=meta.description if meta else None,
        image=meta.image if meta else None,
        paragraphs=paragraphs,
    )


def _published(entry: feedparser.FeedParserDict) -> str:
    for key in ("published", "updated"):
        if entry.get(key):
            try:
                dt = parsedate_to_datetime(entry[key])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_fetch(db: Database, settings: Settings, client: httpx.Client | None = None) -> dict[str, int]:
    """Fetch all enabled feeds, store new articles. Never raises for per-article failures."""
    stats = {"new": 0, "skipped": 0, "failed": 0}
    own_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
    )
    try:
        for src in db.enabled_sources():
            try:
                resp = client.get(src["feed_url"])
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
            except Exception as e:
                log.warning("feed failed %s: %s", src["feed_url"], e)
                stats["failed"] += 1
                continue
            for entry in feed.entries:
                url = (entry.get("link") or "").strip()
                if not url:
                    continue
                if any(part in url.lower() for part in SKIP_URL_PARTS) or db.article_exists(url):
                    stats["skipped"] += 1
                    continue
                time.sleep(settings.request_delay_seconds)
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    ex = extract_article(r.text)
                    if ex is None:
                        log.info("no extractable text: %s", url)
                        stats["failed"] += 1
                        continue
                    title = (entry.get("title") or ex.title or "").strip()
                    if not title:
                        stats["failed"] += 1
                        continue
                    image = ex.image
                    if not image and entry.get("media_content"):
                        image = entry["media_content"][0].get("url")
                    aid = db.add_article(
                        source_id=src["id"], url=url, title=title, teaser=ex.teaser,
                        section=src["section"], published_at=_published(entry), lead_image_url=image,
                        paragraphs=ex.paragraphs, hashes=[text_hash(p) for p in ex.paragraphs],
                    )
                    if aid:
                        stats["new"] += 1
                        log.info("new article %s: %s", aid, title)
                except Exception as e:
                    log.warning("article failed %s: %s", url, e)
                    stats["failed"] += 1
        removed = db.delete_older_than(settings.retention_days)
        log.info("fetch done: %s, removed %d old", stats, removed)
    finally:
        if own_client:
            client.close()
    return stats
