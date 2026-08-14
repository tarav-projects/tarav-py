# $kw: --from Chatlas.Anchory --from Index.Line.Anchor --note [IMPL] batch creation mints line-centered dossiers with typed relationship namespaces --supp ^c20260809-170u
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav.index.model import index_line_statement_parts

from ._payload_helpers import parse_event_timestamp, string_or_none
from .anchory import (
    CHATLAS_NAMESPACE,
    ResolvedSupportMember,
    _depot_equivalence_scan,
    _line_relationship_equivalence_key,
    _prepare_support_members,
    build_line_anchor_dossier,
    build_line_relationships,
    chatlas_anchory_depot,
    ensure_chatlas_namespace,
)


ANCHOR_BATCH_SCHEMA = "chatlas.anchor-batch.v2"
_ITEM_FIELDS = {
    "client_id",
    "line_content",
    "members",
    "gates",
    "predecessors",
    "issue_context",
}


class _PreparedItem:
    __slots__ = (
        "client_id",
        "line_content",
        "relationships",
        "resolved",
        "member_refs",
        "line_key",
    )

    def __init__(
        self,
        *,
        client_id: str,
        line_content: str,
        relationships: dict[str, object],
        resolved: list[ResolvedSupportMember],
        member_refs: list[str],
    ) -> None:
        self.client_id = client_id
        self.line_content = line_content
        self.relationships = relationships
        self.resolved = resolved
        self.member_refs = member_refs
        placeholder = build_line_anchor_dossier(
            anchor="c00000000-0u",
            line_content=line_content,
            relationships=relationships,
        )
        line_type, body = index_line_statement_parts(line_content)
        self.line_key = (
            line_type,
            body,
            _line_relationship_equivalence_key(placeholder),
        )

    def dossier(self, anchor: str) -> dict[str, object]:
        return build_line_anchor_dossier(
            anchor=anchor,
            line_content=self.line_content,
            relationships=self.relationships,
        )

    def placeholder(self) -> dict[str, object]:
        return self.dossier("c00000000-0u")


def parse_anchor_batch(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise CliError("chatlas anchory batch input must be a JSON object")
    if payload.get("schema") != ANCHOR_BATCH_SCHEMA:
        raise CliError(
            "chatlas anchory batch input requires schema "
            f"{ANCHOR_BATCH_SCHEMA!r}; got {payload.get('schema')!r}"
        )
    unknown = set(payload) - {"schema", "items"}
    if unknown:
        raise CliError(
            "chatlas anchory batch input has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise CliError("chatlas anchory batch input requires a non-empty items array")

    items: list[dict[str, Any]] = []
    seen_client_ids: set[str] = set()
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise CliError(f"chatlas anchory batch item {index} must be an object")
        item_unknown = set(raw_item) - _ITEM_FIELDS
        if item_unknown:
            raise CliError(
                f"chatlas anchory batch item {index} has unknown fields: "
                + ", ".join(sorted(item_unknown))
            )
        client_id = string_or_none(raw_item.get("client_id"))
        if client_id is None:
            raise CliError(f"chatlas anchory batch item {index} requires client_id")
        if client_id in seen_client_ids:
            raise CliError(f"chatlas anchory batch client_id is duplicated: {client_id!r}")
        seen_client_ids.add(client_id)
        line_content = string_or_none(raw_item.get("line_content"))
        if line_content is None:
            raise CliError(f"chatlas anchory batch item {client_id!r} requires line_content")
        raw_members = raw_item.get("members")
        if not isinstance(raw_members, list) or not raw_members or not all(
            isinstance(member, str) and member for member in raw_members
        ):
            raise CliError(f"chatlas anchory batch item {client_id!r} requires ordered members")
        gates = raw_item.get("gates")
        raw_predecessors = raw_item.get("predecessors", [])
        if not isinstance(raw_predecessors, list) or not all(
            isinstance(value, str) for value in raw_predecessors
        ):
            raise CliError(
                f"chatlas anchory batch item {client_id!r} predecessors must be an array"
            )
        raw_issue_context = raw_item.get("issue_context", [])
        if not isinstance(raw_issue_context, list) or not all(
            isinstance(value, str) for value in raw_issue_context
        ):
            raise CliError(
                f"chatlas anchory batch item {client_id!r} issue_context must be an array"
            )
        items.append(
            {
                "client_id": client_id,
                "line_content": line_content,
                "members": tuple(raw_members),
                "gates": gates,
                "predecessors": tuple(raw_predecessors),
                "issue_context": tuple(raw_issue_context),
            }
        )
    return items


def _prepare_batch(
    items: list[dict[str, Any]], *, chatlas_root: Path | None
) -> list[_PreparedItem]:
    models: dict[str, dict[str, Any]] = {}
    prepared: list[_PreparedItem] = []
    for item in items:
        try:
            members, resolved = _prepare_support_members(
                members=item["members"],
                chatlas_root=chatlas_root,
                models=models,
            )
            relationships = build_line_relationships(
                members,
                gates=item.get("gates"),
                predecessors=item.get("predecessors", ()),
                issue_context=item.get("issue_context", ()),
            )
            prepared.append(
                _PreparedItem(
                    client_id=item["client_id"],
                    line_content=item["line_content"],
                    relationships=relationships,
                    resolved=resolved,
                    member_refs=list(item["members"]),
                )
            )
        except CliError as exc:
            raise CliError(
                f"chatlas anchory batch item {item['client_id']!r} is invalid: {exc}"
            ) from exc
    return prepared


def _scan(item: _PreparedItem, entries, *, chatlas_root: Path | None):
    return _depot_equivalence_scan(
        item.placeholder(),
        chatlas_root=chatlas_root,
        entries=entries,
        line_content=item.line_content,
    )


def _item_payload(
    item: _PreparedItem,
    *,
    support_equivalent: list[str],
    exact_line_equivalent: list[str],
    anchor: str | None,
    action: str,
    record: dict[str, object] | None = None,
    duplicate_of: str | None = None,
) -> dict[str, object]:
    return {
        "client_id": item.client_id,
        "member_refs": item.member_refs,
        "relationships": item.relationships,
        "record": record,
        "support_equivalent_anchors": support_equivalent,
        "exact_line_equivalent_anchors": exact_line_equivalent,
        "anchor": anchor,
        "action": action,
        "duplicate_of": duplicate_of,
    }


def chatlas_anchory_batch_preview(
    *, items: list[dict[str, Any]], chatlas_root: Path | None = None
) -> dict[str, object]:
    prepared = _prepare_batch(items, chatlas_root=chatlas_root)
    entries = list(chatlas_anchory_depot(chatlas_root).query(namespace=CHATLAS_NAMESPACE))
    planned: dict[tuple[object, ...], str] = {}
    payloads: list[dict[str, object]] = []
    mint_count = reuse_count = 0
    for item in prepared:
        support_equivalent, exact = _scan(item, entries, chatlas_root=chatlas_root)
        anchor = min(exact) if exact else None
        duplicate_of = None
        if anchor is not None:
            action = "reuse"
            reuse_count += 1
        elif item.line_key in planned:
            action = "reuse"
            duplicate_of = planned[item.line_key]
            reuse_count += 1
        else:
            action = "mint"
            planned[item.line_key] = item.client_id
            mint_count += 1
        payloads.append(
            _item_payload(
                item,
                support_equivalent=support_equivalent,
                exact_line_equivalent=exact,
                anchor=anchor,
                action=action,
                duplicate_of=duplicate_of,
            )
        )
    return {
        "status": "ok",
        "command": "chatlas anchory batch preview",
        "schema": ANCHOR_BATCH_SCHEMA,
        "item_count": len(payloads),
        "mint_count": mint_count,
        "reuse_count": reuse_count,
        "items": payloads,
    }


def chatlas_anchory_batch_register(
    *, items: list[dict[str, Any]], chatlas_root: Path | None = None
) -> dict[str, object]:
    prepared = _prepare_batch(items, chatlas_root=chatlas_root)
    depot = chatlas_anchory_depot(chatlas_root)
    ensure_chatlas_namespace(depot)
    entries = list(depot.query(namespace=CHATLAS_NAMESPACE))
    minted_in_batch: dict[tuple[object, ...], str] = {}
    payloads: list[dict[str, object]] = []
    minted_count = reused_count = 0
    for item in prepared:
        support_equivalent, exact = _scan(item, entries, chatlas_root=chatlas_root)
        anchor = min(exact) if exact else minted_in_batch.get(item.line_key)
        if anchor is not None:
            resolution = depot.resolve(anchor, namespace=CHATLAS_NAMESPACE)
            if resolution is None:
                raise CliError(f"planned anchor disappeared during batch: {anchor}")
            record = dict(resolution.record)
            action = "reused"
            reused_count += 1
        else:
            primary_at = parse_event_timestamp(item.relationships["support"]["members"][0]["at"])
            if primary_at is None:
                raise CliError("chatlas anchory primary member has an invalid timestamp")
            alloc_prefix = f"{primary_at.year:04d}{primary_at.month:02d}{primary_at.day:02d}"
            entry = depot.register_derived(
                item.dossier,
                alloc_prefix=alloc_prefix,
                tag="u",
                namespace=CHATLAS_NAMESPACE,
            )
            anchor = entry.anchor
            record = dict(entry.record)
            entries.append(entry)
            minted_in_batch[item.line_key] = anchor
            exact = [*exact, anchor]
            support_equivalent = [*support_equivalent, anchor]
            action = "minted"
            minted_count += 1
        payloads.append(
            _item_payload(
                item,
                support_equivalent=support_equivalent,
                exact_line_equivalent=exact,
                anchor=anchor,
                action=action,
                record=record,
            )
        )
    return {
        "status": "ok",
        "command": "chatlas anchory batch register",
        "schema": ANCHOR_BATCH_SCHEMA,
        "item_count": len(payloads),
        "minted_count": minted_count,
        "reused_count": reused_count,
        "items": payloads,
    }


def load_anchor_batch(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"cannot read chatlas anchory batch input: {path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid chatlas anchory batch input JSON: {path}") from exc
    return parse_anchor_batch(payload)


__all__ = [
    "ANCHOR_BATCH_SCHEMA",
    "chatlas_anchory_batch_preview",
    "chatlas_anchory_batch_register",
    "load_anchor_batch",
    "parse_anchor_batch",
]
