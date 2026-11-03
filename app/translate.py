import logging
from typing import Protocol

import httpx

from .config import Settings
from .db import Database

log = logging.getLogger("translate")


class TranslationError(Exception):
    pass


class Translator(Protocol):
    name: str

    def translate(self, text: str, context: str | None = None) -> str: ...


class DeepLTranslator:
    name = "deepl"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.s = settings
        self.client = client or httpx.Client(timeout=30)

    def translate(self, text: str, context: str | None = None) -> str:
        if not self.s.deepl_api_key:
            raise TranslationError("DEEPL_API_KEY is not set")
        body: dict[str, object] = {"text": [text], "source_lang": "DA", "target_lang": self.s.deepl_target}
        if context:
            body["context"] = context  # not billed; improves disambiguation
        try:
            r = self.client.post(
                self.s.deepl_url, json=body,
                headers={"Authorization": f"DeepL-Auth-Key {self.s.deepl_api_key}"},
            )
        except httpx.HTTPError as e:
            raise TranslationError(f"DeepL unreachable: {e}") from e
        if r.status_code == 429:
            raise TranslationError("DeepL rate limit hit, try again shortly")
        if r.status_code == 456:
            raise TranslationError("DeepL quota exceeded")
        if r.status_code != 200:
            raise TranslationError(f"DeepL error {r.status_code}")
        return r.json()["translations"][0]["text"]


    def usage(self) -> tuple[int, int]:
        """Return (characters used, character limit) for the current billing period."""
        url = self.s.deepl_url.rsplit("/", 1)[0] + "/usage"
        try:
            r = self.client.get(url, headers={"Authorization": f"DeepL-Auth-Key {self.s.deepl_api_key}"})
            r.raise_for_status()
            d = r.json()
            return int(d["character_count"]), int(d["character_limit"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise TranslationError(f"Could not read DeepL usage: {e}") from e


class CachedTranslator:
    """Cache layer keyed by hash of the Danish text, in front of any Translator."""

    def __init__(self, db: Database, provider: Translator):
        self.db = db
        self.provider = provider

    def get(self, text: str, text_hash: str, context: str | None = None) -> str:
        cached = self.db.get_cached_translation(text_hash)
        if cached is not None:
            return cached
        result = self.provider.translate(text, context)
        self.db.save_translation(text_hash, result, self.provider.name)
        return result
