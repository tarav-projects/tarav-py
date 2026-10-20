from uuid import uuid4

import pytest

from tarav.l0.kernel import RDF_TYPE, Ship, entity
from tarav.l1.context import ContextEdge
from tarav.l1.lines import Block, Line
from tarav.l1.lines.context import explore
from tarav.l1.lines.predicates import CONTAINS, PARENT, RDF_MEMBERSHIP, SCOPE, TEXT
from tarav.l3.runtime import get_runtime


@pytest.fixture
def tree():
    get_runtime()
    root = Block(id=Ship(uuid4()))
    root.append(Line(id=Ship(uuid4()), text="Project context.", scope=root))
    model = Block(id=Ship(uuid4()), parent=root)
    first = Line(id=Ship(uuid4()), text="Preserve mixed order.", scope=model)
    model.append(first)
    child = Block(id=Ship(uuid4()), parent=model)
    child.append(Line(id=Ship(uuid4()), text="Nested caching principle.", scope=child))
    model.append(child)
    model.append(Line(id=Ship(uuid4()), text="A final principle.", scope=model))
    root.append(model)
    sibling = Block(id=Ship(uuid4()), parent=root)
    sibling.append(Line(id=Ship(uuid4()), text="Historical discussion only.", scope=sibling))
    root.append(sibling)
    return root, model, first, child, sibling


# tarav.breadcrumb ecdb813b2c9f
def test_lines_and_blocks_supply_typed_text_scope_structure_and_order(tree):
    root, model, first, child, _ = tree
    triplets = first.context.build().triplets
    assert (triplets[0][0], triplets[0][1], triplets[0][2].id) == (
        first, RDF_TYPE, entity(Line).id)
    assert triplets[1:] == [(first, TEXT, "Preserve mixed order."), (first, SCOPE, model)]
    triplets = model.context.build().triplets
    assert (triplets[0][0], triplets[0][1], triplets[0][2].id) == (
        model, RDF_TYPE, entity(Block).id)
    assert (model, PARENT, root) in triplets
    assert [target for _, predicate, target in triplets if predicate == CONTAINS] == [
        first, child, model.contents[2],
    ]
    assert [(predicate, target.id) for _, predicate, target in triplets
            if predicate.startswith(RDF_MEMBERSHIP)] == [
        (RDF_MEMBERSHIP + "1", first.id), (RDF_MEMBERSHIP + "2", child.id),
        (RDF_MEMBERSHIP + "3", model.contents[2].id),
    ]


# tarav.breadcrumb 54a4bbf6887b
def test_complete_subtree_is_queryable_with_ancestor_context_and_no_sibling_payload(tree):
    root, model, first, child, sibling = tree
    explorer = explore(model)
    assert explorer.focus is model
    assert len(explorer.history) == 1
    result = explorer.query(f"SELECT ?text WHERE {{ ?line <{TEXT}> ?text }} ORDER BY ?text")
    assert [row["text"] for row in result] == [
        "A final principle.", "Nested caching principle.", "Preserve mixed order.", "Project context.",
    ]
    assert explorer.query(f'ASK {{ ?line <{TEXT}> "Nested caching principle." }}') is True
    assert explorer.query(f'ASK {{ ?line <{TEXT}> "Historical discussion only." }}') is False
    assert explorer.node(sibling) not in explorer.opened
    assert explorer.node(root) in explorer.opened
    assert explorer.node(child.contents[0]) in explorer.opened
    explorer.follow(ContextEdge("out", CONTAINS, first))
    assert explorer.focus is first
    explorer.follow(ContextEdge("out", SCOPE, model))
    assert explorer.focus is model
    assert explorer.back().focus is first
    assert explorer.forward().focus is model


def test_empty_block_and_nonquery_mutations(tree):
    empty = Block(id=Ship(uuid4()))
    explorer = explore(empty)
    assert explorer.focus is empty and len(explorer.graph) == 1
    assert explorer.query(f"ASK {{ ?line <{TEXT}> ?text }}") is False
    with pytest.raises(ValueError, match="SELECT and ASK"):
        explorer.query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }")
    with pytest.raises(TypeError, match="Block"):
        explore(tree[2])
