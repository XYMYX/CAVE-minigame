"""Schriften: seltsame Zuschauernamen dürfen nichts abstürzen lassen."""

from pathlib import Path

import pygame
import pytest

from cave_dig.fonts import FontBook

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fonts():
    pygame.font.init()
    yield FontBook(ROOT / "assets" / "fonts")
    pygame.font.quit()


@pytest.mark.parametrize(
    "name",
    [
        "\U0001f579️ Max",  # Emoji fehlt in den Schriften, U+FE0F bleibt allein.
        "Max \U0001f336️",
        "A️B",
        "A︁B",
        "️",
        "؜",
    ],
)
def test_zero_width_characters_do_not_crash(fonts, name):
    assert fonts.render(name, 16, (255, 255, 255)).get_width() >= 1


def test_normal_text_still_has_all_letters(fonts):
    short = fonts.render("Ma", 16, (255, 255, 255)).get_width()
    assert fonts.render("Max", 16, (255, 255, 255)).get_width() > short
