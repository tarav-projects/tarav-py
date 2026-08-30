"""record depot hosts an anchory dossier and an index record without naming either schema.

These are the two stores 641 proposes to converge. The test is deliberately built from
real shapes rather than fixtures invented for it: if record depot needed to know anything
about them, this is where that would show.
"""

from __future__ import annotations

from pathlib import Path

from tarav._core.record_depot import OpaqueRecordDepot

# A migrated Chatlas2 line-anchor dossier, verbatim from ~/Documents/chatlas/anchory.
DOSSIER = {
    "app": "chatlas2",
    "schema": "tarav.chatlas2.line-anchor-dossier.v2",
    "attachment": {
        "canonical_schema": "agentos.index-line-anchor-triplet.v1",
        "triplet_hash": "sha256:d2a96bafc4c6ac1590df5f078409ac649f2a0f24d3d5666b34d3e0a647ff39a3",
    },
    "relationships": {
        "support": {
            "members": [
                {
                    "session": "c3aef3136640fd82eb45abbfec838db1308879b36f6647d9208d584b262a5ce1",
                    "message_address": "c8f299857829507159c74a26fd3ca83355395dbdde92473e11e40e8b60ea602a",
                    "message_hash": "7866962074e808c38176002eb7bcbc4c865fc2b342b3320282881f93b436f5c0",
                    "at": "2026-07-12T00:47:44.993Z",
                }
            ]
        },
        "gates": {"semantic_approval": [], "tokenized_verbatim_approval": []},
        "provenance": {"predecessor_anchors": ["c20260712-6u"], "issue_context": []},
    },
}

# An index line record, verbatim from tarav-md/.tarav/index/.
INDEX_RECORD = {
    "schema": "tarav.index-line-record.v3",
    "id": "ln_02b223fe16ebaaa9",
    "trace": "tr_e88630a73c79a72d",
    "scope": "tarav-pkg/design#State.Estimation",
    "line": {
        "type": "DF",
        "body": "a state is minimally a value plus an err or unknown estimate",
        "label": "^c20260819-16u",
    },
    "links": {
        "grounding": [
            {"archive": "chat", "session_id": "9f41aa0e", "message_id": "9d2509ed"}
        ],
        "review": None,
        "landing": None,
    },
    "equivalence": None,
}


def _depot(tmp_path: Path) -> OpaqueRecordDepot:
    depot = OpaqueRecordDepot(tmp_path / "depot")
    depot.insert(DOSSIER)
    depot.insert(INDEX_RECORD)
    return depot


def test_both_shapes_round_trip_verbatim(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    stored = depot.all({})
    assert DOSSIER in stored
    assert INDEX_RECORD in stored


def test_one_depot_holds_both_without_them_colliding(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    assert depot.count({}) == 2
    assert depot.count({"schema": {"contains": "line-anchor-dossier"}}) == 1
    assert depot.count({"schema": {"contains": "index-line-record"}}) == 1


def test_the_index_finds_a_record_by_label(tmp_path: Path) -> None:
    """`by_label` is the index's hot lookup; it becomes an ordinary path query."""
    depot = _depot(tmp_path)
    found = depot.first({"line.label": {"equals": "^c20260819-16u"}})
    assert found == INDEX_RECORD


def test_the_index_finds_a_trace_by_scan(tmp_path: Path) -> None:
    """`by_trace` returns many, so it is `all` — the arity is at the call, not declared."""
    depot = _depot(tmp_path)
    assert depot.all({"trace": {"equals": "tr_e88630a73c79a72d"}}) == (INDEX_RECORD,)


def test_ungated_is_distinguishable_from_unknown(tmp_path: Path) -> None:
    """`links.landing: null` means ungated. `exists` must not collapse it into absent."""
    depot = _depot(tmp_path)
    assert depot.count({"links.landing": {"exists": True}}) == 1
    assert depot.count({"links.landing": {"equals": None}}) == 1


def test_anchory_finds_a_dossier_through_a_nested_support_member(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    session = DOSSIER["relationships"]["support"]["members"][0]["session"]
    found = depot.first({"relationships.support.members.0.session": {"equals": session}})
    assert found == DOSSIER


def test_no_executable_line_names_a_consumer_schema(tmp_path: Path) -> None:
    """The claim the whole design rests on, asserted mechanically rather than trusted.

    Comments and docstrings are excluded on purpose: citing a motivating example explains
    *why* and couples nothing. What would couple is a branch, a constant, or a field name
    in executable code — so that is what this reads.
    """
    import ast
    import tarav._core.record_depot as core

    tree = ast.parse(Path(core.__file__).read_text("utf-8"))
    for node in ast.walk(tree):  # drop every docstring, keeping real code
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:] or [ast.Pass()]
    executable = ast.unparse(ast.fix_missing_locations(tree)).lower()

    for token in ("dossier", "anchor", "grounding", "trace", "triplet", "session", "label"):
        assert token not in executable, (
            f"record depot executes on {token!r}; the cargo is supposed to be opaque"
        )
