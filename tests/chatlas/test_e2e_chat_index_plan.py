from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agentos.cli.cli import main
from agentos.chatlas.chat_index import chatlas_chat_index_source

from ._e2e_helpers import (
    _configure_chatlas,
    _index_rows,
    _isolate_chatlas,
    _write_codex_rollout,
)
from ._helpers import captured_json


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fe4"


def _medium_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    exchanges: int = 24,
) -> tuple[Path, dict[str, object]]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{SESSION_ID}.jsonl"
    )
    _write_codex_rollout(
        rollout,
        session_id=SESSION_ID,
        messages=_messages(exchanges),
    )
    _configure_chatlas(environment, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    chatlas_root = environment.home / "Documents" / "chatlas"
    return chatlas_root, _index_rows(chatlas_root)[0]


def _messages(exchanges: int) -> list[tuple[str, str]]:
    return [
        item
        for exchange in range(exchanges)
        for item in (
            ("user", f"user touched change {exchange:02d}"),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]


def _grow(tmp_path: Path, capsys: pytest.CaptureFixture[str], exchanges: int) -> None:
    rollout = (
        tmp_path
        / "codex-home"
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{SESSION_ID}.jsonl"
    )
    _write_codex_rollout(
        rollout, session_id=SESSION_ID, messages=_messages(exchanges)
    )
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()


def _user_turns(chatlas_root: Path, row: dict[str, object]) -> list[dict[str, object]]:
    source = chatlas_chat_index_source(
        identity_hash=str(row["identity_hash"]),
        chatlas_root=chatlas_root,
    )["source"]
    return [
        entry
        for entry in source["turn_refs"]
        if entry["role"] == "user" and entry["producer_type"] == "human"
    ]


def _scaffold(
    capsys: pytest.CaptureFixture[str], stage: Path, *extra: str
) -> dict[str, object]:
    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "scaffold",
                "--session-id",
                SESSION_ID,
                "--stage",
                str(stage),
                *extra,
                "--json",
            ]
        )
        == 0
    )
    return captured_json(capsys)


def _validate(capsys: pytest.CaptureFixture[str], plan: Path) -> dict[str, object]:
    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan), "--json"]) == 0
    )
    return captured_json(capsys)


def _author(
    plan_path: Path,
    *,
    identity_hash: str,
    horizons: list[str],
    head_only_turn: str | None = None,
) -> dict[str, object]:
    """Fill only the semantic region an agent owns."""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["delta_edits"] = [
        {
            "horizon_turn_id": horizon,
            "blocks": [
                {
                    "concept": "Capture.Plan",
                    "lines": [
                        {
                            "content": f"- [CT] Authored change {index} for {horizon}.",
                            "support": {
                                "members": [f"{identity_hash}:{horizon}"],
                            },
                        }
                    ],
                }
            ],
        }
        for index, horizon in enumerate(horizons)
    ]
    head_lines = [
        {"content": f"- [CT] Authored change {index} for {horizon}."}
        for index, horizon in enumerate(horizons)
    ]
    if head_only_turn is not None:
        head_lines.append(
            {
                "content": "- [CT] This maintenance state has no Delta home yet.",
                "support": {
                    "members": [f"{identity_hash}:{head_only_turn}"],
                },
            }
        )
    plan["head"] = {"blocks": [{"concept": "Capture.Plan", "lines": head_lines}]}
    plan["status"] = "ready"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def _tree_fingerprint(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_scaffold_writes_cpu_envelope_and_chat_only_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    stage = tmp_path / "stage"

    payload = _scaffold(capsys, stage)

    assert payload["mode"] == "create"
    assert payload["base_surface"] is None
    plan = json.loads(Path(str(payload["plan_path"])).read_text(encoding="utf-8"))
    envelope = plan["chatlas"]
    assert plan["schema"] == "agentos.chat-index.capture-plan.v1"
    assert plan["delta_edits"] == []
    assert plan["head"] == {"preserve": False, "blocks": []}
    assert envelope["session"]["identity_hash"] == row["identity_hash"]
    assert envelope["source"]["turn_count"] == 48
    assert envelope["base_surface"] is None

    evidence = json.loads(
        Path(str(payload["evidence_path"])).read_text(encoding="utf-8")
    )
    assert evidence["scope"] == "complete-prefix"
    assert evidence["turn_count"] == 48
    first = evidence["turns"][0]
    assert first["messages"][0]["role"] == "user"
    assert first["messages"][0]["text"] == "user touched change 00"
    # Chat evidence only: no Normal.Turn grouping, no reasoning or tool payloads.
    assert "normal_turn" not in first
    assert set(first["messages"][0]) == {"sequence", "role", "text"}


def test_scaffold_refuses_a_non_empty_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _chatlas_root, _row = _medium_session(tmp_path, monkeypatch, capsys)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "leftover.json").write_text("{}\n", encoding="utf-8")

    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "scaffold",
                "--session-id",
                SESSION_ID,
                "--stage",
                str(stage),
                "--json",
            ]
        )
        == 1
    )


def test_validate_reports_a_complete_render_plan_without_touching_anything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    payload = _scaffold(capsys, stage)
    plan_path = Path(str(payload["plan_path"]))
    horizons = [str(user_turns[index]["turn_ref"]["turn_id"]) for index in (3, 7)]
    _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=horizons,
        head_only_turn=str(user_turns[-1]["turn_ref"]["turn_id"]),
    )

    anchory_before = _tree_fingerprint(chatlas_root / "anchory")
    surface_before = _tree_fingerprint(chatlas_root / "session-index")

    result = _validate(capsys, plan_path)

    assert result["ok"] is True
    assert result["mode"] == "create"
    assert result["tail"]["state"] == "current"
    assert result["anchor_plan"]["item_count"] == 3
    assert result["anchor_plan"]["mint_count"] == 3
    assert result["anchor_plan"]["reuse_count"] == 0
    assert all(item["anchor"] is None for item in result["anchor_plan"]["items"])
    inventory = {item["relative_path"]: item for item in result["files"]}
    assert set(inventory) == {
        "HEAD.md",
        f"deltas/{horizons[0]}.md",
        f"deltas/{horizons[1]}.md",
    }
    assert inventory["HEAD.md"]["line_count"] == 3
    assert inventory[f"deltas/{horizons[0]}.md"]["action"] == "render"
    assert result["removed_paths"] == []

    # No anchors minted, no surface created.
    assert _tree_fingerprint(chatlas_root / "anchory") == anchory_before
    assert _tree_fingerprint(chatlas_root / "session-index") == surface_before


def test_validate_is_idempotent_and_byte_for_byte_non_mutating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    stage_before = _tree_fingerprint(stage)
    root_before = _tree_fingerprint(chatlas_root)

    first = _validate(capsys, plan_path)
    second = _validate(capsys, plan_path)

    assert first == second
    assert _tree_fingerprint(stage) == stage_before
    assert _tree_fingerprint(chatlas_root) == root_before


def test_validate_accepts_append_only_growth_after_scaffold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    _grow(tmp_path, capsys, exchanges=26)

    result = _validate(capsys, plan_path)

    assert result["ok"] is True
    assert result["tail"]["state"] == "append-only"
    assert result["tail"]["pending_turn_count"] == 4
    # The plan still installs exactly the prefix it inspected.
    assert result["anchor_plan"]["item_count"] == 1


def test_validate_refuses_a_line_that_carries_its_own_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    plan = _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    line = plan["delta_edits"][0]["blocks"][0]["lines"][0]
    canonical = str(line["content"])
    line["content"] = f"{canonical} ^c20260804-1u"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 1
    )
    # Mechanical damage is rejected with the content the author should have written.
    assert repr(canonical) in capsys.readouterr().err


def test_validate_shows_the_canonical_content_for_a_padded_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    plan = _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    line = plan["delta_edits"][0]["blocks"][0]["lines"][0]
    canonical = str(line["content"])
    line["content"] = f"  {canonical}  "
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 1
    )
    assert repr(canonical) in capsys.readouterr().err


def test_validate_refuses_support_reaching_past_a_delta_horizon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    plan = _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    later = str(user_turns[-1]["turn_ref"]["turn_id"])
    plan["delta_edits"][0]["blocks"][0]["lines"][0]["support"]["members"] = [
        f"{identity_hash}:{later}"
    ]
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 1
    )


def test_validate_refuses_a_head_only_line_without_its_own_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    plan = _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    plan["head"]["blocks"][0]["lines"].append(
        {"content": "- [CT] Ungrounded HEAD-first claim."}
    )
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 1
    )


def test_validate_refuses_a_delta_horizon_that_is_not_a_user_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    source = chatlas_chat_index_source(
        identity_hash=identity_hash, chatlas_root=chatlas_root
    )["source"]
    assistant = next(
        entry for entry in source["turn_refs"] if entry["role"] != "user"
    )
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    plan = _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )
    plan["delta_edits"][0]["horizon_turn_id"] = str(assistant["turn_ref"]["turn_id"])
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 1
    )


def test_validate_fails_closed_when_the_inspected_prefix_was_revised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    stage = tmp_path / "stage"
    plan_path = Path(str(_scaffold(capsys, stage)["plan_path"]))
    _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=[str(user_turns[3]["turn_ref"]["turn_id"])],
    )

    rollout = (
        tmp_path
        / "codex-home"
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{SESSION_ID}.jsonl"
    )
    revised = [
        item
        for exchange in range(24)
        for item in (
            (
                "user",
                "changed historical touch"
                if exchange == 7
                else f"user touched change {exchange:02d}",
            ),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=revised)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    # A rewritten turn inside the inspected prefix is never silently accepted.
    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 1
    )
    assert (
        main(["chatlas", "chat-index", "apply", "--plan", str(plan_path), "--json"])
        == 1
    )
    assert not (chatlas_root / "session-index" / identity_hash).exists()
