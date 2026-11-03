from pathlib import Path

import pytest

from app.fetcher import clean_paragraphs, extract_article, text_hash

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,starts", [
    ("dr_seneste.html", "Københavns Politi"),
    ("dr_indland.html", "Elias blev kun 15 år"),
])
def test_dr_fixtures_extract(name: str, starts: str):
    ex = extract_article((FIX / name).read_text())
    assert ex is not None
    assert ex.paragraphs[0].startswith(starts)
    assert len(ex.paragraphs) >= 3
    assert all(p == p.strip() and p for p in ex.paragraphs)
    assert ex.teaser


def test_boilerplate_removed():
    raw = "Rigtigt afsnit her.\n\nLæs også: Noget andet\nFoto: Ritzau\n \nEt andet afsnit."
    assert clean_paragraphs(raw) == ["Rigtigt afsnit her.", "Et andet afsnit."]


def test_hash_is_stable():
    assert text_hash("hej") == text_hash("hej") != text_hash("Hej")
