from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main

from ._e2e_helpers import _configure_chatlas, _isolate_chatlas, _write_codex_rollout
from ._helpers import captured_json


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"


def _setup_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    messages: list[tuple[str, str]] | None = None,
) -> tuple[Path, Path]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home
        / "sessions"
        / "2026"
        / "03"
        / "25"
        / f"rollout-{SESSION_ID}.jsonl"
    )
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=messages)
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    return environment.home / "Documents" / "chatlas", rollout


def test_product_missing_stage_commit_and_fresh_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, _rollout = _setup_session(tmp_path, monkeypatch, capsys)

    assert main(["chatlas", "products", "list", "--json"]) == 0
    listed = captured_json(capsys)
    assert listed["products"] == [
        {
            "artifact_filename": "zip-transcript-summary.json",
            "description": "Agent-produced compact transcript preserving every user turn.",
            "input_view": "zip-transcript",
            "name": "zip-transcript-summary",
            "producer": "agentic",
            "producer_reference": (
                "tarav-chatlas-md/skills/tarav-chatlas-pkg/references/"
                "producer-zip-transcript-summary.md"
            ),
        }
    ]

    selector = [
        "--product",
        "zip-transcript-summary",
        "--session-id",
        SESSION_ID,
    ]
    assert main(["chatlas", "products", "status", *selector, "--json"]) == 0
    missing = captured_json(capsys)["product"]
    assert missing["state"] == "production_required"
    assert missing["freshness"] == {"state": "missing"}
    assert "missing" in missing["warning"]

    assert main(["chatlas", "products", "produce", *selector, "--json"]) == 0
    prepared = captured_json(capsys)
    assert "producer-zip-transcript-summary.md" in prepared["prompt"]
    assert "products scaffold --stage-id" in prepared["prompt"]
    assert "products check --stage-id" in prepared["prompt"]
    stage = prepared["stage"]
    input_payload = json.loads(Path(stage["input_path"]).read_text(encoding="utf-8"))
    output_payload = dict(input_payload)
    output_payload["turns"] = [
        {
            **turn,
            "text": "compact assistant summary"
            if turn["role"] == "assistant"
            else turn["text"],
        }
        for turn in input_payload["turns"]
    ]
    Path(stage["output_path"]).write_text(
        json.dumps(output_payload), encoding="utf-8"
    )

    assert (
        main(
            [
                "chatlas",
                "products",
                "commit",
                "--stage-id",
                stage["stage_id"],
                "--json",
            ]
        )
        == 0
    )
    committed = captured_json(capsys)["product"]
    assert committed["state"] == "fresh"
    artifact_path = Path(committed["artifact"]["path"])
    assert artifact_path.is_file()
    assert chatlas_root / "products" / "zip-transcript-summary" in artifact_path.parents
    assert not (chatlas_root / "views").exists()

    before = artifact_path.read_bytes()
    assert main(["chatlas", "products", "get", *selector, "--json"]) == 0
    assert captured_json(capsys)["product"]["state"] == "fresh"
    assert artifact_path.read_bytes() == before


def test_stale_product_warns_without_regeneration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _chatlas_root, rollout = _setup_session(
        tmp_path,
        monkeypatch,
        capsys,
        messages=[("user", "first"), ("assistant", "answer")],
    )
    selector = [
        "--product",
        "zip-transcript-summary",
        "--session-id",
        SESSION_ID,
    ]
    assert main(["chatlas", "products", "produce", *selector, "--json"]) == 0
    prepared = captured_json(capsys)
    stage = prepared["stage"]
    Path(stage["output_path"]).write_bytes(Path(stage["input_path"]).read_bytes())
    assert (
        main(
            ["chatlas", "products", "commit", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    artifact_path = Path(captured_json(capsys)["product"]["artifact"]["path"])
    committed_bytes = artifact_path.read_bytes()

    _write_codex_rollout(
        rollout,
        session_id=SESSION_ID,
        messages=[
            ("user", "first"),
            ("assistant", "answer"),
            ("user", "second"),
            ("assistant", "new answer"),
        ],
    )
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["chatlas", "products", "get", *selector, "--json"]) == 0
    stale = captured_json(capsys)["product"]
    assert stale["state"] == "production_required"
    assert stale["freshness"]["state"] == "stale"
    assert "stale" in stale["warning"]
    assert artifact_path.read_bytes() == committed_bytes


def test_product_definition_prompt_is_a_freshness_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _setup_session(tmp_path, monkeypatch, capsys)
    from tarav.chatlas import products

    reference = tmp_path / "producer.md"
    reference.write_text("first prompt", encoding="utf-8")
    monkeypatch.setattr(products, "_resolve_reference", lambda _path: reference)
    selector = [
        "--product",
        "zip-transcript-summary",
        "--session-id",
        SESSION_ID,
    ]
    assert main(["chatlas", "products", "produce", *selector, "--json"]) == 0
    stage = captured_json(capsys)["stage"]
    Path(stage["output_path"]).write_bytes(Path(stage["input_path"]).read_bytes())
    assert (
        main(
            ["chatlas", "products", "commit", "--stage-id", stage["stage_id"], "--json"]
        )
        == 0
    )
    assert captured_json(capsys)["product"]["state"] == "fresh"

    reference.write_text("changed prompt", encoding="utf-8")
    assert main(["chatlas", "products", "status", *selector, "--explain", "--json"]) == 0
    stale = captured_json(capsys)["product"]
    assert stale["state"] == "production_required"
    assert stale["freshness"]["input_matches"] is True
    assert stale["freshness"]["definition_matches"] is False
