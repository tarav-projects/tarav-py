"""The ObjectGroup view: members reached through registered links, upstream first."""

from __future__ import annotations

import pytest

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context import explore
from tarav.l1.context.groups import Link, Member, ObjectGroup, register_links
from tarav.l1.context.workflow import CONTEXT_WORKFLOW_SHIP


class Seed(TaravObject):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name, self.plant = name, None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3c1e9a52-7f04-4d6b-b8a1-2e5f0c9d7b13"),
                          name="Tarav.Test.Group.Seed", workflow=CONTEXT_WORKFLOW_SHIP)


class Plant(TaravObject):
    def __init__(self, seed: Seed, fruits: list[str]) -> None:
        super().__init__()
        self.seed, self.fruits = seed, fruits
        seed.plant = self

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("8a4d2f71-0c3e-4b95-a6d8-5f1b7e2c9a04"),
                          name="Tarav.Test.Group.Plant", workflow=CONTEXT_WORKFLOW_SHIP)


class Pebble(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e6b0c3d9-4a17-4f28-9c5e-7d3a1b8f0e62"),
                          name="Tarav.Test.Group.Pebble", workflow=CONTEXT_WORKFLOW_SHIP)


def _seed(seed: Seed) -> Member:
    return Member("seed", member_type=entity(Seed).name, key=seed.name, obj=seed)


def _plant(plant: Plant) -> Member:
    return Member("plant", member_type=entity(Plant).name, key=plant.seed.name, obj=plant)


def seed_links(seed: Seed):
    # the seed knows its soil, which has no Type, and its plant
    yield Link(Member("soil", value={"ph": 6.5}), _seed(seed))
    if seed.plant is not None:
        yield Link(_seed(seed), _plant(seed.plant))


def plant_links(plant: Plant):
    yield Link(_seed(plant.seed), _plant(plant))
    for fruit in plant.fruits:
        yield Link(_plant(plant), Member("fruit", member_type="Tarav.Test.Group.Fruit", key=fruit))


register_links(Seed, seed_links)
register_links(Plant, plant_links)


def _rows(view: ObjectGroup) -> list[tuple]:
    return [(entry.name, entry.open().records.to_record()) for entry in view.ls()]


def test_every_member_opens_the_same_group_upstream_first():
    seed = Seed("apple")
    plant = Plant(seed, ["b", "a"])

    from_seed, from_plant = (explore(subject, views=(ObjectGroup,)) for subject in (seed, plant))

    expected = [
        ("soil", {"type": "Tarav.Context.Group.Member", "role": "soil", "value": {"ph": 6.5}}),
        ("seed", {"type": "Tarav.Context.Group.Member", "role": "seed",
                  "member_type": "Tarav.Test.Group.Seed", "key": "apple"}),
        ("plant", {"type": "Tarav.Context.Group.Member", "role": "plant",
                   "member_type": "Tarav.Test.Group.Plant", "key": "apple"}),
        ("fruit-1", {"type": "Tarav.Context.Group.Member", "role": "fruit",
                     "member_type": "Tarav.Test.Group.Fruit", "key": "a"}),
        ("fruit-2", {"type": "Tarav.Context.Group.Member", "role": "fruit",
                     "member_type": "Tarav.Test.Group.Fruit", "key": "b"}),
    ]
    assert _rows(from_seed) == expected
    assert _rows(from_plant) == expected
    assert from_plant.members[2].obj is plant


def test_a_member_known_only_by_its_type_is_not_followed():
    seed = Seed("pear")  # no plant: its links stop at the seed

    assert [entry.name for entry in explore(seed, views=(ObjectGroup,)).ls()] == ["soil", "seed"]


def test_an_object_without_links_has_no_group():
    with pytest.raises(TypeError, match="ObjectGroup does not support"):
        explore(Pebble(), views=(ObjectGroup,))


def test_a_member_round_trips_through_its_record():
    member = Member("poi", member_type="Tarav.POI", id="0" * 64)
    loaded = Member.records.from_record(member.records.to_record())

    assert (loaded.role, loaded.member_type, loaded.id, loaded.obj) == ("poi", "Tarav.POI",
                                                                         "0" * 64, None)
