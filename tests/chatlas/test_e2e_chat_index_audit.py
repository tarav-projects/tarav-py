from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

import pytest

from tarav.cli.cli import main
from tarav.chatlas.anchory import chatlas_anchory_register
from tarav.chatlas.chat_index import chatlas_chat_index_source

from ._e2e_helpers import (
    _configure_chatlas,
    _index_rows,
    _isolate_chatlas,
    _write_codex_rollout,
)
from ._helpers import captured_json


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fe3"
SHARED_LINE = "- [DC] `Chat.Index.HEAD` presents the current chat model."
HEAD_ONLY_LINE = "- [CT] HEAD-only maintenance state still owns its own support."


def _medium_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[Path, dict[str, object]]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{SESSION_ID}.jsonl"
    )
    messages = [
        item
        for exchange in range(24)
        for item in (
            ("user", f"user touched change {exchange:02d}"),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=messages)
    _configure_chatlas(environment, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    chatlas_root = environment.home / "Documents" / "chatlas"
    return chatlas_root, _index_rows(chatlas_root)[0]


def _user_turns(source: dict[str, object]) -> list[dict[str, object]]:
    return [
        entry
        for entry in source["turn_refs"]
        if entry["role"] == "user" and entry["producer_type"] == "human"
    ]


def _anchor(
    chatlas_root: Path,
    identity_hash: str,
    turn_id: str,
    line_content: str,
) -> str:
    payload = chatlas_anchory_register(
        members=(f"{identity_hash}:{turn_id}",),
        hint="audit fixture grounding",
        line_content=line_content,
        chatlas_root=chatlas_root,
    )
    return str(payload["anchor"])


def _grounded_surface(
    chatlas_root: Path,
    row: dict[str, object],
) -> tuple[Path, dict[str, object]]:
    """A complete, fully grounded v2 surface that must audit clean."""
    identity_hash = str(row["identity_hash"])
    surface = chatlas_root / "session-index" / identity_hash
    (surface / "deltas").mkdir(parents=True)
    source = chatlas_chat_index_source(
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )["source"]
    user_turns = _user_turns(source)
    selected = [user_turns[index] for index in (3, 7, 11)]

    shared_anchor = _anchor(
        chatlas_root,
        identity_hash,
        str(selected[1]["turn_ref"]["turn_id"]),
        SHARED_LINE,
    )
    head_only_anchor = _anchor(
        chatlas_root,
        identity_hash,
        str(user_turns[-1]["turn_ref"]["turn_id"]),
        HEAD_ONLY_LINE,
    )

    deltas: list[dict[str, object]] = []
    for delta_index, entry in enumerate(selected):
        turn_ref = entry["turn_ref"]
        turn_id = str(turn_ref["turn_id"])
        own_line = f"- [CT] Captured medium-chat change {delta_index}."
        own_anchor = _anchor(chatlas_root, identity_hash, turn_id, own_line)
        lines = [
            f"# Chat.Index.Delta/{turn_id} @ {turn_ref['at']}",
            "",
            f"{own_line} ^{own_anchor}",
        ]
        if delta_index in {1, 2}:
            lines.append(f"{SHARED_LINE} ^{shared_anchor}")
        (surface / f"deltas/{turn_id}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        deltas.append(
            {
                "path": f"deltas/{turn_id}.md",
                "horizon": turn_ref,
                "tape_position": entry["tape_position"],
            }
        )

    head_horizon = source["turn_refs"][-1]["turn_ref"]
    (surface / "HEAD.md").write_text(
        "# Chat.Index.HEAD\n"
        "\n"
        f"Evidence.Horizon: `{head_horizon['turn_id']}` @ {head_horizon['at']}\n"
        "\n"
        f"{SHARED_LINE} ^{shared_anchor}\n"
        f"{HEAD_ONLY_LINE} ^{head_only_anchor}\n",
        encoding="utf-8",
    )
    return surface, {
        "deltas": deltas,
        "shared_anchor": shared_anchor,
        "head_only_anchor": head_only_anchor,
        "user_turns": user_turns,
        "selected": selected,
    }


def _fingerprint(surface: Path) -> dict[str, str]:
    return {
        str(path.relative_to(surface)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(surface.rglob("*"))
        if path.is_file()
    }


def _audit(
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    expect: int,
) -> dict[str, object]:
    code = main(
        [
            "chatlas",
            "chat-index",
            "audit",
            "--session-id",
            SESSION_ID,
            *extra,
            "--json",
        ]
    )
    assert code == expect
    return captured_json(capsys)


def _codes(payload: dict[str, object]) -> list[str]:
    return [str(finding["code"]) for finding in payload["findings"]]


def _blocking(payload: dict[str, object]) -> list[str]:
    return [
        str(finding["code"])
        for finding in payload["findings"]
        if finding["severity"] == "blocking"
    ]


def test_audit_reports_a_clean_surface_without_mutating_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, _fixture = _grounded_surface(chatlas_root, row)
    before = _fingerprint(surface)

    payload = _audit(capsys, expect=0)

    assert payload["ok"] is True
    assert payload["blocking_finding_count"] == 0
    assert payload["surface_source"] == "live"
    counts = payload["counts"]
    assert counts["delta_count"] == 3
    assert counts["delta_line_count"] == 5
    assert counts["head_line_count"] == 2
    assert counts["line_count"] == 7
    assert counts["distinct_anchor_count"] == 5
    assert counts["resolved_anchor_count"] == 5
    assert counts["home_count"] == 1
    assert counts["head_only_line_count"] == 1
    assert counts["minted_anchor_count"] == 0
    assert counts["reused_anchor_count"] == 0
    # The HEAD-only line is reconciliation work, never a blocking defect.
    assert _codes(payload) == ["head-line-without-delta-home"]
    assert payload["findings"][0]["severity"] == "advisory"
    assert _fingerprint(surface) == before


def test_audit_reports_the_oldest_descriptor_ordered_delta_as_line_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    _surface, fixture = _grounded_surface(chatlas_root, row)

    payload = _audit(capsys, expect=0)

    homes = payload["homes"]
    assert len(homes) == 1
    home = homes[0]
    assert home["occurrence_count"] == 2
    assert home["home"]["relative_path"] == fixture["deltas"][1]["path"]
    assert home["home"]["tape_position"] < home["occurrences"][1]["tape_position"]


def test_audit_blocks_lines_without_exactly_one_trailing_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    first_delta = surface / str(fixture["deltas"][0]["path"])
    first_delta.write_text(
        first_delta.read_text(encoding="utf-8")
        + "- [DC] This maintained line forgot its anchor.\n"
        + f"- [DC] This one carries two. ^{fixture['shared_anchor']} "
        + f"^{fixture['head_only_anchor']}\n",
        encoding="utf-8",
    )

    payload = _audit(capsys, expect=1)

    assert payload["ok"] is False
    assert "line-without-anchor" in _blocking(payload)
    assert "line-with-multiple-anchors" in _blocking(payload)


def test_audit_blocks_an_anchor_whose_attachment_is_not_the_line_it_carries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    head = surface / "HEAD.md"
    head.write_text(
        head.read_text(encoding="utf-8").replace(
            HEAD_ONLY_LINE, "- [CT] The wording drifted away from its attachment."
        ),
        encoding="utf-8",
    )

    payload = _audit(capsys, expect=1)

    assert "anchor-attachment-drift" in _blocking(payload)


def test_audit_blocks_one_anchor_attached_to_two_distinct_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    last_delta = surface / str(fixture["deltas"][2]["path"])
    last_delta.write_text(
        last_delta.read_text(encoding="utf-8")
        + f"- [DC] Different content, same anchor. ^{fixture['shared_anchor']}\n",
        encoding="utf-8",
    )

    payload = _audit(capsys, expect=1)

    blocking = _blocking(payload)
    assert "anchor-triplet-collision" in blocking
    assert "anchor-attachment-drift" in blocking


def test_audit_blocks_delta_support_reaching_past_its_horizon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    identity_hash = str(row["identity_hash"])
    later_turn = str(fixture["user_turns"][-1]["turn_ref"]["turn_id"])
    line = "- [CT] This delta line reaches evidence it cannot see."
    anchor = _anchor(chatlas_root, identity_hash, later_turn, line)
    first_delta = surface / str(fixture["deltas"][0]["path"])
    first_delta.write_text(
        first_delta.read_text(encoding="utf-8") + f"{line} ^{anchor}\n",
        encoding="utf-8",
    )

    payload = _audit(capsys, expect=1)

    assert "support-beyond-delta-horizon" in _blocking(payload)


def test_audit_blocks_a_delta_horizon_timestamp_the_chat_does_not_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    first_delta = surface / str(fixture["deltas"][0]["path"])
    body = first_delta.read_text(encoding="utf-8").splitlines()
    turn_id = first_delta.stem
    body[0] = f"# Chat.Index.Delta/{turn_id} @ 2020-01-01T00:00:00.000Z"
    first_delta.write_text("\n".join(body) + "\n", encoding="utf-8")

    payload = _audit(capsys, expect=1)

    assert "delta-horizon-timestamp-mismatch" in _blocking(payload)


def test_audit_blocks_a_delta_horizon_that_is_not_a_turn_of_the_chat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    first_delta = surface / str(fixture["deltas"][0]["path"])
    body = first_delta.read_text(encoding="utf-8").splitlines()
    body[0] = "# Chat.Index.Delta/turn-elsewhere"
    (surface / "deltas" / "turn-elsewhere.md").write_text(
        "\n".join(body) + "\n", encoding="utf-8"
    )
    first_delta.unlink()

    payload = _audit(capsys, expect=1)

    assert "delta-horizon-absent-from-source" in _blocking(payload)


def test_audit_blocks_a_head_evidence_horizon_the_chat_does_not_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, _fixture = _grounded_surface(chatlas_root, row)
    head = surface / "HEAD.md"
    body = [
        "Evidence.Horizon: `turn-elsewhere`"
        if line.startswith("Evidence.Horizon:")
        else line
        for line in head.read_text(encoding="utf-8").splitlines()
    ]
    head.write_text("\n".join(body) + "\n", encoding="utf-8")

    payload = _audit(capsys, expect=1)

    assert "head-horizon-absent-from-source" in _blocking(payload)


def test_audit_blocks_an_unreadable_surface_without_reading_further(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, _fixture = _grounded_surface(chatlas_root, row)
    (surface / "deltas" / "never-declared.md").write_text(
        "- [DC] A Delta that declares no horizon at all.\n", encoding="utf-8"
    )

    payload = _audit(capsys, expect=1)

    assert _blocking(payload) == ["surface-unreadable"]
    assert payload["counts"]["line_count"] == 0


def test_audit_of_a_staged_surface_leaves_the_live_surface_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    staged = tmp_path / "staged-surface"
    shutil.copytree(surface, staged)
    staged_delta = staged / str(fixture["deltas"][0]["path"])
    staged_delta.write_text(
        staged_delta.read_text(encoding="utf-8")
        + "- [DC] The staged copy forgot an anchor.\n",
        encoding="utf-8",
    )
    live_before = _fingerprint(surface)

    staged_payload = _audit(capsys, "--surface", str(staged), expect=1)
    assert staged_payload["surface_source"] == "staged"
    assert "line-without-anchor" in _blocking(staged_payload)

    live_payload = _audit(capsys, expect=0)
    assert live_payload["ok"] is True
    assert _fingerprint(surface) == live_before


def test_audit_reports_append_only_growth_as_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    _surface, _fixture = _grounded_surface(chatlas_root, row)
    rollout = (
        tmp_path
        / "codex-home"
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{SESSION_ID}.jsonl"
    )
    messages = [
        item
        for exchange in range(26)
        for item in (
            ("user", f"user touched change {exchange:02d}"),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=messages)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    payload = _audit(capsys, expect=0)

    assert payload["ok"] is True
    assert "source-append-only" in _codes(payload)
    assert payload["tail"]["state"] == "append-only"


def test_line_home_is_the_oldest_evidenced_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Home is chosen by where the chat put it, and the anchor agrees."""
    from tarav.index_model import canonical_index_line_statement

    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, fixture = _grounded_surface(chatlas_root, row)
    identity_hash = str(row["identity_hash"])
    deltas = fixture["deltas"]
    first_turn = str(deltas[0]["horizon"]["turn_id"])

    # The same line in both Deltas, grounded in the earlier turn.
    line = "- [CT] This line is materialized twice."
    anchor = _anchor(chatlas_root, identity_hash, first_turn, line)
    for descriptor in deltas[:2]:
        path = surface / str(descriptor["path"])
        path.write_text(
            path.read_text(encoding="utf-8") + f"{line} ^{anchor}\n",
            encoding="utf-8",
        )
    head = surface / "HEAD.md"
    head.write_text(
        head.read_text(encoding="utf-8") + f"{line} ^{anchor}\n", encoding="utf-8"
    )

    payload = _audit(capsys, expect=0)

    home = next(
        item
        for item in payload["homes"]
        if item["statement_key"] == canonical_index_line_statement(line)
    )
    assert home["occurrence_count"] == 2
    assert home["home"]["horizon"]["turn_id"] == first_turn
    assert home["home"]["tape_position"] < home["occurrences"][1]["tape_position"]
