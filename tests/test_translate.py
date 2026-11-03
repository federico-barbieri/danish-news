import httpx
import pytest

from app.config import Settings
from app.db import Database
from app.translate import CachedTranslator, DeepLTranslator, TranslationError


class Fake:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def translate(self, text, context=None):
        self.calls += 1
        return f"EN:{text}"


def test_cache_hits_provider_once():
    db = Database(":memory:")
    db.init()
    fake = Fake()
    t = CachedTranslator(db, fake)
    assert t.get("Hej verden", "h1") == "EN:Hej verden"
    assert t.get("Hej verden", "h1") == "EN:Hej verden"
    assert fake.calls == 1


def test_identical_text_shared_across_paragraphs():
    db = Database(":memory:")
    db.init()
    fake = Fake()
    t = CachedTranslator(db, fake)
    t.get("samme", "same-hash")
    t.get("samme", "same-hash")
    assert fake.calls == 1


def _deepl(handler, key="k"):
    s = Settings(deepl_api_key=key)
    return DeepLTranslator(s, httpx.Client(transport=httpx.MockTransport(handler)))


def test_deepl_request_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["Authorization"]
        seen["body"] = req.read().decode()
        return httpx.Response(200, json={"translations": [{"text": "Hello"}]})

    assert _deepl(handler).translate("Hej", "ctx") == "Hello"
    assert seen["auth"] == "DeepL-Auth-Key k"
    assert '"source_lang":"DA"' in seen["body"].replace(" ", "")


def test_deepl_errors():
    with pytest.raises(TranslationError):
        _deepl(lambda r: httpx.Response(456)).translate("x")
    with pytest.raises(TranslationError):
        _deepl(lambda r: httpx.Response(200), key="").translate("x")


def test_failures_are_not_cached():
    db = Database(":memory:")
    db.init()

    class Boom(Fake):
        def translate(self, text, context=None):
            raise TranslationError("nope")

    with pytest.raises(TranslationError):
        CachedTranslator(db, Boom()).get("x", "h")
    assert db.get_cached_translation("h") is None


def test_deepl_usage():
    def handler(req: httpx.Request):
        assert req.url.path == "/v2/usage"
        return httpx.Response(200, json={"character_count": 1200, "character_limit": 1000000})

    assert _deepl(handler).usage() == (1200, 1000000)
    with pytest.raises(TranslationError):
        _deepl(lambda r: httpx.Response(403)).usage()
