from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.index.linter import build_linter_config, run_linter
from tarav.testing import TaravTestEnvironment
from tarav.cli.cli import main
from tarav.chatlas.normal_turn import normal_turn_ref
from tarav.chatlas.normalization.session_model.events import normal_turn_id

from ._helpers import write_chatlas_codex_source, write_text_file


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rollout(path: Path, *, session_id: str) -> None:
    events = [
        {
            "timestamp": "2026-03-08T01:08:59.089Z",
            "type": "session_meta",
            "payload": {"id": session_id, "originator": "codex_cli_rs", "cwd": "/tmp"},
        },
        {
            "timestamp": "2026-03-08T01:09:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "user decision turn"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:03.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "assistant proposal turn"}],
            },
        },
    ]
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


@pytest.fixture()
def provenance_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.chdir(tmp_path)
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675aa1"
    _rollout(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
    )
    write_chatlas_codex_source(environment, codex_home)
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
    assert (
        main(
            ["chatlas", "query", "--session-id", session_id, "--field", "identity_hash", "--json"]
        )
        == 0
    )
    identity_hash = capsys.readouterr().out.strip().splitlines()[-1]

    from tarav.chatlas.anchory import (
        bind_support_set_to_index_line,
        chatlas_anchory_depot,
    )
    from tarav.chatlas.index_query import (
        select_materialization_row,
        select_one_chatlas_index_row,
    )
    from tarav.chatlas.views import load_chatlas_session_model

    depot = chatlas_anchory_depot()
    session = select_one_chatlas_index_row(
        command="test provenance fixture",
        identity_hash=identity_hash,
    )
    session = select_materialization_row(session)
    session_model = load_chatlas_session_model(session)
    events = session_model["chat"]["events"]
    user_event = next(
        event
        for event in events
        if event.get("kind") == "message"
        and event.get("payload", {}).get("role") == "user"
    )
    user_turn_id = normal_turn_id(user_event)
    assert user_turn_id is not None
    user_member = normal_turn_ref(
        identity_hash,
        [event for event in events if normal_turn_id(event) == user_turn_id],
    )
    generic_record = {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "user turn",
            "members": [user_member],
        }
    depot.register(
        bind_support_set_to_index_line(
            generic_record,
            anchor="c20260308-0u",
            line_content="- [DC] decided thing",
        ),
        anchor="c20260308-0u",
    )
    canonical_record = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "user turn with a canonical key",
        "members": [user_member],
    }
    depot.register(
        bind_support_set_to_index_line(
            canonical_record,
            anchor="c20260308-3u",
            line_content="- [DC] repeated thing",
        ),
        anchor="c20260308-3u",
    )
    depot.register(
        bind_support_set_to_index_line(
            canonical_record,
            anchor="c20260308-4u",
            line_content="- [DC] repeated thing",
        ),
        anchor="c20260308-4u",
    )
    depot.register(
        {
            "app": "chatlas",
            "session": identity_hash,
            "at": "2026-03-08T01:09:03Z",
            "hint": "legacy turn",
        },
        anchor="c20260308-1u",
    )
    depot.register(
        {"app": "other-app", "data": "not chat"},
        anchor="c20260308-2",
    )

    index_depot = tmp_path / "depot"
    _write(
        index_depot / "000-INDEX.md",
        "# Tarav Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    return index_depot


def _lint(index_depot: Path):
    from tarav.chatlas.index_checks import chatlas_grounding_provenance_check

    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(index_depot),), index_paths=(), appendix_paths=()
    )
    return run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(chatlas_grounding_provenance_check(),),
    )


def test_provenance_user_anchor_passes(provenance_setup: Path) -> None:
    _write(
        provenance_setup / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [DC] decided thing ^c20260308-0u\n****\n",
    )
    state = _lint(provenance_setup)
    assert not [f for f in state.findings if f.code.startswith("Index.Linter/Anchor")]


def test_line_drift_check_compares_v4_subject_to_current_content(
    provenance_setup: Path,
) -> None:
    from tarav.chatlas.anchory import (
        CHATLAS_NAMESPACE,
        bind_support_set_to_index_line,
        chatlas_anchory_depot,
    )
    from tarav.chatlas.index_checks import chatlas_anchor_line_drift_check

    depot = chatlas_anchory_depot()
    source = depot.resolve("c20260308-0u")
    assert source is not None
    depot.register(
        bind_support_set_to_index_line(
            source.record,
            line_content="- [DC] stable content",
            anchor="c20260308-5u",
            predecessors=("c20260308-0u",),
        ),
        anchor="c20260308-5u",
        namespace=CHATLAS_NAMESPACE,
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(provenance_setup),), index_paths=(), appendix_paths=()
    )

    _write(
        provenance_setup / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [DC] stable content ^c20260308-5u\n****\n",
    )
    matching = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(chatlas_anchor_line_drift_check(),),
    )
    assert not [
        finding
        for finding in matching.findings
        if finding.code == "Index.Linter/Anchor.LineDrift"
    ]

    _write(
        provenance_setup / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [DC] changed content ^c20260308-5u\n****\n",
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(provenance_setup),), index_paths=(), appendix_paths=()
    )
    drifted = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(chatlas_anchor_line_drift_check(),),
    )
    hits = [
        finding
        for finding in drifted.findings
        if finding.code == "Index.Linter/Anchor.LineDrift"
    ]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert hits[0].details["anchor"] == "c20260308-5u"


def test_provenance_validates_repeated_anchor_once_per_lint(
    provenance_setup: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tarav.chatlas.index_checks as checks

    _write(
        provenance_setup / "design" / "100-design.md",
        (
            "****\n## Example.Concept\n\n"
            "- [DC] first claim ^c20260308-0u\n"
            "- [CT] second claim ^c20260308-0u\n"
            "****\n"
        ),
    )
    original_resolve = checks.resolve_support_set_record
    calls = 0

    def counted_resolve(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_resolve(*args, **kwargs)

    monkeypatch.setattr(checks, "resolve_support_set_record", counted_resolve)

    state = _lint(provenance_setup)

    assert not [
        finding
        for finding in state.findings
        if finding.code.startswith("Index.Linter/Anchor")
        and finding.code != "Index.Linter/Anchor.Collision"
    ]
    assert any(
        finding.code == "Index.Linter/Anchor.Collision" for finding in state.findings
    )
    assert calls == 1


def test_provenance_chatlas_anchor_requires_user_tag(
    provenance_setup: Path,
) -> None:
    _write(
        provenance_setup / "design" / "100-design.md",
        (
            "****\n## Example.Concept\n\n"
            "- [DC] stale assistant tag ^c20260308-3a\n"
            "- [DC] missing tag ^c20260308-4\n"
            "****\n"
        ),
    )
    state = _lint(provenance_setup)
    hits = [
        finding
        for finding in state.findings
        if finding.code == "Index.Linter/Anchor.Chatlas.Tag"
    ]
    assert len(hits) == 2
    assert all(finding.severity == "error" for finding in hits)


def test_provenance_unresolvable_anchor_errors(provenance_setup: Path) -> None:
    _write(
        provenance_setup / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [DC] decided thing ^20990101-0\n****\n",
    )
    state = _lint(provenance_setup)
    hits = [f for f in state.findings if f.code == "Index.Linter/Anchor.Unresolvable"]
    assert len(hits) == 1 and hits[0].severity == "error"


def test_provenance_legacy_record_errors(provenance_setup: Path) -> None:
    _write(
        provenance_setup / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [DC] decided thing ^c20260308-1u\n****\n",
    )
    state = _lint(provenance_setup)
    hits = [f for f in state.findings if f.code == "Index.Linter/Anchor.Turn.Missing"]
    assert len(hits) == 1 and "Line.Anchor.Dossier" in hits[0].message


def test_provenance_as_marker_on_user_landing_warns(provenance_setup: Path) -> None:
    _write(
        provenance_setup / "agendix" / "Example.Concept-agendix.md",
        "****\n## Example.Concept/Agendix\n\n- [AS:CT] captured claim ^c20260308-0u\n****\n",
    )
    state = _lint(provenance_setup)
    hits = [
        f
        for f in state.findings
        if f.code == "Index.Linter/Anchor.Provenance.StaleMarker"
    ]
    assert len(hits) == 1 and hits[0].severity == "warning"


def test_provenance_non_chatlas_record_skipped(provenance_setup: Path) -> None:
    _write(
        provenance_setup / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- [DC] other app anchor ^c20260308-2\n****\n",
    )
    state = _lint(provenance_setup)
    assert not [f for f in state.findings if f.code.startswith("Index.Linter/Anchor")]


def test_provenance_gates_blocked_without_depot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    from tarav.chatlas.index_checks import chatlas_grounding_provenance_check

    index_depot = tmp_path / "depot"
    _write(
        index_depot / "000-INDEX.md",
        "# Tarav Index\n\n## design\n\n- `design/100-design.md` — X.Y\n",
    )
    _write(
        index_depot / "design" / "100-design.md",
        "****\n## X.Y\n\n- [DF] `X.Y` is x\n****\n",
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(index_depot),), index_paths=(), appendix_paths=()
    )
    state = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(chatlas_grounding_provenance_check(),),
    )
    assert any(
        r.code == "Index.Linter/Grounding.Provenance" and r.status == "blocked"
        for r in state.check_results
    )
