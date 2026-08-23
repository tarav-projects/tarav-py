from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path

import pytest

from tarav.cli.cli import main
from tarav.index_model import index_line_anchor_triplet_hash
from tarav.testing import TaravTestEnvironment


def _write_codex_rollout(
    path: Path,
    *,
    session_id: str,
    messages: list[tuple[str, str]],
) -> None:
    records: list[dict[str, object]] = [
        {
            "timestamp": "2026-08-15T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": "2026-08-15T00:00:01.000Z",
            "type": "turn_context",
            "payload": {"turn_id": "turn-1", "model": "gpt"},
        },
    ]
    for index, (role, text) in enumerate(messages, start=2):
        records.append(
            {
                "timestamp": f"2026-08-15T00:00:{index:02d}.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "id": f"message-{index}",
                    "role": role,
                    "content": [
                        {
                            "type": "output_text"
                            if role == "assistant"
                            else "input_text",
                            "text": text,
                        }
                    ],
                },
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _write_script_spec(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "tarav.chatlas2.conformance.script.v1",
                "script_id": "sample",
                "revision": 1,
                "title": "Sample",
                "user_messages": ["first question"],
                "operator_actions": [],
                "features": ["messages"],
                "capture_requirements": ["closed-session"],
            }
        ),
        encoding="utf-8",
    )


def _run_json_command(argv: list[str]) -> dict[str, object]:
    output = StringIO()
    diagnostics = StringIO()
    with redirect_stdout(output), redirect_stderr(diagnostics):
        status = main(argv)
    # A swallowed failure reports only "1 != 0"; the command already said why.
    assert status == 0, (
        f"{argv} exited {status}\n"
        f"stdout: {output.getvalue()}\nstderr: {diagnostics.getvalue()}"
    )
    payload = json.loads(output.getvalue())
    assert isinstance(payload, dict)
    return payload


def test_chatlas2_cli_normalizes_every_archived_codex_transcript(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    first_home = tmp_path / "codex-first"
    second_home = tmp_path / "codex-second"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    relative = Path("sessions/2026/08/15") / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        first_home / relative,
        session_id=session_id,
        messages=[("user", "first question"), ("assistant", "first answer")],
    )
    _write_codex_rollout(
        second_home / relative,
        session_id=session_id,
        messages=[
            ("user", "first question"),
            ("assistant", "first answer"),
            ("user", "second question"),
            ("assistant", "second answer"),
        ],
    )
    environment.write_global_config(
        chatlas={
            "sources": [
                {"provider": "codex", "home": str(first_home)},
                {"provider": "codex", "home": str(second_home)},
            ]
        }
    )
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()

    assert main(["chatlas", "normalize", "--session-id", session_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["class"] == "tarav.chatlas2.normal_model"
    assert payload["schema_version"] == 6
    assert "raw" not in payload
    assert all("record" not in event for event in payload["events"])
    assert payload["session"]["session_id"] == session_id
    assert len(payload["sources"]) == 2
    assert len(payload["events"]) == 6
    assert len(payload["annotations"]["chat_messages"]) == 4
    assert all("event_id" not in event for event in payload["events"])
    assert payload["metadata"]["commit"]

    cached = _run_json_command(
        ["chatlas", "cache", "status", "--session-id", session_id, "--json"]
    )
    assert cached["standing"] == "FRESH"

    refreshed = _run_json_command(
        [
            "chatlas",
            "normalize",
            "--session-id",
            session_id,
            "--refresh",
            "--json",
        ]
    )
    assert refreshed == payload

    def refuse_cached_normalization(*_args, **_kwargs):
        raise AssertionError("default Normal Model access must reuse a fresh cache")

    monkeypatch.setattr(
        "tarav.chatlas.lossless.cache.build_normal_model_from_row",
        refuse_cached_normalization,
    )
    reused = _run_json_command(
        ["chatlas", "normalize", "--session-id", session_id, "--json"]
    )
    assert reused == payload

    assert (
        main(
            [
                "chatlas",
                "normalize",
                "--session-id",
                session_id,
                "--include-raw",
                "--json",
            ]
        )
        == 0
    )
    enriched = json.loads(capsys.readouterr().out)
    raw = enriched.pop("raw")
    assert enriched == payload
    assert len(raw) == 2
    assert all(fragment["value"]["records"] for fragment in raw)

    assert (
        main(
            [
                "chatlas",
                "messages",
                "find",
                "--session-id",
                session_id,
                "--side",
                "user",
                "--contains",
                "second question",
                "--exact",
                "--json",
            ]
        )
        == 0
    )
    found = json.loads(capsys.readouterr().out)
    assert found["count"] == 1
    member_ref = found["messages"][0]["member_ref"]
    line = "- [DF] The second question is retained."

    assert (
        main(
            [
                "chatlas",
                "anchory",
                "preview",
                "--member",
                member_ref,
                "--line-content",
                line,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["action"] == "mint"

    register_args = [
        "chatlas",
        "anchory",
        "register",
        "--member",
        member_ref,
        "--line-content",
        line,
    ]
    assert main(register_args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["action"] == "minted"
    assert main(register_args) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["action"] == "reused"
    assert repeated["anchor"] == first["anchor"]

    assert main(["chatlas", "anchory", "resolve", first["anchor"]]) == 0
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["members"][0]["standing"] == "MATCHED"
    assert resolved["members"][0]["text"] == "second question"

    batch = tmp_path / "chatlas2-anchor-batch.json"
    batch.write_text(
        json.dumps(
            {
                "schema": "tarav.chatlas2.anchor-batch.v2",
                "items": [
                    {
                        "client_id": "alpha",
                        "line_content": "- [DF] First batch line.",
                        "members": [member_ref],
                    },
                    {
                        "client_id": "beta",
                        "line_content": "- [DF] Second batch line.",
                        "members": [member_ref],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    batch_prefix = ["chatlas", "anchory", "batch"]
    assert main([*batch_prefix, "preview", "--input", str(batch)]) == 0
    assert json.loads(capsys.readouterr().out)["mint_count"] == 2
    assert main([*batch_prefix, "register", "--input", str(batch)]) == 0
    first_batch = json.loads(capsys.readouterr().out)
    assert first_batch["minted_count"] == 2
    assert main([*batch_prefix, "register", "--input", str(batch)]) == 0
    repeated_batch = json.loads(capsys.readouterr().out)
    assert repeated_batch["minted_count"] == 0
    assert repeated_batch["reused_count"] == 2



def test_chatlas2_cache_cli_and_bounded_message_reads_reuse_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    rollout = home / "sessions/2026/08/15" / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        rollout,
        session_id=session_id,
        messages=[
            ("user", "first question"),
            ("assistant", "first answer"),
            ("user", "second question"),
        ],
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(home)}]}
    )
    _run_json_command(["chatlas", "index", "update", "--provider", "codex", "--json"])

    missing = _run_json_command(
        ["chatlas", "cache", "status", "--session-id", session_id, "--json"]
    )
    assert missing["standing"] == "MISSING"

    bounded = _run_json_command(
        [
            "chatlas",
            "messages",
            "list",
            "--session-id",
            session_id,
            "--side",
            "user",
            "--limit",
            "1",
            "--json",
        ]
    )
    assert bounded["count"] == 1
    assert bounded["messages"][0]["message"]["text"] == "first question"

    fresh = _run_json_command(
        ["chatlas", "cache", "status", "--session-id", session_id, "--json"]
    )
    assert fresh["standing"] == "FRESH"
    assert Path(fresh["path"]).is_dir()
    rebuilt = _run_json_command(
        ["chatlas", "cache", "build", "--session-id", session_id, "--json"]
    )
    assert rebuilt["standing"] == "FRESH"

    def refuse_normalization(*_args, **_kwargs):
        raise AssertionError("a fresh message read must not normalize")

    monkeypatch.setattr(
        "tarav.chatlas.lossless.cache.build_normal_model_from_row",
        refuse_normalization,
    )
    found = _run_json_command(
        [
            "chatlas",
            "messages",
            "find",
            "--session-id",
            session_id,
            "--side",
            "user",
            "--contains",
            "question",
            "--limit",
            "1",
            "--json",
        ]
    )
    assert found["count"] == 1
    assert found["messages"][0]["at"] == "2026-08-15T00:00:02.000Z"


def test_chatlas2_views_list_and_get_initial_cache_backed_projections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    rollout = home / "sessions/2026/08/15" / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        rollout,
        session_id=session_id,
        messages=[
            ("user", "first question"),
            ("assistant", "first answer"),
            ("user", "second question"),
        ],
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(home)}]}
    )
    _run_json_command(["chatlas", "index", "update", "--provider", "codex", "--json"])

    listed = _run_json_command(["chatlas", "views", "list", "--json"])
    assert [(view["name"], view["collection"]) for view in listed["views"]] == [
        ("full", "normal_model"),
        ("transcript", "chat_messages"),
        ("user", "chat_messages"),
        ("events", "events"),
    ]

    full = _run_json_command(
        ["chatlas", "views", "get", "--session-id", session_id, "--json"]
    )
    assert full["class"] == "tarav.chatlas2.normal_model"
    assert full["session"]["session_id"] == session_id
    assert len(full["events"]) == 5

    transcript = _run_json_command(
        [
            "chatlas",
            "views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "transcript",
            "--limit",
            "2",
            "--json",
        ]
    )
    assert transcript["class"] == "tarav.chatlas2.view"
    assert transcript["view"] == "transcript"
    assert transcript["count"] == 2
    assert [record["message"]["text"] for record in transcript["messages"]] == [
        "first question",
        "first answer",
    ]
    assert transcript["messages"][0]["at"] == "2026-08-15T00:00:02.000Z"

    user = _run_json_command(
        [
            "chatlas",
            "views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "user",
            "--json",
        ]
    )
    assert user["count"] == 2
    assert [record["message"]["text"] for record in user["messages"]] == [
        "first question",
        "second question",
    ]
    assert all(record["message"]["side"] == "user" for record in user["messages"])

    events = _run_json_command(
        [
            "chatlas",
            "views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--limit",
            "1",
            "--json",
        ]
    )
    assert events["count"] == 1
    assert events["events"][0]["started_at"] == "2026-08-15T00:00:00.000Z"

    diagnostics = StringIO()
    with redirect_stderr(diagnostics):
        assert (
            main(
                [
                    "chatlas",
                    "views",
                    "get",
                    "--session-id",
                    session_id,
                    "--view",
                    "full",
                    "--limit",
                    "1",
                ]
            )
            == 1
        )
    assert "--limit is unavailable for the full view" in diagnostics.getvalue()


def test_chatlas2_turns_list_lookup_and_hydrate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    rollout = home / "sessions/2026/08/15" / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        rollout,
        session_id=session_id,
        messages=[("user", "first question"), ("assistant", "first answer")],
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(home)}]}
    )
    _run_json_command(["chatlas", "index", "update", "--provider", "codex", "--json"])

    listed = _run_json_command(
        [
            "chatlas",
            "turns",
            "list",
            "--session-id",
            session_id,
            "--side",
            "user",
            "--limit",
            "1",
            "--json",
        ]
    )
    assert listed["count"] == 1
    assert listed["turns"][0]["side"] == "user"
    message_address = listed["turns"][0]["message_refs"][0]["message_address"]

    compact = _run_json_command(
        [
            "chatlas",
            "turns",
            "get",
            "--session-id",
            session_id,
            "--message-address",
            message_address,
            "--json",
        ]
    )
    assert compact["turn"] == listed["turns"][0]

    hydrated = _run_json_command(
        [
            "chatlas",
            "turns",
            "get",
            "--session-id",
            session_id,
            "--turn-address",
            compact["turn"]["turn_address"],
            "--hydrate",
            "--json",
        ]
    )
    assert hydrated["class"] == "Chat.Turn.Hydration"
    assert hydrated["messages"][0]["message"]["text"] == "first question"
    assert hydrated["events"][0]["raw_observations"][0]["value"]["type"] == (
        "response_item"
    )


def test_direct_raw_normalization_does_not_create_an_ordinary_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    rollout = home / "sessions/2026/08/15" / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        rollout,
        session_id=session_id,
        messages=[("user", "first question")],
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(home)}]}
    )
    _run_json_command(["chatlas", "index", "update", "--provider", "codex", "--json"])

    normalized = _run_json_command(
        [
            "chatlas",
            "normalize",
            "--session-id",
            session_id,
            "--include-raw",
            "--json",
        ]
    )
    assert normalized["raw"]
    status = _run_json_command(
        ["chatlas", "cache", "status", "--session-id", session_id, "--json"]
    )
    assert status["standing"] == "MISSING"


def test_chatlas2_e2e_prints_one_index_line_grounded_on_a_user_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    rollout = home / "sessions/2026/08/15" / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        rollout,
        session_id=session_id,
        messages=[
            ("user", "Ground one design statement on this user message."),
            ("assistant", "Ready."),
        ],
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(home)}]}
    )
    _run_json_command(["chatlas", "index", "update", "--provider", "codex", "--json"])

    found = _run_json_command(
        [
            "chatlas",
            "messages",
            "find",
            "--session-id",
            session_id,
            "--side",
            "user",
            "--contains",
            "Ground one design statement on this user message.",
            "--exact",
            "--json",
        ]
    )
    assert found["count"] == 1
    member_ref = found["messages"][0]["member_ref"]
    line = "- [DF] One design statement is grounded on user evidence."
    registered = _run_json_command(
        [
            "chatlas",
            "anchory",
            "register",
            "--member",
            member_ref,
            "--line-content",
            line,
        ]
    )
    anchor = registered["anchor"]
    assert registered["action"] == "minted"
    assert anchor == "c20260815-0u"

    resolved = _run_json_command(
        ["chatlas", "anchory", "resolve", anchor, "--radius", "0"]
    )
    assert resolved["members"][0]["standing"] == "MATCHED"
    assert resolved["members"][0]["side"] == "user"

    hypothetical_index_line = f"{line} ^{anchor}"
    attachment = registered["record"]["attachment"]
    assert attachment["triplet_hash"] == index_line_anchor_triplet_hash(
        hypothetical_index_line,
        anchor,
    )
    print(f"hypothetical Index.Line: {hypothetical_index_line}")


def test_chatlas2_corpus_cli_prepares_registers_lists_and_verifies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675c22"
    rollout = home / "sessions/2026/08/15" / f"rollout-{session_id}.jsonl"
    _write_codex_rollout(
        rollout,
        session_id=session_id,
        messages=[("user", "first question"), ("assistant", "first answer")],
    )
    environment.write_global_config(
        chatlas={"sources": [{"provider": "codex", "home": str(home)}]}
    )
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    corpus = tmp_path / "corpus"
    stage = tmp_path / "stage"
    script = tmp_path / "sample.json"
    _write_script_spec(script)

    assert (
        main(
            [
                "chatlas",
                "corpus",
                "ingest",
                "prepare",
                "--corpus",
                str(corpus),
                "--stage",
                str(stage),
                "--script",
                str(script),
                "--provider",
                "codex",
                "--session-id",
                session_id,
                "--captured-at",
                "2026-08-15",
                "--feature",
                "messages",
                "--json",
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    candidate = prepared["candidate"]
    assert not corpus.exists()

    assert (
        main(
            [
                "chatlas",
                "corpus",
                "ingest",
                "register",
                "--corpus",
                str(corpus),
                "--candidate",
                candidate,
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["registered"] is True
    assert main(["chatlas", "corpus", "list", "--corpus", str(corpus), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["capture_count"] == 1
    assert (
        main(["chatlas", "corpus", "verify", "--corpus", str(corpus), "--json"]) == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "artifact_count": 1,
        "capture_count": 1,
        "status": "ok",
    }
    _write_script_spec(corpus / "specifications" / "sample.json")
    assert main(["chatlas", "corpus", "check", "--corpus", str(corpus), "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "ok"
    assert checked["passed_count"] == 1
