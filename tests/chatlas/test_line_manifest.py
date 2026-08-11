from __future__ import annotations

from pathlib import Path

from agentos.index.line_manifest import build_index_line_manifest
from agentos.chatlas.anchory import (
    CHATLAS_NAMESPACE,
    build_line_anchor_dossier,
    build_line_relationships,
    chatlas_anchory_depot,
)
from agentos.chatlas.normal_turn import normal_turn_ref
from agentos.chatlas.normalization.session_model.events import compute_event_hash


def _event(sequence: int, *, role: str) -> dict[str, object]:
    event = {
        "annotations": {"normal_turn": {"id": f"turn-{sequence}", "kind": role}},
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "message",
        "timestamp": f"2026-08-09T22:00:{sequence:02d}.000Z",
        "producer": {"type": "human" if role == "user" else "assistant"},
        "surfaces": {"transcript": "visible"},
        "payload": {
            "role": role,
            "content": [{"type": "text", "text": f"{role} event {sequence}"}],
        },
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _fixture(tmp_path: Path) -> tuple[Path, Path, str, dict[str, object]]:
    index_root = tmp_path / "index-depot"
    chapter = index_root / "design" / "100-design.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text(
        "****\n## Example.Concept\n\n"
        "- [DF] neighboring definition\n"
        "- [CT] first line ^c20260809-171u\n"
        "- [PR] second line ^c20260809-172u\n"
        "****\n",
        encoding="utf-8",
    )
    identity = "a" * 64
    user = _event(1, role="user")
    assistant = _event(2, role="assistant")
    model = {
        "chat": {
            "events": [user, assistant],
            "messages": [],
            "model_runs": [],
            "tool_invocations": [],
            "usage": [],
        }
    }
    support_ref = normal_turn_ref(identity, [user])
    gate_ref = normal_turn_ref(identity, [assistant])
    gates = {
        "semantic_approval": [],
        "tokenized_verbatim_approval": [
            {
                "token": "idx-edition:test",
                "proposal_turn": gate_ref,
                "approval_turn": support_ref,
            }
        ],
    }
    depot = chatlas_anchory_depot(tmp_path)
    for anchor, source in (
        ("c20260809-171u", "- [CT] first line ^c20260809-171u"),
        ("c20260809-172u", "- [PR] second line ^c20260809-172u"),
    ):
        depot.register(
            build_line_anchor_dossier(
                anchor=anchor,
                line_content=source,
                relationships=build_line_relationships([support_ref], gates=gates),
            ),
            anchor=anchor,
            namespace=CHATLAS_NAMESPACE,
        )
    return index_root, tmp_path, identity, model


def _projector(
    chatlas_root: Path,
    *,
    verification: str,
    model_loader,
    relationships: tuple[str, ...] = ("support", "gates", "provenance"),
    sample_size: int = 2,
    detail: str = "reference",
):
    from agentos.chatlas.line_manifest import (
        create_chatlas_line_relationship_projector,
    )

    return create_chatlas_line_relationship_projector(
        chatlas_root=chatlas_root,
        relationships=relationships,
        verification=verification,
        sample_size=sample_size,
        detail=detail,
        model_loader=model_loader,
    )


def test_stored_manifest_projects_dossier_without_loading_chats(tmp_path: Path) -> None:
    index_root, chatlas_root, identity, _model = _fixture(tmp_path)

    def forbidden(_session: str):
        raise AssertionError("stored projection must not load a session")

    manifest = build_index_line_manifest(
        depot_root=index_root,
        anchors=("c20260809-171u",),
        neighbors=1,
        relationship_projector=_projector(
            chatlas_root,
            verification="stored",
            model_loader=forbidden,
        ),
        inputs={"verification": "stored", "detail": "reference"},
    )

    assert manifest["schema"] == "agentos.index-line-manifest.v3"
    line = manifest["lines"][0]
    assert line["block"]["path"] == "Example.Concept"
    assert line["context"]["before"][0]["statement"]["body"] == (
        "neighboring definition"
    )
    support_key = f"{identity}:turn-1"
    support = line["anchors"][0]["relationships"]["support"]
    assert support == {
        "members": [{"turn": support_key, "verification": "stored"}]
    }
    assert manifest["turns"][support_key]["verification"] == "stored"
    assert manifest["summary"]["referenced_session_count"] == 1
    assert manifest["summary"]["verified_session_count"] == 0


def test_sampled_manifest_verifies_only_deterministic_member_bound(tmp_path: Path) -> None:
    index_root, chatlas_root, identity, model = _fixture(tmp_path)
    loads: list[str] = []

    def load(session: str) -> dict[str, object]:
        loads.append(session)
        return model

    manifest = build_index_line_manifest(
        depot_root=index_root,
        anchors=("c20260809-171u",),
        relationship_projector=_projector(
            chatlas_root,
            verification="sampled",
            sample_size=1,
            model_loader=load,
        ),
    )

    support_key = f"{identity}:turn-1"
    gate_key = f"{identity}:turn-2"
    assert manifest["turns"][support_key]["verification"] == "verified"
    assert manifest["turns"][support_key]["kind"] == "user"
    assert manifest["turns"][gate_key]["verification"] == "stored"
    assert loads == [identity]
    assert manifest["summary"]["referenced_session_count"] == 1
    assert manifest["summary"]["verified_session_count"] == 1


def test_complete_manifest_verifies_all_and_deduplicates_turns(tmp_path: Path) -> None:
    index_root, chatlas_root, identity, model = _fixture(tmp_path)
    loads: list[str] = []

    manifest = build_index_line_manifest(
        depot_root=index_root,
        anchors=("c20260809-171u", "c20260809-172u"),
        relationship_projector=_projector(
            chatlas_root,
            verification="complete",
            detail="turn",
            model_loader=lambda session: loads.append(session) or model,
        ),
    )

    assert len(manifest["turns"]) == 2
    assert all(turn["verification"] == "verified" for turn in manifest["turns"].values())
    assert manifest["turns"][f"{identity}:turn-1"]["text"] == "user event 1"
    assert loads == [identity]


def test_manifest_preserves_selected_relationship_namespaces(tmp_path: Path) -> None:
    index_root, chatlas_root, _identity, _model = _fixture(tmp_path)
    manifest = build_index_line_manifest(
        depot_root=index_root,
        anchors=("c20260809-171u",),
        relationship_projector=_projector(
            chatlas_root,
            verification="stored",
            relationships=("support", "provenance"),
            model_loader=lambda _session: {},
        ),
    )

    relationships = manifest["lines"][0]["anchors"][0]["relationships"]
    assert set(relationships) == {"support", "provenance"}


def test_line_manifest_materialization_is_volatile_and_ignored(tmp_path: Path) -> None:
    from agentos.chatlas.line_manifest import materialize_index_line_manifest

    manifest = {
        "schema": "agentos.index-line-manifest.v3",
        "generated_at": "2026-08-09T23:00:00Z",
        "summary": {"line_count": 0},
        "lines": [],
        "turns": {},
    }
    result = materialize_index_line_manifest(manifest, chatlas_root=tmp_path)
    path = Path(result["path"])

    assert result["schema"] == "agentos.index-line-manifest-materialization.v3"
    assert path.parent == tmp_path / "workspace" / "index-line-manifests"
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "/workspace/\n"


def test_line_manifest_materialization_rejects_old_schema(tmp_path: Path) -> None:
    import pytest

    from agentos._core.errors import CliError
    from agentos.chatlas.line_manifest import materialize_index_line_manifest

    with pytest.raises(CliError, match="agentos.index-line-manifest.v3"):
        materialize_index_line_manifest(
            {"schema": "agentos.index-line-manifest.v2"},
            chatlas_root=tmp_path,
        )
