"""Queries use RDFLib itself against the incrementally contributed graph."""

import pytest
from rdflib import Literal

from tarav.l0.kernel import Ship, entity
from tarav.l1._future import future
from tarav.l1._future.context import Along, Where
from tarav.l1._future.conversations import AUTHOR, HAS_TURN, IN_CHAT, Conversation, UserTurn
from tarav.l1._future.graph import Diagram, RDFValue


def example():
    graph = Diagram()
    chat = Conversation(Ship("a06ba19f-37e1-4633-9618-533d8af20a6a"), "Example")
    alice = UserTurn(Ship("4e415464-c066-4fa5-8429-cb65096e56ab"), chat.id, "alice", "First")
    bob = UserTurn(Ship("0b8de1ed-356c-47d6-ac25-fbe8ac600afe"), chat.id, "bob", "Second")
    def contribute(turn, diagram):
        diagram.relate(turn, IN_CHAT, chat)
        diagram.relate(turn, AUTHOR, turn.author)
    graph.register(UserTurn, contribute)
    graph.relate(chat, HAS_TURN, alice)
    graph.expand(alice)
    graph.offer(chat, "bob", "Load Bob's runtime turn", lambda diagram: (
        diagram.relate(chat, HAS_TURN, bob), diagram.expand(bob),
    ))
    return graph, chat, alice, bob


# tarav.context 473c89a0:2231281cb94571ae
def test_same_view_observes_new_triples_without_losing_qualifications():
    graph, chat, alice, bob = example()
    explorer = future(chat).context(diagram=graph, views=(Along(HAS_TURN),))
    held = explorer.view
    assert [entry.open().id for entry in held.ls()] == [alice.id]
    before = graph.revision
    explorer.expand("bob")
    assert graph.revision > before
    assert {entry.open().id for entry in held.ls()} == {alice.id, bob.id}
    explorer.refine(views=(Where(AUTHOR, Literal("alice")),))
    assert [entry.open().id for entry in explorer.ls()] == [alice.id]
    explorer.refine(views=(Where(AUTHOR, Literal("bob")),))
    assert explorer.ls() == ()
    assert len(explorer.view.qualifications) == 3


def test_listing_loading_offers_and_views_does_not_load_class_models():
    graph, chat, _, _ = example()
    root = future(chat).context(diagram=graph)
    before = graph.triple_count
    assert [entry.name for entry in root.ls()] == ["out", "in", "type", "model"]
    assert [offer.key for offer in root.expansions()] == ["bob"]
    assert graph.triple_count == before


def test_direct_sparql_and_representations_of_predicate_and_occurrence():
    graph, chat, alice, _ = example()
    rows = list(graph.query("SELECT ?target WHERE { ?focus ?p ?target }",
                            bindings={"focus": chat, "p": HAS_TURN}))
    assert [graph.resolve(row.target).id for row in rows] == [alice.id]
    entry = future(chat).context(diagram=graph, views=(Along(HAS_TURN),)).ls()[0]
    assert entry.predicate is HAS_TURN
    assert entry.relation.subject is chat
    assert entry.relation.target is alice
    graph.expand(entry.relation)
    assert graph.resolve(graph.ref(entry.relation)) is entry.relation
    assert graph.resolve(str(alice.id)) is alice


def test_incoming_navigation_and_history_keep_loaded_graph():
    graph, chat, alice, bob = example()
    explorer = future(chat).context(diagram=graph)
    explorer.expand("bob")
    loaded = graph.triple_count
    explorer.follow(alice).select("in")
    assert any(entry.open() is chat and entry.predicate is HAS_TURN for entry in explorer.ls())
    explorer.back().back()
    assert explorer.subject is chat
    assert graph.triple_count >= loaded
    explorer.forward()
    assert explorer.subject is alice
    assert graph.resolve(graph.ref(bob)) is bob


def test_class_models_reuse_existing_class_and_member_identities():
    graph, _, alice, _ = example()
    model = future(alice).context(diagram=graph).open("model")
    assert {entry.open().path for entry in model.ls()} == {
        "conversation", "author", "text", "read_text",
    }
    assert graph.resolve(graph.ref(UserTurn)).id == entity(UserTurn).id


def test_literal_representation_preserves_language_and_datatype():
    graph = Diagram()
    value = Literal("hello", lang="en")
    obj = graph.resolve(value)
    assert isinstance(obj, RDFValue)
    assert RDFValue.records.from_record(obj.records.to_record()).value == value


@pytest.mark.parametrize("query", [
    "SELECT * FROM <https://example.org/data> WHERE { ?s ?p ?o }",
    "SELECT * WHERE { SERVICE <https://example.org/query> { ?s ?p ?o } }",
])
def test_queries_cannot_escape_the_loaded_graph(query):
    with pytest.raises(ValueError, match="loaded graph"):
        Diagram().query(query)
