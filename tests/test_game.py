"""Die Runde rechnet ohne Fenster: fallen, punkten, neu starten, speichern."""

import logging
from pathlib import Path

from cave_dig.chat.base import ChatMessage
from cave_dig.config import load_config
from cave_dig.game import Game
from cave_dig.languages import load_languages

ROOT = Path(__file__).resolve().parents[1]


def _game(tmp_path, seed=4):
    config = load_config(ROOT / "config.yaml")
    languages = load_languages(ROOT / "languages.yaml")
    # Eigene Speicherdatei, damit der Test nicht den echten Stand anfasst.
    from dataclasses import replace

    config = replace(config, save_path=tmp_path / "stand.json")
    return Game(config, languages, seed=seed)


def test_pickaxe_descends_and_scores(tmp_path):
    game = _game(tmp_path)
    start = game.pickaxe.y
    game.handle_messages(
        [
            ChatMessage("Nora", "links"),
            ChatMessage("Kenji", "left"),
            ChatMessage("Omar", "gauche"),
            ChatMessage("Lina", "rechts"),
        ]
    )
    for _ in range(240):
        game.update(1 / 60)
    assert game.pickaxe.y > start + 120
    assert game.scoreboard.round_score > 0 or game.phase == "ended"
    assert game.max_depth > 0


def test_closed_window_nudges_and_credits(tmp_path):
    game = _game(tmp_path, seed=8)
    game.pickaxe.vx = 0
    game.pending_points = 100
    game.handle_messages([ChatMessage("Nora", "rechts"), ChatMessage("Kenji", "right")])
    # Das Fenster ist 2,5 s. update deckelt einen Schritt auf 0,05 s,
    # darum hier direkt auszählen, wie es die Spielschleife nach der Zeit tut.
    for result in game.votes.close_due(game.time + 2.5):
        game._apply_votes(result)
    assert game.pickaxe.vx > 0
    assert game.scoreboard.contributors["Nora"].points > 0
    assert game.scoreboard.contributors["Kenji"].votes == 1


def test_round_restarts_and_saves(tmp_path):
    game = _game(tmp_path, seed=9)
    for _ in range(90):
        game.update(1 / 60)
    game.pickaxe.integrity = -1000
    game.update(1 / 60)
    assert game.phase == "ended"
    assert game.end_reason
    assert (tmp_path / "stand.json").exists()
    # Pause abwarten. update deckelt dt, darum viele kleine Schritte.
    steps = int(game.config.round_end_pause / (1 / 60)) + 5
    for _ in range(steps):
        game.update(1 / 60)
    assert game.phase == "play"
    assert game.round_index == 2


def test_bad_chat_and_unknown_event_do_not_crash(tmp_path):
    game = _game(tmp_path, seed=2)
    game.handle_messages(
        [
            ChatMessage("Nora", ""),
            ChatMessage("", "left"),
            ChatMessage("Omar", "!event gibt_es_nicht"),
            ChatMessage("Lina", "今日は左へ行くよ"),
            ChatMessage("Kenji", "<<<"),
        ]
    )
    game.update(1 / 60)
    assert game.phase == "play"


def test_chat_during_the_round_pause_counts_in_the_next_round(tmp_path):
    game = _game(tmp_path, seed=9)
    game.pickaxe.integrity = -1000
    game.update(1 / 60)
    assert game.phase == "ended"
    game.handle_messages([ChatMessage("Nora", "links")])
    assert game.votes.left == 0
    for _ in range(int(game.config.round_end_pause * 60) + 5):
        game.update(1 / 60)
    assert game.round_index == 2
    assert game.votes.left == 1
    assert game.held_messages == []


def test_held_messages_are_limited(tmp_path):
    game = _game(tmp_path, seed=9)
    game.phase = "ended"
    game.handle_messages([ChatMessage(f"u{n}", "links") for n in range(1000)])
    assert len(game.held_messages) == 400
    assert game.held_messages[-1].author == "u999"


def test_ore_vein_keeps_bedrock_shelves(tmp_path):
    for seed in range(1, 21):
        game = _game(tmp_path, seed=seed)
        shelf = game.config.shelf_every * 2
        before = [game.world.type_of(col, shelf) for col in range(game.config.columns)]
        game.pickaxe.y = (shelf - 2) * game.block_size + 20
        game.pickaxe.x = 3.5 * game.block_size
        assert game.start_event("ore_vein", force=True)
        after = [game.world.type_of(col, shelf) for col in range(game.config.columns)]
        assert [kind == "bedrock" for kind in after] == [kind == "bedrock" for kind in before]


def test_chat_spam_does_not_reach_the_log(tmp_path, caplog):
    game = _game(tmp_path, seed=2)
    caplog.set_level(logging.DEBUG)
    game.handle_messages([ChatMessage("Nora", "!event \x1b[2Jboom")])
    assert "\x1b" not in caplog.text
    caplog.clear()
    caplog.set_level(logging.INFO)
    game.handle_messages([ChatMessage("Nora", "!event boom") for _ in range(50)])
    game.start_event("darkness", force=True)
    caplog.clear()
    game.handle_messages([ChatMessage("Nora", "!event") for _ in range(50)])
    assert caplog.records == []


def test_event_command_respects_cooldown(tmp_path):
    game = _game(tmp_path, seed=2)
    assert game.start_event("darkness", force=True) is True
    assert game.event is not None
    assert game.event_title() == "Darkness"
    game.update(1 / 60)
    assert game.light_scale() < 1
    game.handle_messages([ChatMessage("Nora", "!event einsturz")])
    assert game.event.id == "darkness"
