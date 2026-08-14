from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tarav._core.errors import CliError


SCRIPT = Path(__file__).parents[2] / "dev/live/522-migrate-agentos-pkg-line-anchors.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("line_dossier_migration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ref(turn_id: str, *, producer: str = "user") -> dict[str, str]:
    suffix = ":assistant" if producer == "assistant" else ""
    return {
        "session": "a" * 64,
        "turn_id": f"{turn_id}{suffix}",
        "turn_hash": ("b" if producer == "assistant" else "c") * 64,
        "at": "2026-08-09T12:00:00.000Z",
    }


def _legacy_record(module, line: str) -> dict[str, object]:
    approval = _ref("turn-2")
    proposal = _ref("turn-1", producer="assistant")
    return {
        "app": "chatlas",
        "schema": "chatlas.support-set.v6",
        "hint": "legacy line relationship",
        "subject": {
            "kind": "index.line",
            "canonical_schema": module.OLD_CONTENT_SCHEMA,
            "content_hash": module._old_content_hash(line),
        },
        "predecessors": ["c20260809-0u"],
        "issue_context": ["Issue.I0001"],
        "members": [
            {
                **approval,
                "types": {
                    "tokenized.approval.turn": {
                        "token": "idx-edition:example",
                        "verbatim_turn": proposal,
                        "approval_turn": approval,
                    }
                },
            }
        ],
    }


def test_migration_projects_legacy_member_cargo_into_independent_relationships() -> None:
    module = _migration_module()
    line = "- [DC] stable line relationship"

    migrated = module.migrate_record(
        anchor="c20260809-1u",
        source=line,
        record=_legacy_record(module, line),
    )

    assert migrated["schema"] == "chatlas.line-anchor-dossier.v1"
    relationships = migrated["relationships"]
    assert "types" not in relationships["support"]["members"][0]
    assert relationships["gates"]["tokenized_verbatim_approval"][0]["token"] == (
        "idx-edition:example"
    )
    assert relationships["provenance"] == {
        "predecessor_anchors": ["c20260809-0u"],
        "issue_context": ["Issue.I0001"],
    }


def test_migration_refuses_unprojectable_legacy_fields() -> None:
    module = _migration_module()
    line = "- [DC] stable line relationship"
    record = _legacy_record(module, line)
    record["unmodeled"] = {"would": "be lost"}

    with pytest.raises(CliError, match="legacy record fields differ"):
        module.migrate_record(anchor="c20260809-1u", source=line, record=record)
