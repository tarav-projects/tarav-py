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


SESSION_ID = "019ccafa-7835-7fc3-ac17-0e0a0f675fe5"


def _messages(exchanges: int) -> list[tuple[str, str]]:
    return [
        item
        for exchange in range(exchanges)
        for item in (
            ("user", f"user touched change {exchange:02d}"),
            ("assistant", f"assistant interpreted change {exchange:02d}"),
        )
    ]


def _medium_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[Path, dict[str, object]]:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    rollout = (
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{SESSION_ID}.jsonl"
    )
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=_messages(24))
    _configure_chatlas(environment, codex_home)
    assert main(["chatlas", "index", "update", "--provider", "codex", "--json"]) == 0
    capsys.readouterr()
    chatlas_root = environment.home / "Documents" / "chatlas"
    return chatlas_root, _index_rows(chatlas_root)[0]


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
    _write_codex_rollout(rollout, session_id=SESSION_ID, messages=_messages(exchanges))
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


def _author(
    plan_path: Path,
    *,
    identity_hash: str,
    horizons: list[str],
    shared_line: str | None = None,
) -> dict[str, object]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["delta_edits"] = []
    for index, horizon in enumerate(horizons):
        lines = [
            {
                "content": f"- [CT] Authored change {index} for {horizon}.",
                "support": {
                    "members": [f"{identity_hash}:{horizon}"],
                },
            }
        ]
        if shared_line is not None:
            lines.append(
                {
                    "content": shared_line,
                    "support": {
                        "members": [f"{identity_hash}:{horizons[0]}"],
                    },
                }
            )
        plan["delta_edits"].append(
            {
                "horizon_turn_id": horizon,
                "blocks": [{"concept": "Capture.Plan", "lines": lines}],
            }
        )
    head_lines = [
        {"content": f"- [CT] Authored change {index} for {horizon}."}
        for index, horizon in enumerate(horizons)
    ]
    if shared_line is not None:
        head_lines.append({"content": shared_line})
    plan["head"] = {"blocks": [{"concept": "Capture.Plan", "lines": head_lines}]}
    plan["status"] = "ready"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def _apply(capsys: pytest.CaptureFixture[str], plan: Path, *, expect: int = 0):
    assert main(["chatlas", "chat-index", "apply", "--plan", str(plan), "--json"]) == expect
    return captured_json(capsys)


def _fingerprint(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    stage_name: str = "stage",
    indexes: tuple[int, ...] = (3, 7),
    shared_line: str | None = None,
) -> tuple[Path, dict[str, object], Path, list[str]]:
    chatlas_root, row = _medium_session(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    user_turns = _user_turns(chatlas_root, row)
    horizons = [str(user_turns[index]["turn_ref"]["turn_id"]) for index in indexes]
    plan_path = Path(
        str(_scaffold(capsys, tmp_path / stage_name)["plan_path"])
    )
    _author(
        plan_path,
        identity_hash=identity_hash,
        horizons=horizons,
        shared_line=shared_line,
    )
    return chatlas_root, row, plan_path, horizons


def test_apply_installs_a_complete_valid_surface_in_one_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row, plan_path, horizons = _prepare(
        tmp_path,
        monkeypatch,
        capsys,
        shared_line="- [DC] `Chat.Index.HEAD` presents the current chat model.",
    )
    surface = chatlas_root / "session-index" / str(row["identity_hash"])

    result = _apply(capsys, plan_path)

    assert result["ok"] is True
    assert result["mode"] == "create"
    assert result["installed"]["replaced_existing"] is False
    # Three distinct lines: two per-Delta lines plus one shared line reused
    # across both Deltas, because support decides identity and it is the same.
    assert result["anchors"]["item_count"] == 4
    assert result["anchors"]["minted_count"] == 3
    assert result["anchors"]["reused_count"] == 1
    assert result["audit"]["ok"] is True
    assert result["audit"]["blocking_finding_count"] == 0
    assert result["tail"]["state"] == "current"

    assert sorted(
        str(path.relative_to(surface))
        for path in surface.rglob("*")
        if path.is_file()
    ) == sorted(
        ["HEAD.md", f"deltas/{horizons[0]}.md", f"deltas/{horizons[1]}.md"]
    )
    head = (surface / "HEAD.md").read_text(encoding="utf-8")
    assert head.startswith("# Chat.Index.HEAD\n")
    assert "Evidence.Horizon: `" in head
    delta = (surface / f"deltas/{horizons[0]}.md").read_text(encoding="utf-8")
    assert delta.startswith(f"# Chat.Index.Delta/{horizons[0]} @ ")
    assert "## Capture.Plan" in delta

    # The freshly installed surface is exactly what the public audit accepts.
    assert (
        main(
            ["chatlas", "chat-index", "audit", "--session-id", SESSION_ID, "--json"]
        )
        == 0
    )
    audit = captured_json(capsys)
    assert audit["ok"] is True
    assert audit["counts"]["home_count"] == 3


def test_apply_maintains_a_v2_surface_and_preserves_unedited_deltas_byte_for_byte(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row, plan_path, horizons = _prepare(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    surface = chatlas_root / "session-index" / identity_hash
    _apply(capsys, plan_path)
    untouched = (surface / f"deltas/{horizons[0]}.md").read_bytes()
    # A stray file inside the surface is not part of the Chat.Index; the swap
    # drops it and says so rather than carrying it along.
    (surface / "notes.txt").write_text("unrelated file\n", encoding="utf-8")

    user_turns = _user_turns(chatlas_root, row)
    later = str(user_turns[11]["turn_ref"]["turn_id"])
    second_plan = Path(str(_scaffold(capsys, tmp_path / "stage2")["plan_path"]))
    plan = json.loads(second_plan.read_text(encoding="utf-8"))
    assert plan["chatlas"]["mode"] == "maintain-v2"
    assert plan["chatlas"]["base_surface"]["fingerprint"].startswith("sha256:")
    plan["delta_edits"] = [
        {
            "horizon_turn_id": later,
            "blocks": [
                {
                    "concept": "Capture.Plan",
                    "lines": [
                        {
                            "content": f"- [CT] Authored change 2 for {later}.",
                            "support": {
                                "members": [f"{identity_hash}:{later}"],
                            },
                        }
                    ],
                }
            ],
        }
    ]
    plan["head"] = {
        "blocks": [
            {
                "concept": "Capture.Plan",
                "lines": [
                    {"content": f"- [CT] Authored change 0 for {horizons[0]}."},
                    {"content": f"- [CT] Authored change 2 for {later}."},
                ],
            }
        ]
    }
    plan["status"] = "ready"
    second_plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    result = _apply(capsys, second_plan)

    assert result["ok"] is True
    assert result["mode"] == "maintain-v2"
    assert result["installed"]["replaced_existing"] is True
    assert result["removed_paths"] == ["notes.txt"]
    # The unedited Delta survived untouched; the stray file did not.
    assert (surface / f"deltas/{horizons[0]}.md").read_bytes() == untouched
    assert not (surface / "notes.txt").exists()
    assert sorted(path.stem for path in (surface / "deltas").glob("*.md")) == sorted(
        [horizons[0], horizons[1], later]
    )
    # The HEAD line whose Delta was never edited still resolves to its anchor.
    assert result["audit"]["counts"]["home_count"] == 2


def test_maintain_plan_can_add_a_delta_while_preserving_the_complete_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row, plan_path, _horizons = _prepare(tmp_path, monkeypatch, capsys)
    identity_hash = str(row["identity_hash"])
    surface = chatlas_root / "session-index" / identity_hash
    _apply(capsys, plan_path)
    head_before = (surface / "HEAD.md").read_bytes()

    user_turns = _user_turns(chatlas_root, row)
    later = str(user_turns[11]["turn_ref"]["turn_id"])
    second_plan = Path(str(_scaffold(capsys, tmp_path / "stage2")["plan_path"]))
    plan = json.loads(second_plan.read_text(encoding="utf-8"))
    assert plan["head"] == {"preserve": True, "blocks": []}
    plan["delta_edits"] = [
        {
            "horizon_turn_id": later,
            "blocks": [
                {
                    "concept": "Issue.I0001",
                    "lines": [
                        {
                            "content": "- [PR] Delta-only maintenance line.",
                            "support": {
                                "members": [f"{identity_hash}:{later}"],
                            },
                        }
                    ],
                }
            ],
        }
    ]
    plan["status"] = "ready"
    second_plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    result = _apply(capsys, second_plan)

    assert result["ok"] is True
    assert (surface / "HEAD.md").read_bytes() == head_before
    assert (surface / f"deltas/{later}.md").is_file()


def test_apply_refuses_when_the_surface_changed_since_scaffold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row, plan_path, _horizons = _prepare(tmp_path, monkeypatch, capsys)
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    _apply(capsys, plan_path)
    before = _fingerprint(surface)

    # The plan's envelope still describes the absent base surface.
    assert (
        main(["chatlas", "chat-index", "apply", "--plan", str(plan_path), "--json"])
        == 1
    )
    assert _fingerprint(surface) == before


def test_failure_before_the_swap_leaves_the_prior_surface_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos._core.errors import CliError
    import agentos.chatlas.chat_index_apply as apply_module

    chatlas_root, row, plan_path, _horizons = _prepare(tmp_path, monkeypatch, capsys)
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    _apply(capsys, plan_path)
    before = _fingerprint(surface)
    anchory_before = _fingerprint(chatlas_root / "anchory")

    user_turns = _user_turns(chatlas_root, row)
    later = str(user_turns[15]["turn_ref"]["turn_id"])
    second_plan = Path(str(_scaffold(capsys, tmp_path / "stage2")["plan_path"]))
    _author(
        second_plan,
        identity_hash=str(row["identity_hash"]),
        horizons=[later],
    )

    def boom(model, stage_dir):  # noqa: ANN001 - test double
        raise CliError("injected staged-audit failure")

    with monkeypatch.context() as injected:
        injected.setattr(apply_module, "_audit_stage", boom)
        assert (
            main(
                ["chatlas", "chat-index", "apply", "--plan", str(second_plan), "--json"]
            )
            == 1
        )

    assert _fingerprint(surface) == before
    assert not list((chatlas_root / "session-index").glob(".*stage-*"))
    # Anchory is append-only, so the ensured anchors survive the refusal.
    assert _fingerprint(chatlas_root / "anchory") != anchory_before

    # Retrying the same plan reuses those anchors instead of duplicating them.
    result = _apply(capsys, second_plan)
    assert result["ok"] is True
    assert result["anchors"]["minted_count"] == 0
    assert result["anchors"]["reused_count"] == 1


def test_failure_during_the_swap_restores_the_prior_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row, plan_path, _horizons = _prepare(tmp_path, monkeypatch, capsys)
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    _apply(capsys, plan_path)
    before = _fingerprint(surface)

    user_turns = _user_turns(chatlas_root, row)
    later = str(user_turns[15]["turn_ref"]["turn_id"])
    second_plan = Path(str(_scaffold(capsys, tmp_path / "stage2")["plan_path"]))
    _author(
        second_plan, identity_hash=str(row["identity_hash"]), horizons=[later]
    )

    original_rename = Path.rename
    failed_once: list[bool] = []

    def failing_rename(self, target):  # noqa: ANN001 - test double
        # Fail only the stage-into-place move, so the restore path can run.
        if Path(target).name == surface.name and not failed_once:
            failed_once.append(True)
            raise OSError("injected swap failure")
        return original_rename(self, target)

    with monkeypatch.context() as injected:
        injected.setattr(Path, "rename", failing_rename)
        assert (
            main(
                ["chatlas", "chat-index", "apply", "--plan", str(second_plan), "--json"]
            )
            == 1
        )

    assert failed_once == [True]
    assert surface.is_dir()
    assert _fingerprint(surface) == before


def test_apply_installs_only_the_inspected_prefix_and_reports_the_new_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chatlas_root, row, plan_path, horizons = _prepare(tmp_path, monkeypatch, capsys)
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    inspected = json.loads(plan_path.read_text(encoding="utf-8"))["chatlas"]["source"]

    _grow(tmp_path, capsys, exchanges=26)
    result = _apply(capsys, plan_path)

    assert result["ok"] is True
    assert result["tail"]["state"] == "append-only"
    assert result["tail"]["pending_turn_count"] == 4
    # HEAD never advanced its declared horizon over unseen content.
    head = (surface / "HEAD.md").read_text(encoding="utf-8")
    inspected_horizon = inspected["turn_refs"][-1]["turn_ref"]["turn_id"]
    assert f"Evidence.Horizon: `{inspected_horizon}`" in head
    assert "source-append-only" in [
        finding["code"] for finding in result["audit"]["findings"]
    ]


def test_apply_refuses_a_draft_plan_and_a_held_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentos.chatlas.chat_index_apply import LOCKS_ROOT

    chatlas_root, row, plan_path, _horizons = _prepare(tmp_path, monkeypatch, capsys)
    draft = json.loads(plan_path.read_text(encoding="utf-8"))
    draft["status"] = "draft"
    plan_path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
    assert (
        main(["chatlas", "chat-index", "apply", "--plan", str(plan_path), "--json"])
        == 1
    )

    draft["status"] = "ready"
    plan_path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
    lock = chatlas_root / LOCKS_ROOT / f"{row['identity_hash']}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("{}\n", encoding="utf-8")
    assert (
        main(["chatlas", "chat-index", "apply", "--plan", str(plan_path), "--json"])
        == 1
    )
    assert not (chatlas_root / "session-index" / str(row["identity_hash"])).exists()

    lock.unlink()
    assert _apply(capsys, plan_path)["ok"] is True


def test_medium_chat_workflow_scaffolds_validates_applies_and_audits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The documented capture workflow, end to end, on a medium chat."""
    shared = "- [DC] `Chat.Index.HEAD` presents the current chat model."
    chatlas_root, row, plan_path, horizons = _prepare(
        tmp_path, monkeypatch, capsys, indexes=(3, 7, 11), shared_line=shared
    )
    surface = chatlas_root / "session-index" / str(row["identity_hash"])
    selector = ["--session-id", SESSION_ID]

    assert (
        main(["chatlas", "chat-index", "validate", "--plan", str(plan_path), "--json"])
        == 0
    )
    validation = captured_json(capsys)
    assert validation["ok"] is True
    # Three unique lines plus the shared line repeated in every Delta.
    assert validation["anchor_plan"]["item_count"] == 6
    assert validation["anchor_plan"]["mint_count"] == 4
    assert validation["anchor_plan"]["reuse_count"] == 2

    result = _apply(capsys, plan_path)
    assert result["ok"] is True
    assert result["anchors"]["minted_count"] == 4
    assert result["anchors"]["reused_count"] == 2

    assert main(["chatlas", "chat-index", "audit", *selector, "--json"]) == 0
    audit = captured_json(capsys)
    assert audit["ok"] is True
    assert audit["counts"]["delta_count"] == 3
    assert audit["counts"]["delta_line_count"] == 6
    assert audit["counts"]["head_line_count"] == 4
    assert audit["counts"]["distinct_anchor_count"] == 4
    assert audit["counts"]["resolved_anchor_count"] == 4
    assert audit["counts"]["head_only_line_count"] == 0
    assert audit["findings"] == []

    # The repeated HEAD line resolves to the oldest descriptor-ordered Delta.
    repeated = next(
        home for home in audit["homes"] if home["occurrence_count"] == 3
    )
    assert repeated["home"]["relative_path"] == f"deltas/{horizons[0]}.md"

    assert (
        main(
            ["chatlas", "chat-index", "home", *selector, "--line-content", shared, "--json"]
        )
        == 0
    )
    home = captured_json(capsys)
    assert home["match_count"] == 3
    assert home["home"]["relative_path"] == f"deltas/{horizons[0]}.md"

    # The repeated line keeps one anchor across every Delta it is attached to.
    anchors = {
        line.rsplit("^", 1)[1].strip()
        for path in (surface / "deltas").iterdir()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(shared)
    }
    head_anchor = next(
        line.rsplit("^", 1)[1].strip()
        for line in (surface / "HEAD.md").read_text(encoding="utf-8").splitlines()
        if line.startswith(shared)
    )
    assert anchors == {head_anchor}

