"""!event erkennt Aliase und lässt normalen Text in Ruhe."""

from cave_dig.commands import parse_event_command

ALIASES = {
    "einsturz": "cave_in",
    "dunkelheit": "darkness",
    "sprengung": "explosion",
    "erzader": "ore_vein",
}


def test_random_and_named_events():
    assert parse_event_command("!event", "!event", ALIASES).event_id is None
    assert parse_event_command("!EVENT Einsturz", "!event", ALIASES).event_id == "cave_in"
    parsed = parse_event_command("!event blabla", "!event", ALIASES)
    assert parsed.unknown == "blabla"
    assert parse_event_command("!eventuell links", "!event", ALIASES) is None
    assert parse_event_command("links", "!event", ALIASES) is None
    assert parse_event_command("!event zufall", "!event", ALIASES).event_id is None
