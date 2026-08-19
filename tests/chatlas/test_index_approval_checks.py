"""Index-linter approval checks (Impl.Req 598): Line.Approval + Line.Verbatim.Gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.index.linter import (
    build_linter_config,
    render_linter_json,
    render_linter_text,
    run_linter,
)
from tarav.poi.discovery import discover_poi_catalog
from tarav.testing import TaravTestEnvironment
from tarav.wayfinder import WayfinderReferenceRoot, WayfinderRegistry
from tarav.cli.cli import main
from tarav.chatlas.normal_turn import normal_turn_ref
from tarav.chatlas.normalization.session_model.events import normal_turn_id

from ._helpers import write_chatlas_codex_source, write_text_file


TOKEN = "AXT-amber-otter-42"
LINE_BODY = "- [DC] the decided thing"


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
                "content": [{"type": "input_text", "text": "please add the line"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:03.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                # verbatim proposal: carries both the line body and the token
                "content": [
                    {"type": "output_text", "text": f"Proposed:\n{LINE_BODY} {TOKEN}"}
                ],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:04.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"::approve {TOKEN}"}],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:05.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": f"Late proposal:\n{LINE_BODY} {TOKEN}",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-03-08T01:09:06.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"I saw {TOKEN}"}],
            },
        },
    ]
    write_text_file(path, "\n".join(json.dumps(event) for event in events) + "\n")


@pytest.fixture()
def approval_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
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

    from tarav.chatlas.anchory import chatlas_anchory_depot
    from tarav.chatlas.index_query import (
        select_materialization_row,
        select_one_chatlas_index_row,
    )
    from tarav.chatlas.views import load_chatlas_session_model

    depot = chatlas_anchory_depot()
    session = select_one_chatlas_index_row(
        command="approval fixture", identity_hash=identity_hash
    )
    session = select_materialization_row(session)
    session_model = load_chatlas_session_model(session)
    messages = [
        event
        for event in session_model["chat"]["events"]
        if event.get("kind") == "message"
    ]
    users = [e for e in messages if e["payload"]["role"] == "user"]
    assistants = [e for e in messages if e["payload"]["role"] == "assistant"]
    verbatim_event, approval_event = assistants[0], users[1]

    def ref_for(event):
        turn_id = normal_turn_id(event)
        assert turn_id is not None
        return normal_turn_ref(
            identity_hash,
            [item for item in session_model["chat"]["events"] if normal_turn_id(item) == turn_id],
        )

    ctx = {
        "depot": depot,
        "identity_hash": identity_hash,
        "verbatim_ref": ref_for(verbatim_event),
        "approval_ref": ref_for(approval_event),
        "approval_event": approval_event,
        "first_user_event": users[0],
        "late_verbatim_ref": ref_for(assistants[-1]),
        "token_only_event": users[-1],
        "token_only_ref": ref_for(users[-1]),
        "ref_for": ref_for,
    }

    index_depot = tmp_path / "depot"
    _write(
        index_depot / "000-INDEX.md",
        "# Tarav Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    ctx["index_depot"] = index_depot
    return ctx


def _lint(index_depot: Path, *check_factories, coverage=()):
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(index_depot),),
        index_paths=(),
        appendix_paths=(),
        coverage=coverage,
    )
    return run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=tuple(factory() for factory in check_factories),
        include=tuple(_selector(factory) for factory in check_factories),
    )


def _selector(factory) -> str:
    from tarav.poi import check_selector

    return check_selector(factory().code)


def _register(ctx, anchor: str, *, gates=None, member_event=None) -> None:
    from tarav.chatlas.anchory import bind_support_set_to_index_line

    member_event = member_event or ctx["approval_event"]
    member = ctx["ref_for"](member_event)
    ctx["depot"].register(
        bind_support_set_to_index_line(
            {
                "app": "chatlas",
                "schema": "chatlas.support-set.v3",
                "hint": "approval fixture record",
                "members": [member],
            },
            anchor=anchor,
            line_content=LINE_BODY,
            gates=gates,
        ),
        anchor=anchor,
    )


def _tokenized_gates(ctx, *, token=TOKEN, verbatim=None, approval=None):
    return {
        "semantic_approval": [],
        "tokenized_verbatim_approval": [{
            "token": token,
            "proposal_turn": verbatim or ctx["verbatim_ref"],
            "approval_turn": approval or ctx["approval_ref"],
        }],
    }


def _line(anchor: str) -> str:
    return f"****\n## Example.Concept\n\n{LINE_BODY} ^{anchor}\n****\n"


def test_hidden_by_default_no_findings(approval_setup) -> None:
    from tarav.chatlas.index_checks import (
        chatlas_line_approval_check,
        chatlas_line_verbatim_gate_check,
    )

    ctx = approval_setup
    _register(ctx, "c20260308-0u")  # base support turn, no approval type
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))

    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(ctx["index_depot"]),), index_paths=(), appendix_paths=()
    )
    state = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(
            chatlas_line_approval_check(),
            chatlas_line_verbatim_gate_check(),
        ),
    )
    # default run: both checks default_on=False → they do not run at all.
    assert not [
        f
        for f in state.findings
        if f.code.startswith("Index.Linter/Line.Approval")
        or f.code.startswith("Index.Linter/Line.Verbatim.Gate")
    ]


def test_line_approval_missing_when_only_base_support(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_approval_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u")  # no approval type
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))
    state = _lint(ctx["index_depot"], chatlas_line_approval_check)
    hits = [f for f in state.findings if f.code == "Index.Linter/Line.Approval.Missing"]
    assert len(hits) == 1 and hits[0].severity == "warning"


def test_line_approval_present_with_approval_turn(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_approval_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u", gates=_tokenized_gates(ctx))
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))
    state = _lint(ctx["index_depot"], chatlas_line_approval_check)
    assert not [
        f for f in state.findings if f.code.startswith("Index.Linter/Line.Approval")
    ]


def test_verbatim_gate_unreviewed_without_token(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(
        ctx,
        "c20260308-0u",
        gates={
            "semantic_approval": [{
                "proposal_turn": ctx["verbatim_ref"],
                "approval_turn": ctx["approval_ref"],
            }],
            "tokenized_verbatim_approval": [],
        },
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))
    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    hits = [
        f
        for f in state.findings
        if f.code == "Index.Linter/Line.Verbatim.Gate.Unreviewed"
    ]
    assert len(hits) == 1 and hits[0].severity == "warning"


def test_verbatim_gate_passes_with_verifying_token(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u", gates=_tokenized_gates(ctx))
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))
    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    assert not [
        f
        for f in state.findings
        if f.code.startswith("Index.Linter/Line.Verbatim.Gate")
    ]


def test_verbatim_gate_ignores_case_and_whitespace(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u", gates=_tokenized_gates(ctx))
    materially_equivalent = (
        "****\n## Example.Concept\n\n- [dc] THEDECIDED   THING ^c20260308-0u\n****\n"
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", materially_equivalent)
    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    assert not [
        f
        for f in state.findings
        if f.code.startswith("Index.Linter/Line.Verbatim.Gate")
    ]


def test_verbatim_gate_keeps_non_whitespace_characters_significant(
    approval_setup,
) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u", gates=_tokenized_gates(ctx))
    materially_different = (
        "****\n## Example.Concept\n\n- [DC] the decided-thing ^c20260308-0u\n****\n"
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", materially_different)
    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    hits = [
        f
        for f in state.findings
        if f.code == "Index.Linter/Line.Verbatim.Gate.NoProposal"
    ]
    assert len(hits) == 1 and hits[0].severity == "error"


def test_verbatim_gate_errors_on_wrong_token(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(
        ctx, "c20260308-0u", gates=_tokenized_gates(ctx, token="AXT-not-echoed-99")
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))
    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    hits = [
        f
        for f in state.findings
        if f.code == "Index.Linter/Line.Verbatim.Gate.TokenMismatch"
    ]
    assert len(hits) == 1 and hits[0].severity == "error"


def test_verbatim_gate_requires_explicit_approve_command(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(
        ctx,
        "c20260308-0u",
        member_event=ctx["token_only_event"],
        gates=_tokenized_gates(ctx, approval=ctx["token_only_ref"]),
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))

    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    hits = [
        finding
        for finding in state.findings
        if finding.code == "Index.Linter/Line.Verbatim.Gate.TokenMismatch"
    ]
    assert len(hits) == 1


def test_verbatim_gate_requires_assistant_proposal_role(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(
        ctx,
        "c20260308-0u",
        gates=_tokenized_gates(ctx, verbatim=ctx["token_only_ref"]),
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))

    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    assert any(
        finding.code == "Index.Linter/Line.Verbatim.Gate.RoleMismatch"
        for finding in state.findings
    )


def test_verbatim_gate_requires_proposal_before_approval(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(
        ctx,
        "c20260308-0u",
        gates=_tokenized_gates(ctx, verbatim=ctx["late_verbatim_ref"]),
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))

    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    assert any(
        finding.code == "Index.Linter/Line.Verbatim.Gate.OrderMismatch"
        for finding in state.findings
    )


def test_gate_approval_turn_is_independent_from_support_membership(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_line_verbatim_gate_check

    ctx = approval_setup
    _register(
        ctx,
        "c20260308-0u",
        member_event=ctx["first_user_event"],
        gates=_tokenized_gates(ctx),
    )
    _write(ctx["index_depot"] / "design" / "100-design.md", _line("c20260308-0u"))

    state = _lint(ctx["index_depot"], chatlas_line_verbatim_gate_check)
    assert not [
        finding
        for finding in state.findings
        if finding.code.startswith("Index.Linter/Line.Verbatim.Gate")
    ]


def test_approval_is_line_local_across_multiple_references(approval_setup) -> None:
    from tarav.chatlas.index_checks import (
        chatlas_line_approval_check,
        chatlas_line_verbatim_gate_check,
    )

    ctx = approval_setup
    _register(ctx, "c20260308-0u")
    _register(ctx, "c20260308-1u", gates=_tokenized_gates(ctx))
    _write(
        ctx["index_depot"] / "design" / "100-design.md",
        _line("c20260308-0u").replace(
            "^c20260308-0u",
            "^c20260308-0u ^c20260308-1u",
        ),
    )

    state = _lint(
        ctx["index_depot"],
        chatlas_line_approval_check,
        chatlas_line_verbatim_gate_check,
    )
    assert not [
        finding
        for finding in state.findings
        if finding.code.startswith("Index.Linter/Line.Approval")
        or finding.code.startswith("Index.Linter/Line.Verbatim.Gate")
    ]


def test_block_grounding_requires_resolved_nonempty_support(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_grounding_provenance_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u")
    target = ctx["index_depot"] / "design" / "100-design.md"
    _write(target, _line("c20260308-0u"))

    grounded = _lint(
        ctx["index_depot"],
        chatlas_grounding_provenance_check,
        coverage=("block",),
    )
    grounded_payload = json.loads(render_linter_json(grounded))
    assert grounded_payload["coverage"]["block"] == {"grounded": 1, "total": 1}

    _write(target, _line("c20260308-9u"))
    unresolved = _lint(
        ctx["index_depot"],
        chatlas_grounding_provenance_check,
        coverage=("block",),
    )
    unresolved_payload = json.loads(render_linter_json(unresolved))
    assert unresolved_payload["coverage"]["block"] == {"grounded": 0, "total": 1}
    assert any(
        finding.code == "Index.Linter/Anchor.Unresolvable"
        for finding in unresolved.findings
    )


def test_chatlas_tag_poi_renders_its_index_backed_class(approval_setup) -> None:
    from tarav.chatlas.index_checks import chatlas_grounding_provenance_check

    ctx = approval_setup
    _register(ctx, "c20260308-0u")
    _write(
        ctx["index_depot"] / "design" / "100-design.md",
        _line("c20260308-0a"),
    )
    package = ctx["index_depot"].parent / "tarav-chatlas-pkg"
    _write(
        package / "000-INDEX.md",
        "# Chatlas Index\n\n## poi\n\n"
        "- `poi/100-poi.md` - Index.Linter/Anchor.Chatlas.Tag\n",
    )
    _write(
        package / "poi" / "100-poi.md",
        "****\n\n## Index.Linter/Anchor.Chatlas.Tag\n\n"
        "- [DF] a Chatlas citation key lacks its user-evidence tag\n",
    )
    WayfinderRegistry().register(
        WayfinderReferenceRoot(type="package.skill", id="tarav-chatlas-pkg"),
        package,
    )

    state = _lint(
        ctx["index_depot"],
        chatlas_grounding_provenance_check,
    )
    catalog = discover_poi_catalog()
    payload = json.loads(render_linter_json(state, catalog=catalog))
    text = render_linter_text(state, catalog=catalog)

    group = next(
        item
        for item in payload["poi_classes"]
        if item["reference"]["address"] == "Index.Linter/Anchor.Chatlas.Tag"
    )
    assert group["reference"]["root"]["id"] == "tarav-chatlas-pkg"
    assert group["description"] == (
        "a Chatlas citation key lacks its user-evidence tag"
    )
    assert text.count("a Chatlas citation key lacks its user-evidence tag") == 1
