"""Punkte teilen, Tiefe, Speicherdatei."""

import json

import pytest

from cave_dig.scoring import (
    Scoreboard,
    load_scoreboard,
    points_at_depth,
    save_scoreboard,
    split_points,
)


def test_split_is_fair_and_stable():
    shares = split_points(10, ["Nora", "Kenji", "Nora", "Omar"])
    # Alphabetisch bekommt Kenji den Restpunkt.
    assert shares == {"Kenji": 4, "Nora": 3, "Omar": 3}
    assert sum(shares.values()) == 10
    assert split_points(0, ["Nora"]) == {}
    assert split_points(5, []) == {}


@pytest.mark.parametrize(
    "content",
    [b'\xff\xfe{"high_score":1}', b'{"contributors":5}', b"[1, 2]", b"{"],
)
def test_broken_save_file_is_set_aside_not_a_crash(tmp_path, content):
    path = tmp_path / "stand.json"
    path.write_bytes(content)
    board = load_scoreboard(path)
    assert board.contributors == {}
    assert not path.exists()
    assert (tmp_path / "stand.broken.json").read_bytes() == content


def test_depth_bonus_is_capped():
    assert points_at_depth(100, 0, 0.002, 3) == 100
    assert points_at_depth(100, 500, 0.002, 3) == 200
    assert points_at_depth(100, 50_000, 0.002, 3) == 300
    assert points_at_depth(0, 10, 0.002, 3) == 0


def test_high_score_survives_round_reset():
    board = Scoreboard()
    board.add_round_points(120)
    board.add_contributor_points("Nora", 80)
    board.add_vote("Nora")
    board.finish_round(40)
    assert board.high_score == 120
    assert board.best_depth == 40
    assert board.round_score == 0
    assert board.rounds_played == 1
    assert board.top(1)[0].name == "Nora"
    board.add_round_points(50)
    board.finish_round(10)
    assert board.high_score == 120
    assert board.best_depth == 40


def test_save_roundtrip_and_corrupt_file(tmp_path):
    board = Scoreboard()
    board.add_round_points(90)
    board.add_contributor_points("Kenji", 90)
    board.add_vote("Kenji")
    board.finish_round(15)
    path = tmp_path / "stand.json"
    save_scoreboard(path, board)
    loaded = load_scoreboard(path)
    assert loaded.high_score == 90
    assert loaded.best_depth == 15
    assert loaded.contributors["Kenji"].points == 90
    assert loaded.contributors["Kenji"].votes == 1

    path.write_text("{", encoding="utf-8")
    fresh = load_scoreboard(path)
    assert fresh.high_score == 0

    path.write_text(json.dumps({"high_score": -5, "contributors": [{"name": "", "points": 3}]}), encoding="utf-8")
    cleaned = load_scoreboard(path)
    assert cleaned.high_score == 0
    assert cleaned.contributors == {}
