import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

USER_AGENT = "danish-news-reader/0.1 (personal reader; non-commercial)"

# (name, feed_url, section label). Seeded into the DB on first run; edit the DB afterwards.
DEFAULT_FEEDS: list[tuple[str, str, str]] = [
    ("DR", "https://www.dr.dk/nyheder/service/feeds/senestenyt", "Seneste"),
    ("DR", "https://www.dr.dk/nyheder/service/feeds/indland", "Indland"),
    ("DR", "https://www.dr.dk/nyheder/service/feeds/udland", "Udland"),
    ("DR", "https://www.dr.dk/nyheder/service/feeds/penge", "Penge"),
    ("DR", "https://www.dr.dk/nyheder/service/feeds/politik", "Politik"),
]


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(os.getenv("DB_PATH", "data/news.db"))
    deepl_api_key: str = os.getenv("DEEPL_API_KEY", "")
    deepl_url: str = os.getenv("DEEPL_URL", "https://api-free.deepl.com/v2/translate")
    deepl_target: str = os.getenv("DEEPL_TARGET", "EN-GB")
    fetch_interval_minutes: int = int(os.getenv("FETCH_INTERVAL_MINUTES", "30"))
    retention_days: int = int(os.getenv("RETENTION_DAYS", "30"))
    request_delay_seconds: float = float(os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
    fetch_on_startup: bool = os.getenv("FETCH_ON_STARTUP", "1") == "1"
    basic_auth_user: str = os.getenv("BASIC_AUTH_USER", "")
    basic_auth_hash: str = os.getenv("BASIC_AUTH_HASH", "")
    translate_rate_limit_per_minute: int = int(os.getenv("TRANSLATE_RATE_LIMIT", "120"))


settings = Settings()
