import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DEFAULT_FEEDS

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    section TEXT,
    feed_url TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    teaser TEXT,
    section TEXT,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    lead_image_url TEXT,
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE TABLE IF NOT EXISTS paragraphs (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text_da TEXT NOT NULL,
    text_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paragraphs_article ON paragraphs(article_id, position);
CREATE TABLE IF NOT EXISTS translations (
    text_hash TEXT PRIMARY KEY,
    text_en TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        # In-memory DBs are per-connection, so share one for tests.
        if self.path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = self._connect()
            yield self._memory_conn
            self._memory_conn.commit()
            return
        c = self._connect()
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        return c

    def init(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA)
            for name, url, section in DEFAULT_FEEDS:
                c.execute(
                    "INSERT OR IGNORE INTO sources (name, section, feed_url) VALUES (?, ?, ?)",
                    (name, section, url),
                )

    # --- sources ---
    def enabled_sources(self) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute("SELECT * FROM sources WHERE enabled = 1").fetchall()

    def source_names(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT s.name FROM sources s JOIN articles a ON a.source_id = s.id ORDER BY s.name"
            ).fetchall()
            return [r["name"] for r in rows]

    # --- articles ---
    def article_exists(self, url: str) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone() is not None

    def add_article(
        self,
        *,
        source_id: int,
        url: str,
        title: str,
        teaser: str | None,
        section: str | None,
        published_at: str,
        lead_image_url: str | None,
        paragraphs: list[str],
        hashes: list[str],
    ) -> int | None:
        with self.conn() as c:
            cur = c.execute(
                """INSERT OR IGNORE INTO articles
                   (source_id, url, title, teaser, section, published_at, fetched_at, lead_image_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_id, url, title, teaser, section, published_at, now_iso(), lead_image_url),
            )
            if cur.rowcount == 0:
                return None
            aid = cur.lastrowid
            c.executemany(
                "INSERT INTO paragraphs (article_id, position, text_da, text_hash) VALUES (?, ?, ?, ?)",
                [(aid, i, t, h) for i, (t, h) in enumerate(zip(paragraphs, hashes))],
            )
            return aid

    def list_articles(
        self, source: str | None = None, section: str | None = None, limit: int = 100
    ) -> list[sqlite3.Row]:
        sql = "SELECT a.*, s.name AS source_name FROM articles a JOIN sources s ON s.id = a.source_id WHERE 1=1"
        args: list[object] = []
        if source:
            sql += " AND s.name = ?"
            args.append(source)
        if section:
            sql += " AND a.section = ?"
            args.append(section)
        sql += " ORDER BY a.published_at DESC LIMIT ?"
        args.append(limit)
        with self.conn() as c:
            return c.execute(sql, args).fetchall()

    def sections(self, source: str | None = None) -> list[str]:
        sql = "SELECT DISTINCT a.section FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.section IS NOT NULL"
        args: list[object] = []
        if source:
            sql += " AND s.name = ?"
            args.append(source)
        with self.conn() as c:
            return [r[0] for r in c.execute(sql + " ORDER BY 1", args).fetchall()]

    def get_article(self, article_id: int) -> sqlite3.Row | None:
        with self.conn() as c:
            return c.execute(
                "SELECT a.*, s.name AS source_name FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ?",
                (article_id,),
            ).fetchone()

    def get_paragraphs(self, article_id: int) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute(
                "SELECT * FROM paragraphs WHERE article_id = ? ORDER BY position", (article_id,)
            ).fetchall()

    def mark_read(self, article_id: int) -> None:
        with self.conn() as c:
            c.execute("UPDATE articles SET read_at = COALESCE(read_at, ?) WHERE id = ?", (now_iso(), article_id))

    def delete_older_than(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            n = c.execute("DELETE FROM articles WHERE published_at < ?", (cutoff,)).rowcount
            c.execute("DELETE FROM translations WHERE created_at < ? AND text_hash NOT IN (SELECT text_hash FROM paragraphs)", (cutoff,))
            return n

    # --- translations ---
    def get_paragraph(self, paragraph_id: int) -> sqlite3.Row | None:
        with self.conn() as c:
            return c.execute("SELECT * FROM paragraphs WHERE id = ?", (paragraph_id,)).fetchone()

    def get_cached_translation(self, text_hash: str) -> str | None:
        with self.conn() as c:
            r = c.execute("SELECT text_en FROM translations WHERE text_hash = ?", (text_hash,)).fetchone()
            return r["text_en"] if r else None

    def cached_translations(self, hashes: list[str]) -> dict[str, str]:
        if not hashes:
            return {}
        with self.conn() as c:
            q = ",".join("?" * len(hashes))
            rows = c.execute(f"SELECT text_hash, text_en FROM translations WHERE text_hash IN ({q})", hashes).fetchall()
            return {r["text_hash"]: r["text_en"] for r in rows}

    def save_translation(self, text_hash: str, text_en: str, provider: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO translations (text_hash, text_en, provider, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, text_en, provider, now_iso()),
            )
