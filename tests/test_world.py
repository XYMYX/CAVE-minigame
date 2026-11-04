"""Höhle: gleiche Seed, gleiche Blöcke. Urgestein hält, Erde nicht."""

from pathlib import Path

from cave_dig.config import load_config
from cave_dig.world import World

ROOT = Path(__file__).resolve().parents[1]


def test_seed_is_stable_and_not_identical_for_another_seed():
    config = load_config(ROOT / "config.yaml")
    first = World(config, seed=5)
    second = World(config, seed=5)
    third = World(config, seed=6)
    assert first.type_of(3, 20) == second.type_of(3, 20)
    assert first.type_of(0, 20) == "bedrock"
    different = [
        first.type_of(col, row) != third.type_of(col, row)
        for col in range(2, 8)
        for row in range(6, 30)
    ]
    assert any(different)


def test_shelf_has_a_gap_and_bedrock_walls():
    config = load_config(ROOT / "config.yaml")
    world = World(config, seed=3)
    row = config.shelf_every * 2
    kinds = [world.type_of(col, row) for col in range(config.columns)]
    assert kinds[0] == "bedrock"
    assert kinds[-1] == "bedrock"
    assert kinds.count("bedrock") < config.columns
    gap = config.shelf_gap
    middle = kinds[config.wall_columns : config.columns - config.wall_columns]
    # Die Lücke ist zusammenhängend und nicht aus Urgestein.
    assert "bedrock" in middle
    assert any(kind != "bedrock" for kind in middle)
    assert sum(1 for kind in middle if kind != "bedrock") == gap


def test_dirt_breaks_and_bedrock_does_not():
    config = load_config(ROOT / "config.yaml")
    world = World(config, seed=1)
    world.set_kind(4, 10, "dirt")
    hit = world.touch(4, 10, now=1, cooldown=0.2)
    assert hit is not None and hit.broken
    assert hit.points == config.blocks["dirt"].points
    assert not world.is_solid(4, 10)

    world.set_kind(4, 11, "bedrock")
    solid = world.touch(4, 11, now=1, cooldown=0.2)
    assert solid is not None and solid.unbreakable and not solid.broken
    assert world.is_solid(4, 11)
    assert world.touch(4, 11, now=1.05, cooldown=0.2) is None

    world.set_kind(4, 12, "stone")
    first = world.touch(4, 12, now=2, cooldown=0.2)
    assert first is not None and not first.broken
    assert world.touch(4, 12, now=2.05, cooldown=0.2) is None
    second = world.touch(4, 12, now=2.3, cooldown=0.2)
    assert second is not None and second.broken
