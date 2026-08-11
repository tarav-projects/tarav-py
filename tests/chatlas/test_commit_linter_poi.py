from __future__ import annotations

from pathlib import Path

import pytest

from agentos.chatlas.poi import (
    CHATLAS_COMMIT_POI_CODES,
    ChatlasCommitLintError,
)
from agentos.chatlas.products import _lint_zip_transcript_summary_commit


SOURCE = {
    "session": {"identity_hash": "session-1"},
    "turns": [
        {"role": "user", "text": "verbatim user text"},
        {"role": "assistant", "text": "assistant source text"},
    ],
}


@pytest.mark.parametrize(
    ("code", "payload"),
    (
        (
            "Session.Mismatch",
            {
                "session": {"identity_hash": "other"},
                "turns": SOURCE["turns"],
            },
        ),
        (
            "Turn.CountMismatch",
            {
                "session": SOURCE["session"],
                "turns": SOURCE["turns"][:1],
            },
        ),
        (
            "Turn.InvalidObject",
            {
                "session": SOURCE["session"],
                "turns": [*SOURCE["turns"], "not-an-object"],
            },
        ),
        (
            "Turn.RoleMismatch",
            {
                "session": SOURCE["session"],
                "turns": [
                    {"role": "assistant", "text": "verbatim user text"},
                    SOURCE["turns"][1],
                ],
            },
        ),
        (
            "Turn.TextNotString",
            {
                "session": SOURCE["session"],
                "turns": [
                    {"role": "user", "text": 7},
                    SOURCE["turns"][1],
                ],
            },
        ),
        (
            "Turn.UserTextNotVerbatim",
            {
                "session": SOURCE["session"],
                "turns": [
                    {"role": "user", "text": "summarized"},
                    SOURCE["turns"][1],
                ],
            },
        ),
        (
            "Turn.AssistantTextBlank",
            {
                "session": SOURCE["session"],
                "turns": [
                    SOURCE["turns"][0],
                    {"role": "assistant", "text": "   "},
                ],
            },
        ),
    ),
)
def test_commit_linter_refusals_carry_canonical_pois(
    code: str, payload: dict[str, object], tmp_path: Path
) -> None:
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=SOURCE,
            artifact_path=tmp_path / "summary.json",
        )

    error = exc_info.value
    assert error.poi.class_reference.root.id == "agentos-chatlas-pkg"
    assert error.poi.class_reference.address == f"Chatlas.Commit.Linter/{code}"
    assert error.poi.instance_id in str(error)
    assert "Commit.Linter failed" in str(error)


LARGE_SOURCE = {
    "session": {"identity_hash": "session-1"},
    "turns": [
        {"role": "user", "text": "verbatim user text"},
        {"role": "assistant", "text": "x" * 60_000},
    ],
}


def test_compression_floor_refuses_an_uncompressed_summary(tmp_path: Path) -> None:
    payload = {
        "session": LARGE_SOURCE["session"],
        "turns": [
            LARGE_SOURCE["turns"][0],
            {"role": "assistant", "text": "x" * 59_000},
        ],
    }
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=LARGE_SOURCE,
            artifact_path=tmp_path / "summary.json",
        )
    poi = exc_info.value.poi
    assert poi.class_reference.address == "Chatlas.Commit.Linter/Compression.Insufficient"
    assert poi.evidence["retained_ratio"] == pytest.approx(59_000 / 60_000, rel=1e-3)
    assert poi.evidence["longest_assistant_turns"][0]["turn_index"] == 1


def test_compression_floor_passes_a_compressed_summary(tmp_path: Path) -> None:
    payload = {
        "session": LARGE_SOURCE["session"],
        "turns": [
            LARGE_SOURCE["turns"][0],
            {"role": "assistant", "text": "x" * 30_000},
        ],
    }
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=LARGE_SOURCE,
        artifact_path=tmp_path / "summary.json",
    )


def test_compression_floor_ignores_small_sessions(tmp_path: Path) -> None:
    """A short session can be irreducible; the floor must not punish that."""
    payload = {
        "session": SOURCE["session"],
        "turns": [
            SOURCE["turns"][0],
            {"role": "assistant", "text": "assistant source tex"},
        ],
    }
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=SOURCE,
        artifact_path=tmp_path / "summary.json",
    )


def test_compression_floor_can_be_waived(tmp_path: Path) -> None:
    payload = {
        "session": LARGE_SOURCE["session"],
        "turns": [
            LARGE_SOURCE["turns"][0],
            {"role": "assistant", "text": "x" * 59_000},
        ],
    }
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=LARGE_SOURCE,
        artifact_path=tmp_path / "summary.json",
        allow_low_compression=True,
    )


def test_blank_assistant_turns_are_reported_as_one_list(tmp_path: Path) -> None:
    """A partial fill must learn every remaining turn from a single refusal."""
    source = {
        "session": {"identity_hash": "session-1"},
        "turns": [
            {"role": "user", "text": "u0"},
            {"role": "assistant", "text": "a1"},
            {"role": "user", "text": "u2"},
            {"role": "assistant", "text": "a3"},
            {"role": "assistant", "text": "a4"},
        ],
    }
    payload = {
        "session": source["session"],
        "turns": [
            source["turns"][0],
            {"role": "assistant", "text": "filled"},
            source["turns"][2],
            {"role": "assistant", "text": ""},
            {"role": "assistant", "text": "   "},
        ],
    }
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=source,
            artifact_path=tmp_path / "summary.json",
        )
    evidence = exc_info.value.poi.evidence
    assert evidence["blank_turn_indices"] == [3, 4]
    assert evidence["blank_turn_count"] == 2
    assert evidence["turn_index"] == 3


def test_structural_refusals_still_precede_blank_reporting(tmp_path: Path) -> None:
    """A mutated user turn must not be masked by a later blank assistant turn."""
    source = {
        "session": {"identity_hash": "session-1"},
        "turns": [
            {"role": "user", "text": "verbatim"},
            {"role": "assistant", "text": "a1"},
        ],
    }
    payload = {
        "session": source["session"],
        "turns": [
            {"role": "user", "text": "mutated"},
            {"role": "assistant", "text": ""},
        ],
    }
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=source,
            artifact_path=tmp_path / "summary.json",
        )
    assert (
        exc_info.value.poi.class_reference.address
        == "Chatlas.Commit.Linter/Turn.UserTextNotVerbatim"
    )


def test_commit_linter_covers_every_declared_class() -> None:
    assert len(CHATLAS_COMMIT_POI_CODES) == 11


# A plausibly summarized assistant turn against a 12_000-byte source: small
# enough to be real compression, large enough not to trip the loss gates. The
# window tests must fail on the invariant they name, not on a neighbouring one.
COMPRESSED = "s" * 3_600


def _windowed_source(window_count: int, *, chunk: int = 12_000) -> dict[str, object]:
    turns: list[dict[str, object]] = []
    for index in range(window_count):
        turns.append({"role": "user", "text": f"u{index}"})
        turns.append({"role": "assistant", "text": f"{index}" * chunk})
    return {"session": {"identity_hash": "session-1"}, "turns": turns}


def test_window_guard_refuses_an_untouched_region(tmp_path: Path) -> None:
    """A global ratio is satisfiable by crushing one region; this catches that."""
    source = _windowed_source(6)
    turns = []
    for index, turn in enumerate(source["turns"]):
        if turn["role"] != "assistant":
            turns.append(turn)
        elif index < 10:
            turns.append({"role": "assistant", "text": COMPRESSED})
        else:
            turns.append(dict(turn))
    payload = {"session": source["session"], "turns": turns}
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=source,
            artifact_path=tmp_path / "summary.json",
        )
    poi = exc_info.value.poi
    assert poi.class_reference.address == "Chatlas.Commit.Linter/Compression.RegionUntouched"
    windows = poi.evidence["untouched_windows"]
    assert poi.evidence["untouched_window_count"] == len(windows) == 1
    assert windows[0]["first_turn_index"] == 11
    assert windows[0]["retained_ratio"] == 1.0


def test_window_guard_passes_evenly_compressed_work(tmp_path: Path) -> None:
    source = _windowed_source(6)
    payload = {
        "session": source["session"],
        "turns": [
            turn if turn["role"] != "assistant" else {"role": "assistant", "text": "s" * 7_000}
            for turn in source["turns"]
        ],
    }
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=source,
        artifact_path=tmp_path / "summary.json",
    )


def test_window_guard_reports_every_untouched_region(tmp_path: Path) -> None:
    source = _windowed_source(6)
    turns = []
    for index, turn in enumerate(source["turns"]):
        if turn["role"] != "assistant":
            turns.append(turn)
        elif index in (3, 11):
            turns.append(dict(turn))
        else:
            turns.append({"role": "assistant", "text": COMPRESSED})
    payload = {"session": source["session"], "turns": turns}
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=source,
            artifact_path=tmp_path / "summary.json",
        )
    evidence = exc_info.value.poi.evidence
    assert evidence["untouched_window_count"] == 2
    assert [w["first_turn_index"] for w in evidence["untouched_windows"]] == [3, 11]


def test_window_guard_shares_the_low_compression_waiver(tmp_path: Path) -> None:
    source = _windowed_source(6)
    turns = []
    for index, turn in enumerate(source["turns"]):
        if turn["role"] != "assistant":
            turns.append(turn)
        elif index < 10:
            turns.append({"role": "assistant", "text": COMPRESSED})
        else:
            turns.append(dict(turn))
    _lint_zip_transcript_summary_commit(
        {"session": source["session"], "turns": turns},
        source_payload=source,
        artifact_path=tmp_path / "summary.json",
        allow_low_compression=True,
    )


def test_window_guard_ignores_small_sessions(tmp_path: Path) -> None:
    _lint_zip_transcript_summary_commit(
        {
            "session": SOURCE["session"],
            "turns": [SOURCE["turns"][0], {"role": "assistant", "text": "assistant source text"}],
        },
        source_payload=SOURCE,
        artifact_path=tmp_path / "summary.json",
    )


def test_window_guard_tolerates_one_dense_window(tmp_path: Path) -> None:
    """A single incompressible window is normal and must not fail the artifact."""
    source = _windowed_source(10)
    turns = []
    for index, turn in enumerate(source["turns"]):
        if turn["role"] != "assistant":
            turns.append(turn)
        elif index == 3:
            turns.append(dict(turn))
        else:
            turns.append({"role": "assistant", "text": COMPRESSED})
    _lint_zip_transcript_summary_commit(
        {"session": source["session"], "turns": turns},
        source_payload=source,
        artifact_path=tmp_path / "summary.json",
    )


def test_collapse_guard_refuses_a_stub_turn(tmp_path: Path) -> None:
    """The mirror of the floor: a fat artifact is faithful, a stub one is wrong."""
    payload = {
        "session": LARGE_SOURCE["session"],
        "turns": [LARGE_SOURCE["turns"][0], {"role": "assistant", "text": "Yes."}],
    }
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=LARGE_SOURCE,
            artifact_path=tmp_path / "summary.json",
        )
    poi = exc_info.value.poi
    assert poi.class_reference.address == "Chatlas.Commit.Linter/Compression.TurnCollapsed"
    assert poi.evidence["collapsed_turn_indices"] == [1]
    assert poi.evidence["collapsed_turns"][0]["source_text_bytes"] == 60_000
    assert poi.evidence["collapsed_turns"][0]["summary_text_bytes"] == 4


def test_collapse_guard_passes_a_proportionate_summary(tmp_path: Path) -> None:
    payload = {
        "session": LARGE_SOURCE["session"],
        "turns": [LARGE_SOURCE["turns"][0], {"role": "assistant", "text": "x" * 12_000}],
    }
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=LARGE_SOURCE,
        artifact_path=tmp_path / "summary.json",
    )


def test_collapse_guard_ignores_a_short_source_turn(tmp_path: Path) -> None:
    """A one-line source turn summarized to a few words is not loss."""
    source = {
        "session": {"identity_hash": "session-1"},
        "turns": [
            {"role": "user", "text": "u"},
            {"role": "assistant", "text": "x" * 60_000},
            {"role": "user", "text": "u2"},
            {"role": "assistant", "text": "the file is at src/app.py"},
        ],
    }
    payload = {
        "session": source["session"],
        "turns": [
            source["turns"][0],
            {"role": "assistant", "text": "x" * 12_000},
            source["turns"][2],
            {"role": "assistant", "text": "src/app.py"},
        ],
    }
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=source,
        artifact_path=tmp_path / "summary.json",
    )


def test_collapse_guard_reports_every_collapsed_turn(tmp_path: Path) -> None:
    source = _windowed_source(6)
    payload = {
        "session": source["session"],
        "turns": [
            turn if turn["role"] != "assistant" else {"role": "assistant", "text": "ok"}
            for turn in source["turns"]
        ],
    }
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=source,
            artifact_path=tmp_path / "summary.json",
        )
    evidence = exc_info.value.poi.evidence
    assert evidence["collapsed_turn_count"] == 6
    assert evidence["collapsed_turn_indices"] == [1, 3, 5, 7, 9, 11]


def test_collapse_guard_ignores_small_sessions(tmp_path: Path) -> None:
    _lint_zip_transcript_summary_commit(
        {
            "session": SOURCE["session"],
            "turns": [SOURCE["turns"][0], {"role": "assistant", "text": "ok"}],
        },
        source_payload=SOURCE,
        artifact_path=tmp_path / "summary.json",
    )


def test_collapse_guard_takes_its_own_waiver_not_the_floor_waiver(tmp_path: Path) -> None:
    """The two hatches assert opposite things and must not be interchangeable."""
    payload = {
        "session": LARGE_SOURCE["session"],
        "turns": [LARGE_SOURCE["turns"][0], {"role": "assistant", "text": "Yes."}],
    }
    with pytest.raises(ChatlasCommitLintError):
        _lint_zip_transcript_summary_commit(
            payload,
            source_payload=LARGE_SOURCE,
            artifact_path=tmp_path / "summary.json",
            allow_low_compression=True,
        )
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=LARGE_SOURCE,
        artifact_path=tmp_path / "summary.json",
        allow_aggressive_compression=True,
    )


def test_crushed_window_guard_refuses_a_thinly_spread_region(tmp_path: Path) -> None:
    """Loss spread across many turns leaves no single stub; the window sees it."""
    source = _windowed_source(90, chunk=1_000)
    turns = []
    for index, turn in enumerate(source["turns"]):
        if turn["role"] != "assistant":
            turns.append(turn)
        elif index < 60:
            turns.append({"role": "assistant", "text": "s" * 60})
        else:
            turns.append({"role": "assistant", "text": "s" * 400})
    with pytest.raises(ChatlasCommitLintError) as exc_info:
        _lint_zip_transcript_summary_commit(
            {"session": source["session"], "turns": turns},
            source_payload=source,
            artifact_path=tmp_path / "summary.json",
        )
    poi = exc_info.value.poi
    assert poi.class_reference.address == "Chatlas.Commit.Linter/Compression.RegionCrushed"
    assert poi.evidence["crushed_share"] >= 0.15
    assert poi.evidence["crushed_windows"][0]["retained_ratio"] < 0.10


def test_crushed_window_guard_tolerates_one_crushed_window(tmp_path: Path) -> None:
    """Tool output and build logs legitimately compress to almost nothing."""
    source = _windowed_source(10)
    turns = []
    for index, turn in enumerate(source["turns"]):
        if turn["role"] != "assistant":
            turns.append(turn)
        elif index == 3:
            turns.append({"role": "assistant", "text": "s" * 300})
        else:
            turns.append({"role": "assistant", "text": COMPRESSED})
    _lint_zip_transcript_summary_commit(
        {"session": source["session"], "turns": turns},
        source_payload=source,
        artifact_path=tmp_path / "summary.json",
    )


def test_crushed_window_guard_shares_the_aggressive_waiver(tmp_path: Path) -> None:
    source = _windowed_source(90, chunk=1_000)
    turns = [
        turn if turn["role"] != "assistant" else {"role": "assistant", "text": "s" * 60}
        for turn in source["turns"]
    ]
    _lint_zip_transcript_summary_commit(
        {"session": source["session"], "turns": turns},
        source_payload=source,
        artifact_path=tmp_path / "summary.json",
        allow_aggressive_compression=True,
    )
