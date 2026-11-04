"""Mehrsprachige Stimmen: jedes gelistete Wort, und die Fallen dazwischen."""

from pathlib import Path

import pytest

from cave_dig.languages import LanguageError, fold_token, load_languages

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def table():
    return load_languages(ROOT / "languages.yaml")


CASES = [
    ("links", "left"),
    ("RECHTS", "right"),
    ("  Gauche  ", "left"),
    ("go left now", "left"),
    ("nach rechts bitte", "right"),
    ("LEFT!!!", "left"),
    ("li", "left"),
    ("hello li", None),
    ("l", "left"),
    ("r", "right"),
    ("re", "right"),
    ("re:", None),
    ("brilliant", None),
    ("alright", None),
    ("leftover food", None),
    ("linksrechts", None),
    ("solar", None),
    ("left right", None),
    ("<>", None),
    ("<", "left"),
    (">", "right"),
    (">>>", "right"),
    ("<3", None),
    ("5 > 3", None),
    ("左", "left"),
    ("右", "right"),
    ("今日は左", None),
    ("go 左", "left"),
    ("ひだり", "left"),
    ("みぎ", "right"),
    ("왼쪽", "left"),
    ("오른쪽", "right"),
    ("sağ", "right"),
    ("sag", "right"),
    ("SAG", "right"),
    ("höger", "right"),
    ("høyre", "right"),
    ("højre", "right"),
    ("vänster", "left"),
    ("stânga", "left"),
    ("αριστερά", "left"),
    ("ΑΡΙΣΤΕΡΑ", "left"),
    ("δεξιά", "right"),
    ("يسار", "left"),
    ("يَسَار", "left"),
    ("يمين", "right"),
    ("बाएँ", "left"),
    ("दाएँ", "right"),
    ("kiri", "left"),
    ("kanan", "right"),
    ("trái", "left"),
    ("phải", "right"),
    ("trai", "left"),
    ("ซ้าย", "left"),
    ("ขวา", "right"),
    ("налево", "left"),
    ("направо", "right"),
    ("ліво", "left"),
    ("праворуч", "right"),
    ("izquierda", "left"),
    ("direita", "right"),
    ("sinistra", "left"),
    ("lewo", "left"),
    ("oikea", "right"),
    ("vlevo", "left"),
    ("doleva", "left"),
    ("venstre", "left"),
    ("←", "left"),
    ("→", "right"),
    ("⬅️", "left"),
    ("➡️", "right"),
    ("👈", "left"),
    ("👉", "right"),
    ("go →", "right"),
    ("ＬＥＦＴ", "left"),
    ("lin\u200dks", "left"),
    ("", None),
    ("   ", None),
    ("haha", None),
    (None, None),
    (12, None),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_parse_cases(table, text, expected):
    assert table.parse(text) == expected


def test_every_listed_word_parses(table):
    for entry in table.words:
        assert table.parse(entry.word) == entry.direction


def test_hints_are_directions_or_arrows(table):
    for hint in table.hints:
        assert table.parse(hint) in ("left", "right")


def test_fold_examples():
    assert fold_token("Sağ") == fold_token("sag")
    assert fold_token("höger") == "hoger"
    assert fold_token("højre") == "hojre"
    assert fold_token("høyre") == "hoyre"
    assert fold_token("stânga") == "stanga"
    assert fold_token("trái") == "trai"
    # Thai-Tonzeichen bleibt, sonst würden verschiedene Wörter zusammenfallen.
    assert "\u0e49" in fold_token("ซ้าย")


def test_conflicting_word_is_rejected(tmp_path):
    path = tmp_path / "languages.yaml"
    path.write_text(
        "left:\n  - {word: links, lang: de}\nright:\n  - {word: links, lang: en}\n",
        encoding="utf-8",
    )
    with pytest.raises(LanguageError):
        load_languages(path)
