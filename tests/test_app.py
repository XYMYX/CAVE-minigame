"""Die echte Spielschleife, ohne Fenster und mit eigener Speicherdatei."""

import json

from cave_dig import app
from cave_dig.chat.base import ChatMessage, ChatProvider
from cave_dig.render import Renderer


class OneVoter(ChatProvider):
    """Schickt genau eine Stimme und danach nichts mehr."""

    def __init__(self, author):
        super().__init__()
        self.author = author

    def start(self):
        return None

    def stop(self):
        return None

    def poll(self, now):
        author, self.author = self.author, None
        return [ChatMessage(author, "links")] if author else []


def _config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "game:\n"
        f"  save_path: {(tmp_path / 'stand.json').as_posix()}\n"
        f"  log_dir: {(tmp_path / 'logs').as_posix()}\n",
        encoding="utf-8",
    )
    return path


def _run(tmp_path, monkeypatch, author=None, frames=200):
    monkeypatch.setattr(app, "create_provider", lambda *args, **kwargs: OneVoter(author))
    return app.main(
        ["--headless", "--frames", str(frames), "--seed", "3", "--config", str(_config(tmp_path))]
    )


def test_name_with_invisible_character_survives_and_restarts(tmp_path, monkeypatch):
    name = "\U0001f579️ Max"
    assert _run(tmp_path, monkeypatch, name) == 0
    # Der Testlauf nutzt den Simulator und darf den echten Stand nicht berühren.
    assert not (tmp_path / "stand.json").exists()
    saved = json.loads((tmp_path / "stand.simulator.json").read_text(encoding="utf-8"))
    assert [entry["name"] for entry in saved["contributors"]] == [name]
    # Der Name steht jetzt im Stand und wird beim nächsten Start wieder gezeichnet.
    assert _run(tmp_path, monkeypatch) == 0


def test_bad_config_uses_the_exit_code_without_restart(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("game: [", encoding="utf-8")
    assert app.main(["--headless", "--config", str(path)]) == app.EXIT_BAD_CONFIG


def test_a_broken_frame_does_not_stop_the_stream(tmp_path, monkeypatch):
    def broken(self, target, game):
        raise RuntimeError("Testfehler beim Zeichnen")

    monkeypatch.setattr(Renderer, "draw", broken)
    assert _run(tmp_path, monkeypatch, frames=3) == 0


def test_lasting_error_ends_the_game_with_few_log_lines(tmp_path, monkeypatch, caplog):
    def broken(self, target, game):
        raise RuntimeError("Testfehler beim Zeichnen")

    monkeypatch.setattr(Renderer, "draw", broken)
    assert _run(tmp_path, monkeypatch, frames=app.FRAME_ERROR_LIMIT + 50) == 1
    assert sum("Fehler im Bild" in record.getMessage() for record in caplog.records) == 1
