from __future__ import annotations

from pathlib import Path

import pytest

from tarav.cli.cli import main
from tarav.chatlas.chat_index import chatlas_chat_index_source
from tarav.chatlas.event_query import chatlas_turns_query

from ._e2e_helpers import (
    _configure_chatlas,
    _index_rows,
    _isolate_chatlas,
    _write_codex_rollout,
)
from ._helpers import captured_json


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fe2"
REPEATED_LINE = "- [DC] `Chat.Index.HEAD` presents the current chat model."


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


def _user_turns_in_tape_order(
    chatlas_root: Path,
    row: dict[str, object],
) -> list[tuple[int, dict[str, object]]]:
    payload = chatlas_turns_query(
        identity_hash=str(row["identity_hash"]),
        detail="turn",
        sort="oldest",
        limit=1000,
        chatlas_root=chatlas_root,
    )
    result: list[tuple[int, dict[str, object]]] = []
    for turn in payload["turns"]:
        events = turn["normal_turn"]["events"]
        if not any(
            event.get("producer", {}).get("type") == "human"
            and event.get("payload", {}).get("role") == "user"
            for event in events
        ):
            continue
        result.append((min(event["sequence"] for event in events), turn["turn_ref"]))
    return sorted(result)


def _materialize_v2(
    chatlas_root: Path,
    row: dict[str, object],
) -> tuple[Path, list[dict[str, object]]]:
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    (surface / "deltas").mkdir(parents=True)
    user_turns = _user_turns_in_tape_order(chatlas_root, row)
    selected = [user_turns[index] for index in (3, 7, 11, 15, 19, 23)]
    deltas: list[dict[str, object]] = []
    for delta_index, (tape_position, turn_ref) in enumerate(selected):
        path = f"deltas/{turn_ref['turn_id']}.md"
        lines = [
            f"# Chat.Index.Delta/{turn_ref['turn_id']} @ {turn_ref['at']}",
            "",
            f"- [CT] Captured medium-chat change {delta_index}.",
        ]
        if delta_index in {1, 4}:
            lines.append(REPEATED_LINE)
        (surface / path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        deltas.append(
            {
                "path": path,
                "horizon": turn_ref,
                "tape_position": tape_position,
            }
        )
    horizon = chatlas_chat_index_source(
        identity_hash=str(row["identity_hash"]),
        chatlas_root=chatlas_root,
    )["source"]["turn_refs"][-1]["turn_ref"]
    (surface / "HEAD.md").write_text(
        "# Chat.Index.HEAD\n\n"
        f"Evidence.Horizon: `{horizon['turn_id']}` @ {horizon['at']}\n\n"
        f"{REPEATED_LINE}\n"
        "- [POI] This HEAD-only line still needs a Delta home.\n",
        encoding="utf-8",
    )
    return surface, deltas


def test_medium_chat_v2_cli_preserves_tape_order_and_selects_oldest_line_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, expected_deltas = _materialize_v2(chatlas_root, row)
    selector = ["--session-id", SESSION_ID]

    assert main(["chatlas", "chat-index", "source", *selector, "--json"]) == 0
    source = captured_json(capsys)["source"]
    assert source["turn_count"] == 48
    assert source["linear"] is True
    assert source["findings"] == []
    positions = [turn["tape_position"] for turn in source["turn_refs"]]
    assert positions == sorted(positions)

    assert main(["chatlas", "chat-index", "status", *selector, "--json"]) == 0
    status = captured_json(capsys)["chat_index"]
    assert status["state"] == "materialized"
    assert status["freshness"]["state"] == "current"
    assert status["layout"] == "delta-head-v2"
    assert status["delta_count"] == 6

    assert main(["chatlas", "chat-index", "deltas", *selector, "--json"]) == 0
    deltas = captured_json(capsys)["deltas"]
    assert [item["path"] for item in deltas] == [
        str(surface / delta["path"]) for delta in expected_deltas
    ]
    assert all(item["exists"] is True for item in deltas)

    assert main(["chatlas", "chat-index", "head", *selector, "--json"]) == 0
    head = captured_json(capsys)["head"]
    assert head["path"] == str(surface / "HEAD.md")
    assert head["exists"] is True

    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "home",
                *selector,
                "--line-content",
                REPEATED_LINE,
                "--json",
            ]
        )
        == 0
    )
    home = captured_json(capsys)
    assert home["match_count"] == 2
    assert home["home"]["relative_path"] == expected_deltas[1]["path"]
    assert home["home"]["tape_position"] == expected_deltas[1]["tape_position"]

    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "home",
                *selector,
                "--line-content",
                "- [POI] This HEAD-only line still needs a Delta home.",
                "--json",
            ]
        )
        == 0
    )
    missing = captured_json(capsys)
    assert missing["home"] is None
    assert missing["finding"]["kind"] == "missing-line-home"


def test_v2_delta_order_is_the_chats_order_not_the_directory_listing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    _surface, expected_deltas = _materialize_v2(chatlas_root, row)

    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "deltas",
                "--session-id",
                SESSION_ID,
                "--json",
            ]
        )
        == 0
    )
    deltas = captured_json(capsys)["deltas"]

    # The listing is alphabetical by turn id; the reported order is the tape's.
    assert [item["relative_path"] for item in deltas] == [
        delta["path"] for delta in expected_deltas
    ]
    assert [item["tape_position"] for item in deltas] == [
        delta["tape_position"] for delta in expected_deltas
    ]
    assert [item["relative_path"] for item in deltas] != sorted(
        item["relative_path"] for item in deltas
    )


def test_medium_chat_v2_tail_tracks_growth_then_becomes_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, _deltas = _materialize_v2(chatlas_root, row)
    selector = ["--session-id", SESSION_ID]

    assert main(["chatlas", "chat-index", "tail", *selector, "--json"]) == 0
    current = captured_json(capsys)["tail"]
    assert current["state"] == "current"
    assert current["pending_turn_count"] == 0

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

    before = (surface / "HEAD.md").read_bytes()
    before_horizon = next(
        line
        for line in before.decode("utf-8").splitlines()
        if line.startswith("Evidence.Horizon:")
    ).split(" @ ")[0]
    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "tail",
                *selector,
                "--detail",
                "turn",
                "--json",
            ]
        )
        == 0
    )
    grown = captured_json(capsys)
    assert grown["tail"]["state"] == "append-only"
    assert grown["tail"]["pending_turn_count"] == 4
    assert len(grown["turns"]) == 4
    assert [turn["role"] for turn in grown["turns"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert (surface / "HEAD.md").read_bytes() == before

    # Maintaining the capture means moving the horizon HEAD declares.
    horizon = chatlas_chat_index_source(
        identity_hash=str(row["identity_hash"]),
        chatlas_root=chatlas_root,
    )["source"]["turn_refs"][-1]["turn_ref"]
    head = surface / "HEAD.md"
    head.write_text(
        head.read_text(encoding="utf-8").replace(
            before_horizon, f"Evidence.Horizon: `{horizon['turn_id']}`"
        ),
        encoding="utf-8",
    )

    assert main(["chatlas", "chat-index", "tail", *selector, "--json"]) == 0
    maintained = captured_json(capsys)["tail"]
    assert maintained["state"] == "current"
    assert maintained["pending_turn_count"] == 0


def test_medium_chat_v2_tail_chat_detail_returns_message_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, _deltas = _materialize_v2(chatlas_root, row)
    selector = ["--session-id", SESSION_ID]

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
        for exchange in range(25)
        for item in (
            ("user", f"user touched change {exchange:02d}"),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=messages)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    before = (surface / "HEAD.md").read_bytes()
    assert (
        main(
            [
                "chatlas",
                "chat-index",
                "tail",
                *selector,
                "--detail",
                "chat",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert payload["tail"]["state"] == "append-only"
    assert payload["tail"]["pending_turn_count"] == 2
    turns = payload["turns"]
    assert len(turns) == 2
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert all("normal_turn" not in turn for turn in turns)
    assert [
        [message["text"] for message in turn["messages"]] for turn in turns
    ] == [["user touched change 24"], ["assistant interpreted change 24"]]
    for turn in turns:
        assert turn["turn_ref"]["session"] == row["identity_hash"]
        assert isinstance(turn["tape_position"], int)
        assert turn["producer_type"] in {"human", "assistant"}
        assert all(
            isinstance(message["sequence"], int) for message in turn["messages"]
        )
    assert (surface / "HEAD.md").read_bytes() == before


def test_chat_index_tail_rejects_unknown_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    _materialize_v2(chatlas_root, row)

    with pytest.raises(SystemExit) as refusal:
        main(
            [
                "chatlas",
                "chat-index",
                "tail",
                "--session-id",
                SESSION_ID,
                "--detail",
                "product",
                "--json",
            ]
        )
    assert refusal.value.code == 2


def test_a_revision_inside_the_read_prefix_is_not_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The Accepted.Loss of Impl.Req 556, pinned so it stays deliberate.

    The read prefix is reconstructed from the horizon HEAD declares, not from a
    stored snapshot, so a turn revised behind that horizon leaves no trace to
    compare against. Growth past the horizon is still fully detected.
    """
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    surface, _deltas = _materialize_v2(chatlas_root, row)
    selector = ["--session-id", SESSION_ID]
    before = (surface / "HEAD.md").read_bytes()
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
        for exchange in range(24)
        for item in (
            (
                "user",
                "changed historical touch"
                if exchange == 3
                else f"user touched change {exchange:02d}",
            ),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=messages)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    assert main(["chatlas", "chat-index", "tail", *selector, "--json"]) == 0
    tail = captured_json(capsys)["tail"]
    assert tail["state"] == "current"
    assert tail["pending_turn_count"] == 0
    assert (surface / "HEAD.md").read_bytes() == before
