from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main

from ._e2e_helpers import _configure_chatlas, _isolate_chatlas, _write_codex_rollout
from ._helpers import captured_json


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
SELECTOR = ["--product", "zip-transcript-summary", "--session-id", SESSION_ID]


def _stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, str]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{SESSION_ID}.jsonl"
    )
    _write_codex_rollout(
        rollout,
        session_id=SESSION_ID,
        messages=[
            ("user", "first question"),
            ("assistant", "a long assistant answer that should be compressed"),
            ("user", "second question"),
            ("assistant", "another long assistant answer"),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    assert main(["chatlas", "products", "produce", *SELECTOR, "--json"]) == 0
    return captured_json(capsys)["stage"]


def test_scaffold_writes_a_structurally_complete_empty_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    payload = captured_json(capsys)["scaffold"]
    source = json.loads(Path(stage["input_path"]).read_text(encoding="utf-8"))
    written = json.loads(Path(stage["output_path"]).read_text(encoding="utf-8"))

    for field in ("class", "schema_version", "view", "session"):
        assert written[field] == source[field]
    assert len(written["turns"]) == len(source["turns"])
    assert [t["role"] for t in written["turns"]] == [t["role"] for t in source["turns"]]
    for src, out in zip(source["turns"], written["turns"], strict=True):
        if src["role"] == "user":
            assert out["text"] == src["text"]
        else:
            assert out["text"] == ""
    assert payload["turn_count"] == len(source["turns"])
    assert payload["assistant_turns_to_fill"] == sum(
        1 for t in source["turns"] if t["role"] == "assistant"
    )


def test_scaffold_refuses_to_overwrite_without_force(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage(tmp_path, monkeypatch, capsys)
    Path(stage["output_path"]).write_text('{"filled": true}', encoding="utf-8")

    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 1
    )
    assert Path(stage["output_path"]).read_text(encoding="utf-8") == '{"filled": true}'

    assert (
        main(
            [
                "chatlas",
                "products",
                "scaffold",
                "--stage-id",
                stage["stage_id"],
                "--force",
                "--json",
            ]
        )
        == 0
    )
    assert "filled" not in Path(stage["output_path"]).read_text(encoding="utf-8")


def test_check_reports_the_scaffold_as_incomplete_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 1
    )
    payload = captured_json(capsys)
    assert payload["status"] == "error"
    assert payload["check"]["ok"] is False
    finding = payload["check"]["finding"]
    assert "Turn.AssistantTextBlank" in finding["class_sugar"]
    assert finding["severity"] == "error"


def test_check_passes_a_filled_artifact_and_does_not_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage(tmp_path, monkeypatch, capsys)
    source = json.loads(Path(stage["input_path"]).read_text(encoding="utf-8"))
    filled = dict(source)
    filled["turns"] = [
        {**t, "text": "summary" if t["role"] == "assistant" else t["text"]}
        for t in source["turns"]
    ]
    Path(stage["output_path"]).write_text(json.dumps(filled), encoding="utf-8")

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 0
    )
    payload = captured_json(capsys)
    assert payload["status"] == "ok"
    assert payload["check"]["ok"] is True
    assert payload["check"]["finding"] is None
    # check never materializes the depot
    assert (
        main(["chatlas", "products", "status", *SELECTOR, "--json"]) == 0
    )
    assert captured_json(capsys)["product"]["state"] == "production_required"
    # the stage survives a check, so commit still works afterwards
    assert (
        main(
            ["chatlas", "products", "commit", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    assert captured_json(capsys)["product"]["state"] == "fresh"


def test_check_reports_a_broken_user_turn_with_its_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage(tmp_path, monkeypatch, capsys)
    source = json.loads(Path(stage["input_path"]).read_text(encoding="utf-8"))
    broken = dict(source)
    broken["turns"] = [
        {**t, "text": "tampered" if t["role"] == "user" else "summary"}
        for t in source["turns"]
    ]
    Path(stage["output_path"]).write_text(json.dumps(broken), encoding="utf-8")

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 1
    )
    finding = captured_json(capsys)["check"]["finding"]
    assert "Turn.UserTextNotVerbatim" in finding["class_sugar"]
    assert finding["evidence"]["turn_index"] == 0


def test_check_requires_a_written_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage(tmp_path, monkeypatch, capsys)
    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 1
    )
    payload = captured_json(capsys)
    assert payload["check"]["ok"] is False
    assert "missing" in payload["check"]["error"]


def test_scaffold_then_fill_then_check_then_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The documented producer loop, end to end."""
    stage = _stage(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()

    output = Path(stage["output_path"])
    payload = json.loads(output.read_text(encoding="utf-8"))
    for turn in payload["turns"]:
        if turn["role"] == "assistant":
            turn["text"] = "compressed"
    output.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 0
    )
    assert captured_json(capsys)["check"]["ok"] is True
    assert (
        main(
            ["chatlas", "products", "commit", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    assert captured_json(capsys)["product"]["state"] == "fresh"


LARGE_SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fd6"
LARGE_SELECTOR = [
    "--product",
    "zip-transcript-summary",
    "--session-id",
    LARGE_SESSION_ID,
]


def _stage_large(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, str]:
    """Stage a session big enough for the compression floor to apply."""
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{LARGE_SESSION_ID}.jsonl"
    )
    _write_codex_rollout(
        rollout,
        session_id=LARGE_SESSION_ID,
        messages=[
            ("user", "first question"),
            ("assistant", "answer one. " * 3000),
            ("user", "second question"),
            ("assistant", "answer two. " * 3000),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    assert main(["chatlas", "products", "produce", *LARGE_SELECTOR, "--json"]) == 0
    return captured_json(capsys)["stage"]


def _fill(stage: dict[str, str], *, text_for: object) -> None:
    output = Path(stage["output_path"])
    payload = json.loads(output.read_text(encoding="utf-8"))
    for index, turn in enumerate(payload["turns"]):
        if turn["role"] == "assistant":
            turn["text"] = text_for(index, turn)
    output.write_text(json.dumps(payload), encoding="utf-8")


def test_check_refuses_an_uncompressed_large_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage_large(tmp_path, monkeypatch, capsys)
    source = json.loads(Path(stage["input_path"]).read_text(encoding="utf-8"))
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()
    _fill(stage, text_for=lambda index, _turn: source["turns"][index]["text"])

    assert (
        main(
            [
                "chatlas",
                "products",
                "check",
                "--stage-id",
                stage["stage_id"],
                "--json",
            ]
        )
        == 1
    )
    check = captured_json(capsys)["check"]
    assert check["ok"] is False
    assert "Compression.Insufficient" in check["finding"]["class_sugar"]
    assert check["finding"]["evidence"]["retained_ratio"] == 1.0


def test_allow_low_compression_waives_the_floor_and_is_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The escape hatch exists so the alternative is not truncation."""
    stage = _stage_large(tmp_path, monkeypatch, capsys)
    source = json.loads(Path(stage["input_path"]).read_text(encoding="utf-8"))
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()
    _fill(stage, text_for=lambda index, _turn: source["turns"][index]["text"])

    assert (
        main(
            [
                "chatlas",
                "products",
                "check",
                "--stage-id",
                stage["stage_id"],
                "--allow-low-compression",
                "--json",
            ]
        )
        == 0
    )
    assert captured_json(capsys)["check"]["ok"] is True

    assert (
        main(
            [
                "chatlas",
                "products",
                "commit",
                "--stage-id",
                stage["stage_id"],
                "--allow-low-compression",
                "--json",
            ]
        )
        == 0
    )
    product = captured_json(capsys)["product"]
    assert product["state"] == "fresh"
    manifest = json.loads(
        (Path(product["artifact"]["path"]).parent / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["compression"]["allow_low_compression"] is True
    assert manifest["compression"]["retained_ratio"] == 1.0


def test_compressed_large_artifact_passes_the_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage_large(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()
    _fill(stage, text_for=lambda _index, _turn: "a compact assistant summary. " * 400)

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 0
    )
    assert captured_json(capsys)["check"]["ok"] is True
    assert (
        main(
            ["chatlas", "products", "commit", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    product = captured_json(capsys)["product"]
    manifest = json.loads(
        (Path(product["artifact"]["path"]).parent / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["compression"]["floor_applied"] is True
    assert manifest["compression"]["collapse_applied"] is True
    assert manifest["compression"]["retained_ratio"] < 0.40


def test_check_refuses_a_collapsed_large_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Over-retention is a fat artifact; collapse is a wrong one, so it refuses too."""
    stage = _stage_large(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()
    _fill(stage, text_for=lambda _index, _turn: "Yes.")

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 1
    )
    check = captured_json(capsys)["check"]
    assert check["ok"] is False
    assert "Compression.TurnCollapsed" in check["finding"]["class_sugar"]
    assert check["finding"]["evidence"]["collapsed_turn_indices"] == [1, 3]


def test_allow_aggressive_compression_waives_collapse_and_is_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = _stage_large(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()
    _fill(stage, text_for=lambda _index, _turn: "Yes.")

    assert (
        main(
            [
                "chatlas",
                "products",
                "commit",
                "--stage-id",
                stage["stage_id"],
                "--allow-aggressive-compression",
                "--json",
            ]
        )
        == 0
    )
    product = captured_json(capsys)["product"]
    manifest = json.loads(
        (Path(product["artifact"]["path"]).parent / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["compression"]["allow_aggressive_compression"] is True
    assert manifest["compression"]["collapse_applied"] is False


def test_check_lists_every_blank_assistant_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A partially filled artifact must report its whole remaining work list."""
    stage = _stage(tmp_path, monkeypatch, capsys)
    assert (
        main(
            ["chatlas", "products", "scaffold", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(["chatlas", "products", "check", "--stage-id", stage["stage_id"], "--json"])
        == 1
    )
    evidence = captured_json(capsys)["check"]["finding"]["evidence"]
    assert evidence["blank_turn_indices"] == [1, 3]
    assert evidence["blank_turn_count"] == 2
