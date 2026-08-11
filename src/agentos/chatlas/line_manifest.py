# $kw: --from Index.Line.Manifest --from Normal.Turn.Ref --note [IMPL] Chatlas enriches the foundation manifest with independently selected dossier relationships and explicitly bounded turn verification --supp ^c20260811-0u
"""Chatlas relationship provider and materializer for Index.Line.Manifest."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

from agentos._core.errors import CliError
from agentos._core.persistence import atomic_write_text
from agentos.index.line_manifest import LINE_MANIFEST_SCHEMA
from agentos.index.model import index_line_anchor_triplet_hash

from ._payload_helpers import compact_text, dict_list, string_or_none
from .anchory import (
    CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
    ChatlasSupportRuntimeCache,
    chatlas_anchory_depot,
    event_neighborhood,
    parse_line_anchor_dossier,
)
from .index_store import ChatlasSessionIndexCache
from .normal_turn import normal_turn_ref, parse_normal_turn_ref
from .normalization.session_model.events import normal_turn_kind
from .paths import INDEX_LINE_MANIFEST_ROOT, default_chatlas_root


LineManifestDetail = Literal["reference", "turn", "context"]
LineManifestVerification = Literal["stored", "sampled", "complete"]
RELATIONSHIP_NAMESPACES = ("support", "gates", "provenance")


def create_chatlas_line_relationship_projector(
    *,
    chatlas_root: Path | None = None,
    relationships: tuple[str, ...] = RELATIONSHIP_NAMESPACES,
    verification: LineManifestVerification = "stored",
    sample_size: int = 2,
    detail: LineManifestDetail = "reference",
    radius: int = 2,
    model_loader: Callable[[str], dict[str, Any]] | None = None,
) -> Callable[[str, str], dict[str, object]]:
    """Return one operation-scoped Chatlas dossier relationship projector."""

    selected_relationships = _relationship_selection(relationships)
    if verification not in {"stored", "sampled", "complete"}:
        raise CliError(f"unsupported line manifest verification: {verification!r}")
    if detail not in {"reference", "turn", "context"}:
        raise CliError(f"unsupported line manifest detail: {detail!r}")
    if sample_size < 1:
        raise CliError("line manifest sample size must be positive")
    if radius < 0:
        raise CliError("line manifest radius must be non-negative")

    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    depot = chatlas_anchory_depot(root)
    runtime_cache = ChatlasSupportRuntimeCache()
    loaded_models: dict[str, dict[str, Any]] = {}
    source_loader = model_loader or _default_model_loader(
        chatlas_root=root,
        index_cache=ChatlasSessionIndexCache(),
    )

    def load_model(identity: str) -> dict[str, Any]:
        if identity not in loaded_models:
            loaded_models[identity] = source_loader(identity)
        return loaded_models[identity]

    def project(anchor: str, line_source: str) -> dict[str, object]:
        resolution = depot.resolve(anchor)
        if resolution is None:
            raise CliError(f"Index line anchor has no Anchory record: {anchor}")
        dossier = parse_line_anchor_dossier(resolution.record)
        stored_hash = dossier["attachment"]["triplet_hash"]
        observed_hash = index_line_anchor_triplet_hash(line_source, anchor)
        projected_relationships: dict[str, Any] = {}
        referenced = _relationship_turn_refs(
            dossier,
            selected_relationships=selected_relationships,
        )
        verify_keys = _verification_keys(
            tuple(referenced),
            verification=verification,
            sample_size=sample_size,
        )
        turns: dict[str, dict[str, Any]] = {}

        if "support" in selected_relationships:
            members = dossier["relationships"]["support"]["members"]
            projected_relationships["support"] = {
                "members": [
                    _project_relationship_turn(
                        member,
                        relationship="support",
                        verify_keys=verify_keys,
                        load_model=load_model,
                        runtime_cache=runtime_cache,
                        turns=turns,
                        detail=detail,
                        radius=radius,
                    )
                    for member in members
                ]
            }
        if "gates" in selected_relationships:
            gates: dict[str, list[dict[str, Any]]] = {}
            for gate_kind, gate_items in dossier["relationships"]["gates"].items():
                projected_items: list[dict[str, Any]] = []
                for gate in gate_items:
                    projected = {
                        key: value
                        for key, value in gate.items()
                        if key not in {"proposal_turn", "approval_turn"}
                    }
                    for position in ("proposal_turn", "approval_turn"):
                        if position in gate:
                            relationship_turn = _project_relationship_turn(
                                gate[position],
                                relationship=f"gates.{gate_kind}.{position}",
                                verify_keys=verify_keys,
                                load_model=load_model,
                                runtime_cache=runtime_cache,
                                turns=turns,
                                detail=detail,
                                radius=radius,
                            )
                            projected[position] = relationship_turn["turn"]
                            projected[f"{position}_verification"] = relationship_turn[
                                "verification"
                            ]
                    projected_items.append(projected)
                gates[gate_kind] = projected_items
            projected_relationships["gates"] = gates
        if "provenance" in selected_relationships:
            projected_relationships["provenance"] = dossier["relationships"][
                "provenance"
            ]

        return {
            "anchor": {
                "anchor": anchor,
                "dossier_schema": CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
                "record_fingerprint": _json_hash(dossier),
                "attachment": {
                    "canonical_schema": dossier["attachment"]["canonical_schema"],
                    "asserted_triplet_hash": stored_hash,
                    "observed_triplet_hash": observed_hash,
                    "standing": "matched" if stored_hash == observed_hash else "amended",
                },
                "relationships": projected_relationships,
            },
            "turns": turns,
            "verified_sessions": sorted(
                {
                    str(entry["ref"]["session"])
                    for entry in turns.values()
                    if entry.get("verification") == "verified"
                }
            ),
        }

    return project


def _relationship_turn_refs(
    dossier: dict[str, Any],
    *,
    selected_relationships: tuple[str, ...],
) -> list[str]:
    keys: list[str] = []
    if "support" in selected_relationships:
        for member in dossier["relationships"]["support"]["members"]:
            keys.append(_turn_key(member))
    if "gates" in selected_relationships:
        for gate_items in dossier["relationships"]["gates"].values():
            for gate in gate_items:
                for position in ("proposal_turn", "approval_turn"):
                    if position in gate:
                        keys.append(_turn_key(gate[position]))
    return list(dict.fromkeys(keys))


def _verification_keys(
    keys: tuple[str, ...],
    *,
    verification: LineManifestVerification,
    sample_size: int,
) -> frozenset[str]:
    if verification == "stored":
        return frozenset()
    if verification == "complete" or sample_size >= len(keys):
        return frozenset(keys)
    if not keys:
        return frozenset()
    if sample_size == 1:
        return frozenset((keys[0],))
    indexes = {
        round(index * (len(keys) - 1) / (sample_size - 1))
        for index in range(sample_size)
    }
    return frozenset(keys[index] for index in sorted(indexes))


def _project_relationship_turn(
    value: object,
    *,
    relationship: str,
    verify_keys: frozenset[str],
    load_model: Callable[[str], dict[str, Any]],
    runtime_cache: ChatlasSupportRuntimeCache,
    turns: dict[str, dict[str, Any]],
    detail: LineManifestDetail,
    radius: int,
) -> dict[str, str]:
    ref = parse_normal_turn_ref(value)
    key = _turn_key(ref)
    should_verify = key in verify_keys
    verification = "verified" if should_verify else "stored"
    if key not in turns or (
        should_verify and turns[key].get("verification") != "verified"
    ):
        entry: dict[str, Any] = {"ref": ref, "verification": verification}
        if should_verify:
            model = load_model(ref["session"])
            events = list(
                runtime_cache.turn_events(ref["session"], model, ref["turn_id"])
            )
            if not events:
                raise CliError(f"turn is unavailable: {key}")
            actual = normal_turn_ref(ref["session"], events)
            if actual["turn_hash"] != ref["turn_hash"] or actual["at"] != ref["at"]:
                raise CliError(f"Normal.Turn.Ref assertion mismatch: {key}")
            kind = normal_turn_kind(events[0])
            if relationship == "support" and kind != "user":
                raise CliError(f"support member is not a User.Turn: {key}")
            entry["kind"] = kind
            if detail in {"turn", "context"}:
                entry["text"] = compact_text(_turn_text(events))
                entry["events"] = events
            if detail == "context":
                entry["context"] = event_neighborhood(
                    model,
                    turn_id=ref["turn_id"],
                    radius=radius,
                )
        turns[key] = entry
    return {"turn": key, "verification": verification}


def _turn_key(value: object) -> str:
    ref = parse_normal_turn_ref(value)
    return f"{ref['session']}:{ref['turn_id']}"


def materialize_index_line_manifest(
    manifest: dict[str, Any], *, chatlas_root: Path | None = None
) -> dict[str, Any]:
    """Atomically write one manifest beneath the ignored Chatlas workspace."""

    if manifest.get("schema") != LINE_MANIFEST_SCHEMA:
        raise CliError(f"materialization requires {LINE_MANIFEST_SCHEMA}")
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    _ensure_workspace_ignored(root)
    output_root = root / INDEX_LINE_MANIFEST_ROOT
    output_root.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    fingerprint = _text_hash(encoded)
    stamp = str(manifest.get("generated_at") or _utc_now()).replace(":", "").replace("-", "")
    stamp = stamp.replace(".", "").replace("+", "").replace("Z", "Z")
    destination = output_root / f"{stamp}-{fingerprint.removeprefix('sha256:')[:12]}.json"
    atomic_write_text(destination, encoded)
    return {
        "schema": "agentos.index-line-manifest-materialization.v3",
        "path": str(destination),
        "manifest_fingerprint": fingerprint,
        "summary": manifest.get("summary", {}),
    }


def _default_model_loader(
    *, chatlas_root: Path, index_cache: ChatlasSessionIndexCache
) -> Callable[[str], dict[str, Any]]:
    from .index_query import select_materialization_row, select_one_chatlas_index_row
    from .views import load_chatlas_session_model

    def load(identity: str) -> dict[str, Any]:
        row = select_one_chatlas_index_row(
            command="index line manifest",
            identity_hash=identity,
            chatlas_root=chatlas_root,
            index_cache=index_cache,
        )
        return load_chatlas_session_model(
            select_materialization_row(row), chatlas_root=chatlas_root
        )

    return load


def _relationship_selection(relationships: tuple[str, ...]) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(relationships or RELATIONSHIP_NAMESPACES))
    unknown = set(selected) - set(RELATIONSHIP_NAMESPACES)
    if unknown:
        raise CliError(
            "unknown line manifest relationship namespace(s): "
            + ", ".join(sorted(unknown))
        )
    return tuple(name for name in RELATIONSHIP_NAMESPACES if name in selected)


def _turn_text(events: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for event in events:
        payload = event.get("payload")
        content = dict_list(payload.get("content")) if isinstance(payload, dict) else []
        texts.extend(
            text
            for item in content
            if (text := string_or_none(item.get("text"))) is not None
        )
    return "\n".join(texts)


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _text_hash(encoded)


def _text_hash(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_workspace_ignored(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    ignore_path = root / ".gitignore"
    entry = "/workspace/"
    existing = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
    if entry in {line.strip() for line in existing.splitlines()}:
        return
    separator = "" if not existing or existing.endswith("\n") else "\n"
    ignore_path.write_text(f"{existing}{separator}{entry}\n", encoding="utf-8")


__all__ = [
    "LineManifestDetail",
    "LineManifestVerification",
    "RELATIONSHIP_NAMESPACES",
    "create_chatlas_line_relationship_projector",
    "materialize_index_line_manifest",
]
