from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main
from tarav.chatlas.anchory import CHATLAS_NAMESPACE, chatlas_anchory_depot
from tarav.chatlas.normalization.session_model.events import (
    compute_event_group_hash,
    normal_turn_id,
)
from ._e2e_helpers import (
    _inline_selection_events,
    _selection_fixture,
)
from ._helpers import captured_json


def _fixture_identity_hash(
    capsys: pytest.CaptureFixture[str],
    session_id: str,
) -> str:
    assert (
        main(
            [
                "chatlas",
                "query",
                "--session-id",
                session_id,
                "--field",
                "identity_hash",
                "--json",
            ]
        )
        == 0
    )
    return capsys.readouterr().out.strip().splitlines()[-1]


def _fixture_event_sequence(
    capsys: pytest.CaptureFixture[str],
    session_id: str,
    text: str,
) -> int:
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--contains",
            text,
            "--view",
            "events",
        ],
    )
    assert len(events) == 1
    return int(events[0]["sequence"])


def _fixture_turn_ref(
    capsys: pytest.CaptureFixture[str],
    session_id: str,
    text: str,
) -> dict[str, str]:
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--contains",
            text,
            "--view",
            "events",
        ],
    )
    assert len(events) == 1
    event = events[0]
    turn_id = normal_turn_id(event)
    assert turn_id is not None
    return {
        "turn_id": turn_id,
        "turn_hash": compute_event_group_hash([event]),
        "at": str(event["timestamp"]),
    }


def _mint_fixture_anchor(
    identity_hash: str,
    turn_ref: dict[str, str],
    anchor: str = "c20260308-0u",
) -> str:
    from tarav.chatlas.anchory import chatlas_anchory_depot

    chatlas_anchory_depot().register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "fixture turn",
            "members": [{"session": identity_hash, **turn_ref}],
        },
        anchor=anchor,
    )
    return anchor


def test_chatlas_anchory_resolve_returns_member_neighborhood(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    event_sequence = _fixture_event_sequence(capsys, session_id, "beta question")
    turn_ref = _fixture_turn_ref(capsys, session_id, "beta question")
    anchor = _mint_fixture_anchor(identity_hash, turn_ref)

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "resolve",
                anchor,
                "--radius",
                "1",
                "--detail",
                "context",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert payload["record"]["schema"] == "chatlas.support-set.v3"
    events = payload["members"][0]["neighborhood"]["chat"]["events"]
    assert len(events) == 3
    assert events[1]["sequence"] == event_sequence


def test_chatlas_anchory_resolve_unresolvable_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _selection_fixture(tmp_path, monkeypatch, capsys)
    assert main(["chatlas", "session-anchory", "resolve", "c20990101-0u", "--json"]) == 1
    err = capsys.readouterr().err
    assert "c20990101-0u" in err


def test_chatlas_anchory_stats_pretty_and_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.chatlas.anchory import chatlas_anchory_depot

    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    beta = _fixture_turn_ref(capsys, session_id, "beta question")
    alpha = _fixture_turn_ref(capsys, session_id, "alpha question")
    depot = chatlas_anchory_depot()
    depot.register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "single support member",
            "members": [
                {
                    "session": identity_hash,
                    **beta,
                }
            ],
        },
        anchor="c20260308-0u",
        namespace=CHATLAS_NAMESPACE,
    )
    depot.register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "two support members",
            "members": [
                {
                    "session": identity_hash,
                    **beta,
                },
                {
                    "session": identity_hash,
                    **alpha,
                },
            ],
        },
        anchor="c20260308-1u",
        namespace=CHATLAS_NAMESPACE,
    )

    assert main(["chatlas", "session-anchory", "stats"]) == 0
    pretty = capsys.readouterr().out
    assert "Chatlas Anchory Support Sets" in pretty
    assert "Anchors: 2" in pretty
    assert "Support turns: 3" in pretty
    assert "1 member" in pretty
    assert "2 members" in pretty

    assert main(["chatlas", "session-anchory", "stats", "--json"]) == 0
    assert captured_json(capsys) == {
        "anchor_count": 2,
        "support_turn_count": 3,
        "min": 1,
        "max": 2,
        "mean": 1.5,
        "population_stddev": 0.5,
        "distribution": {"1": 1, "2": 1},
    }


def test_chatlas_anchory_sessions_extracts_unique_sessions_from_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    assert main(["chatlas", "query", "--session-id", session_id, "--json"]) == 0
    uri = captured_json(capsys)["rows"][0]["uri"]
    beta = {
        "turn_id": "turn-4",
        "turn_hash": "a" * 64,
        "at": "2026-03-08T01:09:04.000Z",
    }
    alpha = {
        "turn_id": "turn-2",
        "turn_hash": "b" * 64,
        "at": "2026-03-08T01:09:02.000Z",
    }
    depot = chatlas_anchory_depot()
    depot.register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "beta support",
            "members": [{"session": identity_hash, **beta}],
        },
        anchor="c20260308-0u",
        namespace=CHATLAS_NAMESPACE,
    )
    depot.register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "alpha support",
            "members": [{"session": identity_hash, **alpha}],
        },
        anchor="c20260308-1u",
        namespace=CHATLAS_NAMESPACE,
    )

    surfaces = tmp_path / "surfaces"
    nested = surfaces / "nested"
    nested.mkdir(parents=True)
    first = surfaces / "100-design.md"
    first.write_text(
        "one ^c20260308-0u\nmissing ^c20990101-0u\n",
        encoding="utf-8",
    )
    second = nested / "Concept-appendix.md"
    second.write_text(
        "duplicate ^c20260308-0u\nanother ^c20260308-1u\nwrong tag ^c20260308-1x\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "sessions",
                "--source",
                str(first),
                "--source",
                str(surfaces),
                "--regex",
                r"\^(?P<anchor>c\d{8}-\d+[a-z]?)",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)

    assert payload["status"] == "needs-review"
    assert payload["command"] == "chatlas anchory sessions"
    assert payload["file_count"] == 2
    assert payload["anchor_count"] == 4
    assert payload["resolved_anchor_count"] == 3
    assert payload["session_count"] == 1
    assert payload["sessions"] == [
        {
            "identity_hash": identity_hash,
            "indexed": True,
            "provider": "codex",
            "session_id": session_id,
            "uri": uri,
            "last_activity_at": "2026-03-08T01:09:05.000Z",
            "anchors": ["c20260308-0u", "c20260308-1u", "c20260308-1x"],
            "support_member_count": 3,
            "chat_index": {
                "materialized": False,
                "state": "missing",
                "path": str(
                    Path(payload["chatlas_root"]) / "session-index" / identity_hash
                ),
            },
        }
    ]
    anchors = {item["anchor"]: item for item in payload["anchors"]}
    assert anchors["c20260308-0u"]["occurrences"] == [
        {"path": str(first.resolve()), "line": 1, "column": 6},
        {"path": str(second.resolve()), "line": 1, "column": 12},
    ]
    assert anchors["c20260308-1x"]["resolved_anchor"] == "c20260308-1u"
    assert anchors["c20260308-1x"]["tag_mismatch"] is True
    assert [finding["kind"] for finding in payload["findings"]] == [
        "tag_mismatch",
        "unresolved_anchor",
    ]


def test_chatlas_anchory_preview_is_compact_and_non_mutating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_ref = _fixture_turn_ref(capsys, session_id, "beta question")
    turn_id = turn_ref["turn_id"]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "preview",
                "--member",
                f"{identity_hash[:12]}:{turn_id}",
                "--hint",
                "beta question turn",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert "anchor" not in payload
    record = payload["record"]
    assert record["app"] == "chatlas"
    assert record["schema"] == "chatlas.support-set.v3"
    assert record["members"] == [
        {
            "session": identity_hash,
            **turn_ref,
        }
    ]
    assert record["hint"] == "beta question turn"
    member = payload["members"][0]
    assert member["member_ref"] == f"{identity_hash}:{turn_id}"
    assert member["text"] == "beta question"
    assert "normal_turn" not in member
    assert "neighborhood" not in member
    assert chatlas_anchory_depot().query(namespace=CHATLAS_NAMESPACE) == ()


def test_chatlas_anchory_register_defaults_to_compact_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_id = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                f"{identity_hash}:{turn_id}",
                "--hint",
                "beta question turn",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert payload["anchor"] == "c20260308-0u"
    assert payload["members"][0]["text"] == "beta question"
    assert "neighborhood" not in payload["members"][0]


def test_chatlas_anchory_register_binds_index_line_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.index_model import index_line_anchor_triplet_hash

    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_id = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    line_content = "- [DC] beta decision"

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                f"{identity_hash}:{turn_id}",
                "--hint",
                "beta question turn",
                "--line-content",
                line_content,
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    record = payload["record"]
    assert record["schema"] == "chatlas.line-anchor-dossier.v1"
    assert record["relationships"]["provenance"]["issue_context"] == []
    assert record["attachment"]["triplet_hash"] == index_line_anchor_triplet_hash(
        line_content,
        payload["anchor"],
    )


def test_chatlas_anchory_reattach_preserves_anchor_and_relationships(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tarav.index_model import index_line_anchor_triplet_hash

    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_id = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    untyped = "- beta decision"
    typed = "- [DC] beta decision"
    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                f"{identity_hash}:{turn_id}",
                "--line-content",
                untyped,
                "--json",
            ]
        )
        == 0
    )
    registered = captured_json(capsys)
    anchor = registered["anchor"]
    relationships = registered["record"]["relationships"]
    index_depot = tmp_path / "index-depot"
    design = index_depot / "design"
    design.mkdir(parents=True)
    (design / "100-design.md").write_text(
        f"****\n## Example.Concept\n\n{typed} ^{anchor}\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "reattach",
                "--depot",
                str(index_depot),
                "--anchor",
                anchor,
                "--json",
            ]
        )
        == 0
    )
    amended = captured_json(capsys)
    assert amended["anchor"] == anchor
    assert amended["changed"] is True
    assert amended["depot"] == str(index_depot.resolve())
    assert amended["sources"] == [{"path": "design/100-design.md", "line": 4}]
    assert amended["relationships"] == relationships
    assert amended["attachment"]["triplet_hash"] == index_line_anchor_triplet_hash(
        typed,
        anchor,
    )

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "reattach",
                "--depot",
                str(index_depot),
                "--anchor",
                anchor,
                "--json",
            ]
        )
        == 0
    )
    assert captured_json(capsys)["changed"] is False


def test_chatlas_anchory_reattach_rejects_parser_observed_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    anchor = "c20260810-1u"
    design = tmp_path / "index-depot" / "design"
    design.mkdir(parents=True)
    (design / "100-design.md").write_text(
        f"****\n## Example.One\n\n- [CT] first body ^{anchor}\n",
        encoding="utf-8",
    )
    (design / "101-design.md").write_text(
        f"****\n## Example.Two\n\n- [CT] second body ^{anchor}\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "reattach",
                "--depot",
                str(tmp_path / "index-depot"),
                "--anchor",
                anchor,
                "--json",
            ]
        )
        == 1
    )
    error = capsys.readouterr().err
    assert "2 distinct Index line triplets" in error
    assert "design/100-design.md:4" in error
    assert "design/101-design.md:4" in error


def test_chatlas_anchory_preview_context_escalates_to_neighborhood(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_id = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "preview",
                "--member",
                f"{identity_hash}:{turn_id}",
                "--hint",
                "beta question turn",
                "--detail",
                "context",
                "--radius",
                "1",
                "--json",
            ]
        )
        == 0
    )
    member = captured_json(capsys)["members"][0]
    events = member["neighborhood"]["chat"]["events"]
    assert any(normal_turn_id(event) == turn_id for event in events)


def test_chatlas_anchory_preview_reports_equivalent_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_ref = _fixture_turn_ref(capsys, session_id, "beta question")
    member_ref = f"{identity_hash}:{turn_ref['turn_id']}"
    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                member_ref,
                "--hint",
                "original member meaning",
                "--json",
            ]
        )
        == 0
    )
    anchor = captured_json(capsys)["anchor"]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "preview",
                "--member",
                member_ref,
                "--hint",
                "same member meaning",
                "--json",
            ]
        )
        == 0
    )
    assert captured_json(capsys)["equivalent_anchors"] == [anchor]


def test_chatlas_anchory_register_preserves_member_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    beta = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    alpha = _fixture_turn_ref(capsys, session_id, "alpha question")["turn_id"]
    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                f"{identity_hash}:{beta}",
                "--member",
                f"{identity_hash}:{alpha}",
                "--hint",
                "relevance ordered",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert [member["turn_id"] for member in payload["record"]["members"]] == [
        beta,
        alpha,
    ]


def test_chatlas_anchory_register_rejects_non_user_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    # a turn holding no human user message cannot be a support member; the
    # session-scope group is the standing example
    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                f"{identity_hash}:session",
                "--hint",
                "assistant is not authority",
                "--json",
            ]
        )
        == 1
    )
    assert "turn is unavailable" in capsys.readouterr().err


LINE_A = "- [CT] The batch service grounds many lines in one pass."
LINE_B = "- [DC] Exact line equivalence never accepts a generic support anchor."


def test_generic_support_equivalence_is_not_exact_line_equivalence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    turn_ref = _fixture_turn_ref(capsys, session_id, "beta question")
    member_ref = f"{identity_hash}:{turn_ref['turn_id']}"

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                member_ref,
                "--hint",
                "generic support without a line subject",
                "--json",
            ]
        )
        == 0
    )
    generic_anchor = captured_json(capsys)["anchor"]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "preview",
                "--member",
                member_ref,
                "--hint",
                "same members, now bound to a line",
                "--line-content",
                LINE_A,
                "--json",
            ]
        )
        == 0
    )
    preview = captured_json(capsys)
    assert preview["support_equivalent_anchors"] == [generic_anchor]
    assert preview["exact_line_equivalent_anchors"] == []
    assert preview["equivalent_anchors"] == [generic_anchor]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "register",
                "--member",
                member_ref,
                "--hint",
                "line-bound support",
                "--line-content",
                LINE_A,
                "--json",
            ]
        )
        == 0
    )
    line_anchor = captured_json(capsys)["anchor"]

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "preview",
                "--member",
                member_ref,
                "--hint",
                "same line again",
                "--line-content",
                LINE_A,
                "--json",
            ]
        )
        == 0
    )
    same_line = captured_json(capsys)
    assert same_line["exact_line_equivalent_anchors"] == [line_anchor]
    assert sorted(same_line["support_equivalent_anchors"]) == sorted(
        [generic_anchor, line_anchor]
    )

    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "preview",
                "--member",
                member_ref,
                "--hint",
                "another line, same members",
                "--line-content",
                LINE_B,
                "--json",
            ]
        )
        == 0
    )
    other_line = captured_json(capsys)
    assert other_line["exact_line_equivalent_anchors"] == []
    assert sorted(other_line["support_equivalent_anchors"]) == sorted(
        [generic_anchor, line_anchor]
    )


def _batch_input(path: Path, identity_hash: str, alpha: str, beta: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "chatlas.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "line-a",
                        "line_content": LINE_A,
                        "members": [f"{identity_hash}:{beta}"],
                    },
                    {
                        "client_id": "line-b",
                        "line_content": LINE_B,
                        "members": [
                            f"{identity_hash}:{beta}",
                            f"{identity_hash}:{alpha}",
                        ],
                    },
                    {
                        "client_id": "line-a-again",
                        "line_content": LINE_A,
                        "members": [f"{identity_hash}:{beta}"],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_anchory_batch_previews_then_registers_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    alpha = _fixture_turn_ref(capsys, session_id, "alpha question")["turn_id"]
    beta = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    batch = _batch_input(tmp_path / "batch.json", identity_hash, alpha, beta)

    assert (
        main(
            ["chatlas", "session-anchory", "batch", "preview", "--input", str(batch), "--json"]
        )
        == 0
    )
    preview = captured_json(capsys)
    assert [item["client_id"] for item in preview["items"]] == [
        "line-a",
        "line-b",
        "line-a-again",
    ]
    assert [item["action"] for item in preview["items"]] == ["mint", "mint", "reuse"]
    assert all(item["anchor"] is None for item in preview["items"])
    assert preview["items"][2]["duplicate_of"] == "line-a"
    assert preview["mint_count"] == 2
    assert preview["reuse_count"] == 1
    assert list(chatlas_anchory_depot().query(namespace=CHATLAS_NAMESPACE)) == []

    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(batch), "--json"]
        )
        == 0
    )
    registered = captured_json(capsys)
    anchors = {item["client_id"]: item["anchor"] for item in registered["items"]}
    assert anchors["line-a"] == anchors["line-a-again"]
    assert anchors["line-a"] != anchors["line-b"]
    assert registered["minted_count"] == 2
    assert registered["reused_count"] == 1
    assert [item["action"] for item in registered["items"]] == [
        "minted",
        "minted",
        "reused",
    ]
    assert len(chatlas_anchory_depot().query(namespace=CHATLAS_NAMESPACE)) == 2

    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(batch), "--json"]
        )
        == 0
    )
    again = captured_json(capsys)
    assert again["minted_count"] == 0
    assert again["reused_count"] == 3
    assert {item["client_id"]: item["anchor"] for item in again["items"]} == anchors
    assert len(chatlas_anchory_depot().query(namespace=CHATLAS_NAMESPACE)) == 2


def test_anchory_batch_refuses_before_writing_when_one_item_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    beta = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    batch = tmp_path / "invalid.json"
    batch.write_text(
        json.dumps(
            {
                "schema": "chatlas.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "valid",
                        "line_content": LINE_A,
                        "members": [f"{identity_hash}:{beta}"],
                    },
                    {
                        "client_id": "unresolvable",
                        "line_content": LINE_B,
                        "members": [f"{identity_hash}:turn-does-not-exist"],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(batch), "--json"]
        )
        == 1
    )
    assert list(chatlas_anchory_depot().query(namespace=CHATLAS_NAMESPACE)) == []


def test_anchory_batch_rejects_duplicate_client_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    beta = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    batch = tmp_path / "duplicate.json"
    batch.write_text(
        json.dumps(
            {
                "schema": "chatlas.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "same",
                        "line_content": LINE_A,
                        "members": [f"{identity_hash}:{beta}"],
                    },
                    {
                        "client_id": "same",
                        "line_content": LINE_B,
                        "members": [f"{identity_hash}:{beta}"],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            ["chatlas", "session-anchory", "batch", "preview", "--input", str(batch), "--json"]
        )
        == 1
    )


def test_anchory_batch_carries_independent_gates_predecessors_and_support_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    alpha_ref = _fixture_turn_ref(capsys, session_id, "alpha question")
    beta_ref = _fixture_turn_ref(capsys, session_id, "beta question")
    alpha = alpha_ref["turn_id"]
    beta = beta_ref["turn_id"]
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps(
            {
                "schema": "chatlas.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "predecessor",
                        "line_content": LINE_A,
                        "members": [f"{identity_hash}:{alpha}"],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(seed), "--json"]
        )
        == 0
    )
    predecessor = captured_json(capsys)["items"][0]["anchor"]

    batch = tmp_path / "typed.json"
    batch.write_text(
        json.dumps(
            {
                "schema": "chatlas.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "typed",
                        "line_content": LINE_B,
                        "members": [
                            f"{identity_hash}:{beta}",
                            f"{identity_hash}:{alpha}",
                        ],
                        "gates": {
                            "semantic_approval": [
                                {
                                    "approval_turn": {
                                        "session": identity_hash,
                                        **beta_ref,
                                    }
                                }
                            ],
                            "tokenized_verbatim_approval": [],
                        },
                        "predecessors": [predecessor],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(batch), "--json"]
        )
        == 0
    )
    item = captured_json(capsys)["items"][0]
    record = item["record"]
    assert record["schema"] == "chatlas.line-anchor-dossier.v1"
    relationships = record["relationships"]
    assert [member["turn_id"] for member in relationships["support"]["members"]] == [
        beta,
        alpha,
    ]
    assert (
        relationships["gates"]["semantic_approval"][0]["approval_turn"]["turn_id"]
        == beta
    )
    assert relationships["provenance"]["predecessor_anchors"] == [predecessor]

    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(batch), "--json"]
        )
        == 0
    )
    again = captured_json(capsys)
    assert again["minted_count"] == 0
    assert again["items"][0]["anchor"] == item["anchor"]


def test_anchory_batch_retry_reuses_anchors_minted_by_an_earlier_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    identity_hash = _fixture_identity_hash(capsys, session_id)
    alpha = _fixture_turn_ref(capsys, session_id, "alpha question")["turn_id"]
    beta = _fixture_turn_ref(capsys, session_id, "beta question")["turn_id"]
    partial = tmp_path / "partial.json"
    partial.write_text(
        json.dumps(
            {
                "schema": "chatlas.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "line-a",
                        "line_content": LINE_A,
                        "members": [f"{identity_hash}:{beta}"],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "chatlas",
                "session-anchory",
                "batch",
                "register",
                "--input",
                str(partial),
                "--json",
            ]
        )
        == 0
    )
    already = captured_json(capsys)["items"][0]["anchor"]

    full = _batch_input(tmp_path / "full.json", identity_hash, alpha, beta)
    assert (
        main(
            ["chatlas", "session-anchory", "batch", "register", "--input", str(full), "--json"]
        )
        == 0
    )
    retried = captured_json(capsys)
    assert retried["minted_count"] == 1
    assert retried["reused_count"] == 2
    anchors = {item["client_id"]: item["anchor"] for item in retried["items"]}
    assert anchors["line-a"] == already
    assert anchors["line-a-again"] == already
    assert len(list(chatlas_anchory_depot().query(namespace=CHATLAS_NAMESPACE))) == 2
