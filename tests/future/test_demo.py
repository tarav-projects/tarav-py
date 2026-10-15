"""Real JSON → object → RDF and progressive navigation without a mock engine."""

import importlib.util

import pytest

HAS_RDF = importlib.util.find_spec("rdflib") is not None
pytestmark = pytest.mark.skipif(not HAS_RDF, reason="Install tarav[future] for RDF checks")
if HAS_RDF:
    from tarav.l1._future.context import ContextViewEntry
    from tarav.l1._future.conversations import ABOUT, AUTHOR
    from tarav.l2._future.demo import ALICE_ID, BOB_ID, CHAT_ID, LIVE_ID, Demo


def objects(view):
    return [entry.open() for entry in view.ls() if not isinstance(entry, ContextViewEntry)]


# tarav.context 473c89a0:8944495a171e5499
def test_record_backed_demo_and_runtime_expansion_use_the_same_provider(tmp_path):
    demo = Demo(tmp_path).seed()
    explorer = demo.open()
    initial = explorer.diagram.triple_count
    root = explorer.view
    assert "messages" in root.available_views()
    assert demo.diagram.triple_count == initial
    explorer.select("messages")
    held = explorer.view
    assert {obj.id for obj in objects(held)} == {ALICE_ID, BOB_ID}
    explorer.select("by-alice")
    assert [obj.id for obj in objects(explorer.view)] == [ALICE_ID]
    explorer.expand("runtime-turn")
    assert {obj.id for obj in objects(held)} == {ALICE_ID, BOB_ID, LIVE_ID}
    assert {obj.id for obj in objects(explorer.view)} == {ALICE_ID, LIVE_ID}
    assert str(LIVE_ID) not in demo.store.names()
    assert demo.source(demo.resolve(str(LIVE_ID))) is None
    assert demo.source(demo.resolve(str(ALICE_ID))).is_file()
    assert explorer.subject.id == CHAT_ID
    assert len(explorer.view.qualifications) == 2


def test_loaded_annotation_is_discoverable_through_an_incoming_query(tmp_path):
    demo = Demo(tmp_path).seed()
    explorer = demo.open()
    explorer.expand("annotation")
    explorer.follow(demo.resolve(str(ALICE_ID))).select("in")
    assert any(entry.predicate is ABOUT for entry in explorer.ls())
    result = list(explorer.query(
        "SELECT ?who WHERE { ?focus ?author ?who }", bindings={"author": AUTHOR},
    ))
    assert [str(row.who) for row in result] == ["alice"]


def test_a_fresh_demo_reloads_records_without_retaining_runtime_nodes(tmp_path):
    first = Demo(tmp_path).seed()
    first.open().expand("runtime-turn")
    second = Demo(tmp_path).seed()
    explorer = second.open().select("messages")
    assert {obj.id for obj in objects(explorer.view)} == {ALICE_ID, BOB_ID}
    assert {offer.key for offer in explorer.expansions()} == {"runtime-turn", "annotation"}
