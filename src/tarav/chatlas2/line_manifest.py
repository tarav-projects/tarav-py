from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from tarav._core.errors import CliError
from tarav.chatlas.line_manifest import create_chatlas_line_relationship_projector
from tarav.index_model import index_line_anchor_triplet_hash

from .anchory import chatlas2_anchory_depot, parse_line_anchor_dossier
from .grounding import resolve_message_member
from .messages import chat_message_neighborhood
from .model import JsonObject
from .normal_model import provide_normal_model


Verification = Literal["stored", "sampled", "complete"]
Detail = Literal["reference", "turn", "context"]
RELATIONSHIPS = ("support", "gates", "provenance")


def _message_key(member: JsonObject) -> str:
    return f"{member['session']}:{member['message_address']}"


def _verification_keys(
    keys: list[str], *, verification: Verification, sample_size: int
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


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def create_chatlas2_line_relationship_projector(
    *,
    chatlas_root: Path | None = None,
    relationships: tuple[str, ...] = RELATIONSHIPS,
    verification: Verification = "stored",
    sample_size: int = 2,
    detail: Detail = "reference",
    radius: int = 2,
    model_loader: Callable[[str], JsonObject] | None = None,
) -> Callable[[str, str], JsonObject]:
    selected = tuple(name for name in RELATIONSHIPS if name in relationships)
    unknown = set(relationships) - set(RELATIONSHIPS)
    if unknown:
        raise CliError(f"unknown Chatlas2 line relationship(s): {sorted(unknown)!r}")
    if verification not in {"stored", "sampled", "complete"}:
        raise CliError(f"unsupported Chatlas2 verification: {verification!r}")
    if sample_size < 1 or radius < 0:
        raise CliError("Chatlas2 manifest bounds must be non-negative and non-zero")
    depot = chatlas2_anchory_depot(chatlas_root)
    load = model_loader or (
        lambda identity: provide_normal_model(
            identity_hash=identity, chatlas_root=chatlas_root
        )
    )

    def project(anchor: str, line_source: str) -> JsonObject:
        resolution = depot.resolve(anchor)
        if resolution is None:
            raise CliError(f"Index line anchor has no Anchory record: {anchor}")
        dossier = parse_line_anchor_dossier(resolution.record)
        relationship_members: list[JsonObject] = []
        if "support" in selected:
            relationship_members.extend(
                dossier["relationships"]["support"]["members"]
            )
        if "gates" in selected:
            for items in dossier["relationships"]["gates"].values():
                for gate in items:
                    relationship_members.extend(
                        gate[position]
                        for position in ("proposal", "approval")
                        if position in gate
                    )
        keys = list(dict.fromkeys(_message_key(member) for member in relationship_members))
        verify = _verification_keys(
            keys, verification=verification, sample_size=sample_size
        )
        messages: JsonObject = {}

        def project_member(member: JsonObject) -> JsonObject:
            key = _message_key(member)
            should_verify = key in verify
            entry: JsonObject = {
                "ref": dict(member),
                "verification": "verified" if should_verify else "stored",
            }
            if should_verify:
                model = load(str(member["session"]))
                resolved = resolve_message_member(member, loader=lambda _identity: model)
                if resolved["standing"] != "MATCHED":
                    raise CliError(f"Chat.Message.Ref assertion mismatch: {key}")
                entry["kind"] = resolved["side"]
                if detail in {"turn", "context"}:
                    entry["text"] = resolved["text"]
                if detail == "context":
                    ref = {
                        "message_address": member["message_address"],
                        "message_hash": member["message_hash"],
                    }
                    entry["context"] = chat_message_neighborhood(
                        model, ref, radius=radius
                    )
            existing = messages.get(key)
            if existing is not None and existing != entry:
                if existing.get("verification") == "verified":
                    return {"message": key, "verification": "verified"}
            messages[key] = entry
            return {"message": key, "verification": entry["verification"]}

        projected_relationships: JsonObject = {}
        if "support" in selected:
            projected_relationships["support"] = {
                "members": [
                    project_member(member)
                    for member in dossier["relationships"]["support"]["members"]
                ]
            }
        if "gates" in selected:
            projected_gates: JsonObject = {}
            for kind, items in dossier["relationships"]["gates"].items():
                projected_items: list[JsonObject] = []
                for gate in items:
                    item = {
                        key: value
                        for key, value in gate.items()
                        if key not in {"proposal", "approval"}
                    }
                    for position in ("proposal", "approval"):
                        if position in gate:
                            projected = project_member(gate[position])
                            item[f"{position}_message"] = projected["message"]
                            item[f"{position}_verification"] = projected[
                                "verification"
                            ]
                    projected_items.append(item)
                projected_gates[kind] = projected_items
            projected_relationships["gates"] = projected_gates
        if "provenance" in selected:
            projected_relationships["provenance"] = dossier["relationships"][
                "provenance"
            ]
        asserted = dossier["attachment"]["triplet_hash"]
        observed = index_line_anchor_triplet_hash(line_source, anchor)
        return {
            "anchor": {
                "anchor": anchor,
                "dossier_schema": dossier["schema"],
                "record_fingerprint": _fingerprint(dossier),
                "attachment": {
                    "canonical_schema": dossier["attachment"]["canonical_schema"],
                    "asserted_triplet_hash": asserted,
                    "observed_triplet_hash": observed,
                    "standing": "matched" if asserted == observed else "amended",
                },
                "relationships": projected_relationships,
            },
            "turns": messages,
            "verified_sessions": sorted(
                {
                    str(entry["ref"]["session"])
                    for entry in messages.values()
                    if entry.get("verification") == "verified"
                }
            ),
        }

    return project


def create_grounding_line_relationship_projector(
    **kwargs,
) -> Callable[[str, str], JsonObject]:
    old = create_chatlas_line_relationship_projector(**kwargs)
    new = create_chatlas2_line_relationship_projector(**kwargs)
    depot = chatlas2_anchory_depot(kwargs.get("chatlas_root"))

    def project(anchor: str, line_source: str) -> JsonObject:
        resolution = depot.resolve(anchor)
        record = resolution.record if resolution is not None else None
        if isinstance(record, dict) and record.get("app") == "chatlas2":
            return new(anchor, line_source)
        return old(anchor, line_source)

    return project


__all__ = [
    "create_chatlas2_line_relationship_projector",
    "create_grounding_line_relationship_projector",
]
