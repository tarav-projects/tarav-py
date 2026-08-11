from __future__ import annotations

import pytest

from agentos._core.errors import CliError
from agentos.index.model import index_line_anchor_triplet_hash
from agentos.chatlas.anchory import (
    CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
    bind_support_set_to_index_line,
    parse_line_anchor_dossier,
    parse_line_attachment,
    parse_line_gate_relationships,
    parse_line_issue_context,
    parse_line_predecessors,
    parse_support_set_record,
)


TURN = {
    "session": "a" * 64,
    "turn_id": "turn-r2",
    "turn_hash": "b" * 64,
    "at": "2026-08-05T02:00:00Z",
}


def _support_record() -> dict[str, object]:
    return {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "fixture support",
        "members": [TURN],
    }


def test_line_dossier_owns_attachment_and_independent_relationship_namespaces() -> None:
    line = "- [DC] use the line-centered dossier"
    anchor = "c20260809-1u"
    gates = {
        "semantic_approval": [],
        "tokenized_verbatim_approval": [
            {"token": "idx-edition:test", "proposal_turn": TURN, "approval_turn": TURN}
        ],
    }

    record = bind_support_set_to_index_line(
        _support_record(),
        line_content=line,
        anchor=anchor,
        gates=gates,
        predecessors=("c20260808-1u",),
        issue_context=("Issue.I0001",),
    )

    assert record["schema"] == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
    assert parse_line_attachment(record)["triplet_hash"] == index_line_anchor_triplet_hash(
        line, anchor
    )
    assert parse_support_set_record(record) == [TURN]
    assert parse_line_gate_relationships(record) == gates
    assert parse_line_predecessors(record) == ("c20260808-1u",)
    assert parse_line_issue_context(record) == ("Issue.I0001",)
    assert "hint" not in record
    assert "types" not in record["relationships"]["support"]["members"][0]


def test_retired_line_bound_schemas_are_not_runtime_readable() -> None:
    retired = {
        **_support_record(),
        "schema": "chatlas.support-set.v6",
        "subject": {},
        "issue_context": [],
    }

    with pytest.raises(CliError, match="unsupported schema"):
        parse_support_set_record(retired)
    with pytest.raises(CliError, match="requires schema"):
        parse_line_anchor_dossier(retired)
