# $kw: ^test-file-edition-event-refs --from Chatlas.Session.Model.Tests --from Session.Event.Tape --note [CT] durable file-edition POI evidence stores Event.Ref objects with deterministic identity ^c20260728-16u
from __future__ import annotations

from typing import Any

import pytest

from agentos.chatlas.file_edition_pois import (
    FileEditionDetector,
    FileEditionPoi,
    file_edition_pois_from_session_model,
)
from agentos.chatlas.event_ref import event_ref
from agentos.chatlas.normalization.session_model.events import compute_event_hash


def _session_model(
    *events: dict[str, object], provider: str = "codex"
) -> dict[str, Any]:
    return {
        "session": {
            "session_id": "session-123",
            "provider_family": provider,
        },
        "chat": {"events": list(events)},
    }


def _tool_event(
    sequence: int,
    *,
    kind: str,
    tool_name: str | None = None,
    arguments: object = None,
    invocation_ref: str = "tool-1",
    outcome: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if tool_name is not None:
        payload["tool_name"] = tool_name
    if arguments is not None:
        payload["input"] = {"arguments": arguments}
    event: dict[str, object] = {
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": kind,
        "producer": {"type": "assistant"},
        "payload": payload,
        "timestamp": f"2026-07-28T10:00:{sequence:02d}.000Z",
        "tool_invocation_ref": invocation_ref,
    }
    if outcome is not None:
        event["outcome"] = outcome
    event["event_hash"] = compute_event_hash(event)
    return event


@pytest.mark.parametrize("provider", ["codex", "claude-code", "copilot-cli"])
def test_apply_patch_detector_uses_provider_neutral_events(provider: str) -> None:
    patch = """*** Begin Patch
*** Update File: src/alpha.py
@@
-old
+new
*** Add File: src/beta.py
+new
*** End Patch
"""
    model = _session_model(
        _tool_event(
            1,
            kind="tool.call",
            tool_name="apply_patch",
            arguments=patch,
        ),
        _tool_event(
            2,
            kind="tool.result",
            invocation_ref="tool-1",
            outcome="error",
        ),
        provider=provider,
    )

    result = file_edition_pois_from_session_model(model)

    assert result["session"] == "session-123"
    assert result["detectors"] == ["tool.apply_patch", "tool.file-write"]
    events = model["chat"]["events"]
    assert [
        (poi["file"], poi["region"], poi["event_refs"]) for poi in result["pois"]
    ] == [
        ("src/alpha.py", None, [event_ref(events[0]), event_ref(events[1])]),
        ("src/beta.py", None, [event_ref(events[0]), event_ref(events[1])]),
    ]
    assert all(len(poi["poi_id"]) == 10 for poi in result["pois"])


def test_structured_file_write_detector_and_file_filter() -> None:
    model = _session_model(
        _tool_event(
            1,
            kind="tool.call",
            tool_name="Write",
            arguments={"file_path": "/repo/src/alpha.py", "content": "x"},
        ),
        _tool_event(2, kind="tool.result"),
        _tool_event(
            3,
            kind="tool.call",
            tool_name="NotebookEdit",
            arguments={"notebook_path": "/repo/notebooks/demo.ipynb"},
            invocation_ref="tool-2",
        ),
    )

    result = file_edition_pois_from_session_model(
        model,
        file="/repo/src/alpha.py",
    )

    assert result["file"] == "/repo/src/alpha.py"
    assert [poi["file"] for poi in result["pois"]] == ["/repo/src/alpha.py"]
    assert result["pois"][0]["event_refs"] == [
        event_ref(model["chat"]["events"][0]),
        event_ref(model["chat"]["events"][1]),
    ]


def test_absolute_filter_matches_observed_relative_path() -> None:
    model = _session_model(
        _tool_event(
            1,
            kind="tool.call",
            tool_name="Edit",
            arguments={"file_path": "src/alpha.py"},
        ),
    )

    result = file_edition_pois_from_session_model(
        model,
        file="/repo/src/alpha.py",
    )

    assert [poi["file"] for poi in result["pois"]] == ["src/alpha.py"]


def test_detector_stack_is_injectable_and_deduplicated() -> None:
    def detect_marker(
        _session_model: dict[str, Any],
    ) -> list[FileEditionPoi]:
        return [
            FileEditionPoi(
                poi_id="ignored",
                file="marker.txt",
                region=None,
                event_refs=({"event_address": "a" * 64, "event_hash": "9" * 16},),
            ),
            FileEditionPoi(
                poi_id="also-ignored",
                file="marker.txt",
                region=None,
                event_refs=({"event_address": "a" * 64, "event_hash": "9" * 16},),
            ),
        ]

    detector = FileEditionDetector(name="test.marker", detect=detect_marker)

    result = file_edition_pois_from_session_model(
        _session_model(),
        detectors=(detector,),
    )

    assert result == {
        "session": "session-123",
        "file": None,
        "detectors": ["test.marker"],
        "pois": [
            {
                "poi_id": result["pois"][0]["poi_id"],
                "file": "marker.txt",
                "region": None,
                "event_refs": [{"event_address": "a" * 64, "event_hash": "9" * 16}],
            }
        ],
    }


def test_irrelevant_session_returns_no_pois() -> None:
    result = file_edition_pois_from_session_model(
        _session_model(
            {
                "sequence": 1,
                "kind": "message",
                "payload": {"content": "src/alpha.py"},
            }
        )
    )

    assert result == {
        "session": "session-123",
        "file": None,
        "detectors": ["tool.apply_patch", "tool.file-write"],
        "pois": [],
    }


def test_poi_identity_is_scoped_to_the_session() -> None:
    event = _tool_event(
        1,
        kind="tool.call",
        tool_name="Write",
        arguments={"file_path": "src/alpha.py"},
    )
    first = file_edition_pois_from_session_model(_session_model(event))
    second_model = _session_model(event)
    second_model["session"]["session_id"] = "session-456"
    second = file_edition_pois_from_session_model(second_model)

    assert first["pois"][0]["poi_id"] != second["pois"][0]["poi_id"]


def test_limit_caps_deterministically_sorted_pois() -> None:
    model = _session_model(
        _tool_event(
            1,
            kind="tool.call",
            tool_name="Write",
            arguments={"file_path": "src/beta.py"},
        ),
        _tool_event(
            2,
            kind="tool.call",
            tool_name="Write",
            arguments={"file_path": "src/alpha.py"},
            invocation_ref="tool-2",
        ),
    )

    result = file_edition_pois_from_session_model(model, limit=1)

    assert [poi["file"] for poi in result["pois"]] == ["src/alpha.py"]


@pytest.mark.parametrize("limit", [0, -1])
def test_limit_must_be_positive(limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be positive"):
        file_edition_pois_from_session_model(_session_model(), limit=limit)
