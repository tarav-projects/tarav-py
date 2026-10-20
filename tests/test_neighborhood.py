"""The neighborhood of an object: itself by default, and what its class adds."""

from __future__ import annotations

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context import ContextEdge
from tarav.l1.neighborhood import NEIGHBOR, NEIGHBORHOOD_WORKFLOW_SHIP, neighborhood
from tarav.l3.runtime import create_runtime


class Lamp(TaravObject):
    """An object that declares no neighbors."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1b36493f-2238-4ca2-bf77-6fce95e387a6"),
                          name="Tarav.Test.Neighborhood.Lamp", workflow=NEIGHBORHOOD_WORKFLOW_SHIP)


class Switch(TaravObject):
    """An object shown with the lamp it turns on."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("abf1e7c2-44c5-4209-96d4-ca63de15e65f"),
                          name="Tarav.Test.Neighborhood.Switch", workflow=NEIGHBORHOOD_WORKFLOW_SHIP)

    def __init__(self, lamp: Lamp) -> None:
        super().__init__()
        self.lamp = lamp

    class Context(TaravObject.Context):
        def _obj_context_hook(self, cxt) -> None:
            super()._obj_context_hook(cxt)
            cxt.triplets.append((self.obj, NEIGHBOR, self.obj.lamp))


def test_by_default_an_objects_neighborhood_is_itself():
    create_runtime()
    lamp = Lamp()
    (only,) = neighborhood(lamp)
    assert only is lamp
    # and that default adds nothing to its context
    assert [edge.predicate for edge in lamp.context().ls()] == ["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"]
    # a class is its representing object, its TaravClass
    assert [type_.id for type_ in neighborhood(Lamp)] == [entity(Lamp).id]


def test_a_class_adds_its_neighbors_after_the_object_itself():
    create_runtime()
    lamp = Lamp()
    switch = Switch(lamp)
    found = neighborhood(switch)
    assert len(found) == 2 and found[0] is switch and found[1] is lamp
    # a declared neighbor is an ordinary triple of the object's context; itself is not
    edges = switch.context().ls()
    assert ContextEdge("out", NEIGHBOR, lamp) in edges
    assert [edge for edge in edges if edge.predicate == NEIGHBOR] == [ContextEdge("out", NEIGHBOR, lamp)]
