"""Objects contribute triples; a Context Explorer collects and explores them."""

from __future__ import annotations

import pytest

from tarav.l0.kernel import RDF_TYPE, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context import ContextEdge, ContextExplorer
from tarav.l1.poi import POI
from tarav.l3.runtime import get_runtime

AUTHOR = "urn:tarav:test:author"
NAME = "urn:tarav:test:name"


class Person(TaravObject):
    """An object that adds a name and an author to its default triple."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0b6f3f43-57f0-4a5e-9a33-2d1fb7c58e01"),
                          name="Tarav.Test.Context.Person")

    def __init__(self, name: str, author: TaravObject | None = None) -> None:
        super().__init__()
        self.name, self.author = name, author

    class Context(TaravObject.Context):
        def triplets(self):
            person = self.obj
            added = [(person, NAME, person.name)]
            if person.author is not None:
                added.append((person, AUTHOR, person.author))
            return (*super().triplets(), *added)


def test_an_object_contributes_its_type_by_default() -> None:
    poi_class = entity(POI)
    [(subject, predicate, target)] = POI.context.triplets()
    assert (subject.id, predicate, target.id) == (poi_class.id, RDF_TYPE, entity(TaravClass).id)

    explorer = ContextExplorer(POI)
    [(own, kind, its_class)] = explorer.context.triplets()
    assert own is explorer and kind == RDF_TYPE and its_class.name == "Tarav.Context.Explorer"


def test_context_opens_an_explorer_focused_on_the_subject() -> None:
    get_runtime()  # composing the runtime configures `.context()`
    alice = Person("alice")
    explorer = alice.context()

    assert isinstance(explorer, ContextExplorer) and explorer.focus is alice
    edges = explorer.ls()
    assert sorted((edge.direction, edge.predicate) for edge in edges) == [("out", RDF_TYPE), ("out", NAME)]
    assert {edge.predicate: edge.node for edge in edges}[NAME] == "alice"
    assert {edge.predicate: edge.node for edge in edges}[RDF_TYPE].name == "Tarav.Test.Context.Person"


def test_following_opens_the_target_and_the_graph_only_grows() -> None:
    alice = Person("alice")
    bob = Person("bob", author=alice)
    explorer = ContextExplorer(bob)
    assert len(explorer.graph) == 3 and explorer.node(alice) not in explorer.opened

    explorer.follow(ContextEdge("out", AUTHOR, alice))
    assert explorer.focus is alice
    assert len(explorer.graph) == 5  # alice's type and name joined bob's three triples
    assert ContextEdge("in", AUTHOR, bob) in explorer.ls()

    explorer.follow(next(edge for edge in explorer.ls() if edge.predicate == RDF_TYPE))
    assert explorer.focus.name == "Tarav.Test.Context.Person"
    explorer.follow(next(edge for edge in explorer.ls() if edge.direction == "out"))
    assert explorer.focus.name == "Tarav.Class"
    # the class of classes is its own type: following it stays there
    explorer.follow(next(edge for edge in explorer.ls() if edge.direction == "out"))
    assert explorer.focus.name == "Tarav.Class"
    size = len(explorer.graph)

    assert explorer.back().back().focus.name == "Tarav.Test.Context.Person"
    assert explorer.back().focus is alice and explorer.back().focus is bob
    with pytest.raises(IndexError):
        explorer.back()
    assert explorer.forward().focus is alice
    assert len(explorer.graph) == size  # moving the cursor adds and removes nothing

    explorer.follow(ContextEdge("out", AUTHOR, alice))  # a new step drops the old forward path
    with pytest.raises(IndexError):
        explorer.forward()


def test_a_literal_cannot_be_followed_and_bad_triples_are_rejected() -> None:
    explorer = ContextExplorer(Person("alice"))
    with pytest.raises(TypeError, match="literal"):
        explorer.follow(next(edge for edge in explorer.ls() if edge.predicate == NAME))

    class Broken(Person):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip("8a0f6a4e-2b8b-4f3c-b2a1-6f0d7e9c3b12"),
                              name="Tarav.Test.Context.Broken")

        class Context(Person.Context):
            def triplets(self):
                return ((self.obj, entity(Person), "x"),)

    with pytest.raises(TypeError, match="IRI string"):
        ContextExplorer(Broken("x"))


def test_identifiers_open_through_the_resolver() -> None:
    explorer = get_runtime().context(Person("alice"))
    node = explorer.open("Tarav.POI")
    assert explorer.objects[node].id == entity(POI).id and node in explorer.opened
    assert explorer.focus.name == "alice"  # opening collects; only following moves

    with pytest.raises(KeyError, match="Nothing resolves"):
        ContextExplorer(Person("alice")).open("Tarav.POI")


def test_queries_run_over_what_is_open_and_open_nothing() -> None:
    alice = Person("alice")
    explorer = ContextExplorer(Person("bob", author=alice))
    select = f"SELECT ?who ?name WHERE {{ ?who <{NAME}> ?name }}"

    assert [row["name"] for row in explorer.query(select)] == ["bob"]
    assert explorer.query(f"ASK {{ ?x <{AUTHOR}> ?y }}") is True
    assert explorer.node(alice) not in explorer.opened

    explorer.open(alice)
    rows = explorer.query(select)
    assert sorted(row["name"] for row in rows) == ["alice", "bob"]
    assert {row["who"].name for row in rows} == {"alice", "bob"}
    assert {row["p"] for row in explorer.query("SELECT ?p WHERE { ?s ?p ?o }")} == {RDF_TYPE, NAME, AUTHOR}
    with pytest.raises(ValueError, match="SELECT and ASK"):
        explorer.query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
