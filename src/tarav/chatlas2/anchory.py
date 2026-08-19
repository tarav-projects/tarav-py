# $kw: ^chatlas2-design-support --from Event.Annotation --from Index.Line.Anchor --from Anchory.System --note [IMPL] the first Chatlas2 consumer route grounds line dossiers in user Chat.Message.Ref assertions inside an isolated namespace and requests models through the canonical provider --supp ^c20260815-7u ^c20260815-40u ^c20260815-42u ^c20260815-46u ^d20260816-13u ^d20260816-17u
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Callable

from tarav._core.errors import CliError
from tarav.anchory import AnchoryDepot
from tarav.chatlas.paths import default_chatlas_root
from tarav.index_model import (
    INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
    index_line_anchor_triplet_hash,
    index_line_statement_parts,
)

from .message_ref import resolve_chat_message_ref
from .messages import (
    chat_message_at,
    chat_message_neighborhood,
    chat_message_support_member,
    list_chat_messages,
)
from .model import JsonObject
from .normal_model import provide_normal_model


CHATLAS2_NAMESPACE = "chatlas2"
CHATLAS2_NAMESPACE_PREFIX = "d"
CHATLAS2_MESSAGE_SUPPORT_SCHEMA = "tarav.chatlas2.message-support.v1"
CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1 = "tarav.chatlas2.line-anchor-dossier.v1"
CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA = "tarav.chatlas2.line-anchor-dossier.v2"
CHATLAS2_ANCHOR_BATCH_SCHEMA = "tarav.chatlas2.anchor-batch.v2"
_FULL_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTENT_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_ANCHOR_KEY = re.compile(r"[a-z][0-9]{8}-[0-9]+[a-z]")
_ISSUE_ID = re.compile(r"Issue\.I[0-9]{4}")
ModelLoader = Callable[[str], JsonObject]


def chatlas2_anchory_depot(chatlas_root: Path | None = None) -> AnchoryDepot:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    return AnchoryDepot(root / "anchory")


def ensure_chatlas2_namespace(depot: AnchoryDepot) -> None:
    meta = depot.namespace_meta(CHATLAS2_NAMESPACE)
    if meta is None:
        depot.write_namespace_meta(
            CHATLAS2_NAMESPACE,
            prefix=CHATLAS2_NAMESPACE_PREFIX,
            intention=(
                "Hugentic grounding records whose chat members are exact "
                "Chatlas2 Chat.Message.Ref assertions"
            ),
            semantics="tarav-chatlas-md/notes/live/527-chatlas2-normal-model-redesign-design-session.md",
        )
        return
    if meta.get("prefix") != CHATLAS2_NAMESPACE_PREFIX:
        raise CliError(
            f"Chatlas2 Anchory namespace prefix is not {CHATLAS2_NAMESPACE_PREFIX!r}"
        )


def format_support_member_ref(member: JsonObject) -> str:
    parsed = _parse_support_member(member)
    return (
        f"{parsed['session']}:{parsed['message_address']}:"
        f"{parsed['message_hash']}"
    )


def parse_support_member_ref(value: str) -> JsonObject:
    if not isinstance(value, str):
        raise CliError("Chatlas2 support member ref must be a string")
    parts = value.rsplit(":", 2)
    if len(parts) != 3 or not all(parts):
        raise CliError(
            "Chatlas2 support member must have the form "
            "<session>:<message-address>:<message-hash>"
        )
    session, address, digest = parts
    _digest(address, field="message_address")
    _digest(digest, field="message_hash")
    return {"session": session, "message_address": address, "message_hash": digest}


def _parse_message_member(value: object) -> JsonObject:
    if not isinstance(value, dict) or set(value) != {
        "session",
        "message_address",
        "message_hash",
        "at",
    }:
        raise CliError(
            "Chatlas2 message member must contain exactly session, "
            "message_address, message_hash, and at"
        )
    session = value.get("session")
    at = value.get("at")
    if not isinstance(session, str) or not session:
        raise CliError("Chatlas2 message member session must be non-empty")
    if not isinstance(at, str) or not at:
        raise CliError("Chatlas2 message member at must be non-empty")
    return {
        "session": session,
        "message_address": _digest(value.get("message_address"), field="message_address"),
        "message_hash": _digest(value.get("message_hash"), field="message_hash"),
        "at": at,
    }


def _parse_support_member(value: object) -> JsonObject:
    return _parse_message_member(value)


def _member_identity(member: JsonObject) -> tuple[str, str, str]:
    return (
        str(member["session"]),
        str(member["message_address"]),
        str(member["message_hash"]),
    )


def _parse_member_list(raw: object, *, field: str) -> list[JsonObject]:
    if not isinstance(raw, list) or not raw:
        raise CliError(f"{field} must be a non-empty list")
    members = [_parse_message_member(member) for member in raw]
    identities = [_member_identity(member) for member in members]
    if len(identities) != len(set(identities)):
        raise CliError(f"{field} repeats a message member")
    return members


def _parse_support_relationship(value: object) -> JsonObject:
    if not isinstance(value, dict) or set(value) != {"members"}:
        raise CliError("Chatlas2 support relationship must contain only members")
    return {
        "members": _parse_member_list(
            value.get("members"), field="relationships.support.members"
        )
    }


def _parse_gate_list(raw: object, *, kind: str) -> list[JsonObject]:
    if not isinstance(raw, list):
        raise CliError(f"Chatlas2 line gate {kind} must be a list")
    parsed: list[JsonObject] = []
    seen: set[str] = set()
    required = {"approval"}
    allowed = {"proposal", "approval"}
    if kind == "tokenized_verbatim_approval":
        required |= {"token", "proposal"}
        allowed |= {"token"}
    for index, value in enumerate(raw):
        if not isinstance(value, dict) or not required.issubset(value) or not set(
            value
        ).issubset(allowed):
            raise CliError(f"Chatlas2 line gate {kind} item {index} has an invalid shape")
        item: JsonObject = {}
        if kind == "tokenized_verbatim_approval":
            token = value.get("token")
            if not isinstance(token, str) or not token:
                raise CliError(f"Chatlas2 line gate {kind} item {index} has no token")
            item["token"] = token
        for position in ("proposal", "approval"):
            if position in value:
                item[position] = _parse_message_member(value[position])
        key = json.dumps(item, sort_keys=True, separators=(",", ":"))
        if key in seen:
            raise CliError(f"Chatlas2 line gate {kind} repeats item {index}")
        seen.add(key)
        parsed.append(item)
    return parsed


def _parse_gates(value: object) -> JsonObject:
    if not isinstance(value, dict) or set(value) != {
        "semantic_approval",
        "tokenized_verbatim_approval",
    }:
        raise CliError(
            "Chatlas2 line dossier gates must contain semantic_approval and "
            "tokenized_verbatim_approval"
        )
    return {
        "semantic_approval": _parse_gate_list(
            value["semantic_approval"], kind="semantic_approval"
        ),
        "tokenized_verbatim_approval": _parse_gate_list(
            value["tokenized_verbatim_approval"],
            kind="tokenized_verbatim_approval",
        ),
    }


def _parse_provenance(value: object) -> JsonObject:
    if not isinstance(value, dict) or set(value) != {
        "predecessor_anchors",
        "issue_context",
    }:
        raise CliError(
            "Chatlas2 line dossier provenance must contain predecessor_anchors "
            "and issue_context"
        )
    predecessors = value["predecessor_anchors"]
    issues = value["issue_context"]
    if not isinstance(predecessors, list) or not all(
        isinstance(item, str) and _ANCHOR_KEY.fullmatch(item) for item in predecessors
    ):
        raise CliError("Chatlas2 predecessor_anchors contains an invalid anchor")
    if len(predecessors) != len(set(predecessors)):
        raise CliError("Chatlas2 predecessor_anchors contains a duplicate")
    if not isinstance(issues, list) or not all(
        isinstance(item, str) and _ISSUE_ID.fullmatch(item) for item in issues
    ):
        raise CliError("Chatlas2 issue_context contains an invalid Issue identity")
    if len(issues) != len(set(issues)):
        raise CliError("Chatlas2 issue_context contains a duplicate")
    return {
        "predecessor_anchors": list(predecessors),
        "issue_context": list(issues),
    }


def _empty_gates() -> JsonObject:
    return {"semantic_approval": [], "tokenized_verbatim_approval": []}


def _empty_provenance() -> JsonObject:
    return {"predecessor_anchors": [], "issue_context": []}


def parse_message_support_record(record: object) -> JsonObject:
    if not isinstance(record, dict) or set(record) != {
        "app",
        "schema",
        "relationships",
    }:
        raise CliError("Chatlas2 message-support record has an invalid top-level shape")
    if record.get("app") != "chatlas2" or record.get("schema") != CHATLAS2_MESSAGE_SUPPORT_SCHEMA:
        raise CliError("Chatlas2 message-support record has an invalid app or schema")
    relationships = record.get("relationships")
    if not isinstance(relationships, dict) or set(relationships) != {"support"}:
        raise CliError("Chatlas2 message-support relationships must contain only support")
    return {
        "app": "chatlas2",
        "schema": CHATLAS2_MESSAGE_SUPPORT_SCHEMA,
        "relationships": {
            "support": _parse_support_relationship(relationships["support"])
        },
    }


def build_message_support_record(*, members: list[JsonObject]) -> JsonObject:
    return parse_message_support_record(
        {
            "app": "chatlas2",
            "schema": CHATLAS2_MESSAGE_SUPPORT_SCHEMA,
            "relationships": {"support": {"members": deepcopy(members)}},
        }
    )


def parse_line_anchor_dossier(record: object) -> JsonObject:
    if not isinstance(record, dict) or set(record) != {
        "app",
        "schema",
        "attachment",
        "relationships",
    }:
        raise CliError("Chatlas2 line dossier has an invalid top-level shape")
    if record.get("app") != "chatlas2":
        raise CliError("Chatlas2 line dossier must have app='chatlas2'")
    schema = record.get("schema")
    if schema not in {
        CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
        CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
    }:
        raise CliError(
            "Chatlas2 line dossier has an unsupported schema"
        )
    attachment = record.get("attachment")
    if not isinstance(attachment, dict) or set(attachment) != {
        "canonical_schema",
        "triplet_hash",
    }:
        raise CliError("Chatlas2 line dossier attachment has an invalid shape")
    if attachment.get("canonical_schema") != INDEX_LINE_ANCHOR_TRIPLET_SCHEMA:
        raise CliError("Chatlas2 line dossier has an invalid canonical attachment schema")
    triplet_hash = attachment.get("triplet_hash")
    if not isinstance(triplet_hash, str) or _CONTENT_HASH.fullmatch(triplet_hash) is None:
        raise CliError("Chatlas2 line dossier has an invalid triplet_hash")
    relationships = record.get("relationships")
    if not isinstance(relationships, dict):
        raise CliError("Chatlas2 line dossier relationships must be an object")
    if schema == CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1:
        if set(relationships) != {"support"}:
            raise CliError("Chatlas2 v1 line dossier relationships are invalid")
        gates = _empty_gates()
        provenance = _empty_provenance()
    else:
        if set(relationships) != {"support", "gates", "provenance"}:
            raise CliError(
                "Chatlas2 line dossier relationships must contain support, gates, "
                "and provenance"
            )
        gates = _parse_gates(relationships["gates"])
        provenance = _parse_provenance(relationships["provenance"])
    support = _parse_support_relationship(relationships.get("support"))
    return {
        "app": "chatlas2",
        "schema": schema,
        "attachment": {
            "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
            "triplet_hash": triplet_hash,
        },
        "relationships": {
            "support": support,
            "gates": gates,
            "provenance": provenance,
        },
    }


def build_line_anchor_dossier(
    *,
    anchor: str,
    line_content: str,
    members: list[JsonObject],
    gates: JsonObject | None = None,
    predecessors: tuple[str, ...] = (),
    issue_context: tuple[str, ...] = (),
) -> JsonObject:
    return parse_line_anchor_dossier(
        {
            "app": "chatlas2",
            "schema": CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
            "attachment": {
                "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
                "triplet_hash": index_line_anchor_triplet_hash(line_content, anchor),
            },
            "relationships": {
                "support": {"members": deepcopy(members)},
                "gates": deepcopy(gates or _empty_gates()),
                "provenance": {
                    "predecessor_anchors": list(predecessors),
                    "issue_context": list(issue_context),
                },
            },
        }
    )


def _model_loader(
    *, chatlas_root: Path | None, model_loader: ModelLoader | None
) -> ModelLoader:
    return model_loader or (
        lambda identity: provide_normal_model(
            identity_hash=identity,
            chatlas_root=chatlas_root,
        )
    )


def _prepare_member_ref(
    value: str,
    *,
    index: int,
    relationship: str,
    expected_side: str | None,
    loader: ModelLoader,
) -> tuple[JsonObject, int]:
    asserted = parse_support_member_ref(value)
    session_ref = str(asserted["session"])
    try:
        model = loader(session_ref)
    except Exception as exc:
        raise CliError(
            f"Chatlas2 {relationship} member {index} session is unavailable: "
            f"{session_ref}"
        ) from exc
    messages = list_chat_messages(model)
    resolution = resolve_chat_message_ref(
        messages,
        {
            "message_address": asserted["message_address"],
            "message_hash": asserted["message_hash"],
        },
    )
    if resolution["standing"] != "MATCHED":
        raise CliError(
            f"Chatlas2 {relationship} member {index} is "
            f"{resolution['standing']}: {value}"
        )
    message = resolution["message"]
    if not isinstance(message, dict):
        raise CliError(f"Chatlas2 {relationship} member {index} has no message")
    side = message.get("side")
    if expected_side is not None and side != expected_side:
        raise CliError(
            f"Chatlas2 {relationship} member {index} must be {expected_side}-side; "
            f"got {side!r}"
        )
    position = next(
        (candidate for candidate, current in enumerate(messages) if current is message),
        -1,
    )
    return chat_message_support_member(model, message), position


def _prepare_members(
    member_refs: tuple[str, ...] | list[str],
    *,
    chatlas_root: Path | None,
    model_loader: ModelLoader | None,
) -> list[JsonObject]:
    if not member_refs:
        raise CliError("Chatlas2 Anchory requires at least one support member")
    loader = _model_loader(chatlas_root=chatlas_root, model_loader=model_loader)
    members: list[JsonObject] = []
    for index, value in enumerate(member_refs):
        member, _position = _prepare_member_ref(
            value,
            index=index,
            relationship="support",
            expected_side="user",
            loader=loader,
        )
        members.append(member)
    identities = [_support_identity(member) for member in members]
    if len(identities) != len(set(identities)):
        raise CliError("Chatlas2 Anchory support members must be unique")
    return members


def _prepare_gates(
    gates: object,
    *,
    chatlas_root: Path | None,
    model_loader: ModelLoader | None,
) -> JsonObject:
    if gates is None:
        return _empty_gates()
    if not isinstance(gates, dict) or not set(gates).issubset(
        {"semantic_approval", "tokenized_verbatim_approval"}
    ):
        raise CliError("Chatlas2 line gates have an invalid shape")
    loader = _model_loader(chatlas_root=chatlas_root, model_loader=model_loader)
    prepared = _empty_gates()
    for kind in ("semantic_approval", "tokenized_verbatim_approval"):
        raw_items = gates.get(kind, [])
        if not isinstance(raw_items, list):
            raise CliError(f"Chatlas2 line gate {kind} must be a list")
        for index, raw in enumerate(raw_items):
            required = {"approval"}
            allowed = {"proposal", "approval"}
            if kind == "tokenized_verbatim_approval":
                required |= {"token", "proposal"}
                allowed |= {"token"}
            if (
                not isinstance(raw, dict)
                or not required.issubset(raw)
                or not set(raw).issubset(allowed)
            ):
                raise CliError(
                    f"Chatlas2 line gate {kind} item {index} has an invalid shape"
                )
            item: JsonObject = {}
            if kind == "tokenized_verbatim_approval":
                token = raw.get("token")
                if not isinstance(token, str) or not token:
                    raise CliError(f"Chatlas2 line gate {kind} item {index} has no token")
                item["token"] = token
            proposal_position: int | None = None
            if "proposal" in raw:
                proposal, proposal_position = _prepare_member_ref(
                    raw["proposal"],
                    index=index,
                    relationship=f"{kind} proposal",
                    expected_side="agent",
                    loader=loader,
                )
                item["proposal"] = proposal
            approval, approval_position = _prepare_member_ref(
                raw["approval"],
                index=index,
                relationship=f"{kind} approval",
                expected_side="user",
                loader=loader,
            )
            item["approval"] = approval
            if proposal_position is not None:
                if proposal["session"] != approval["session"]:
                    raise CliError(
                        f"Chatlas2 line gate {kind} item {index} spans sessions"
                    )
                if proposal_position >= approval_position:
                    raise CliError(
                        f"Chatlas2 line gate {kind} item {index} approval must follow proposal"
                    )
            prepared[kind].append(item)
    return _parse_gates(prepared)


def _support_identity(member: JsonObject) -> tuple[str, str, str]:
    return _member_identity(member)


def _support_key(record: JsonObject) -> tuple[tuple[str, str, str], ...]:
    dossier = _parse_grounding_record(record)
    return tuple(
        _support_identity(member)
        for member in dossier["relationships"]["support"]["members"]
    )


def _relationship_key(record: JsonObject) -> str:
    dossier = parse_line_anchor_dossier(record)
    return json.dumps(
        dossier["relationships"], sort_keys=True, separators=(",", ":")
    )


def _parse_grounding_record(record: object) -> JsonObject:
    if isinstance(record, dict) and record.get("schema") == CHATLAS2_MESSAGE_SUPPORT_SCHEMA:
        return parse_message_support_record(record)
    return parse_line_anchor_dossier(record)


def _equivalent_anchors(
    *,
    record: JsonObject,
    line_content: str,
    chatlas_root: Path | None,
) -> tuple[list[str], list[str]]:
    support_key = _support_key(record)
    relationship_key = _relationship_key(record)
    support_matches: list[str] = []
    exact_matches: list[str] = []
    depot = chatlas2_anchory_depot(chatlas_root)
    for entry in depot.query(namespace=CHATLAS2_NAMESPACE):
        try:
            stored = parse_line_anchor_dossier(entry.record)
        except CliError:
            continue
        if _support_key(entry.record) != support_key:
            continue
        support_matches.append(entry.anchor)
        expected = index_line_anchor_triplet_hash(line_content, entry.anchor)
        if (
            stored["attachment"]["triplet_hash"] == expected
            and _relationship_key(entry.record) == relationship_key
        ):
            exact_matches.append(entry.anchor)
    return sorted(support_matches), sorted(exact_matches)


def _project_member(
    member: JsonObject,
    *,
    model: JsonObject,
    radius: int,
) -> JsonObject:
    ref = {
        "message_address": member["message_address"],
        "message_hash": member["message_hash"],
    }
    resolution = resolve_chat_message_ref(list_chat_messages(model), ref)
    message = resolution["message"]
    current_at = chat_message_at(model, message) if isinstance(message, dict) else None
    projected: JsonObject = {
        "member_ref": format_support_member_ref(member),
        "member": deepcopy(member),
        "standing": resolution["standing"],
        "at_matches": current_at == member["at"] if current_at is not None else None,
        "current_at": current_at,
        "side": message.get("side") if isinstance(message, dict) else None,
        "text": message.get("text") if isinstance(message, dict) else None,
        "neighborhood": chat_message_neighborhood(model, ref, radius=radius),
    }
    return projected


def _project_record(
    record: JsonObject,
    *,
    anchor: str | None,
    action: str,
    chatlas_root: Path | None,
    model_loader: ModelLoader | None,
    radius: int,
) -> JsonObject:
    dossier = _parse_grounding_record(record)
    projected: list[JsonObject] = []
    loader = model_loader or (
        lambda identity: provide_normal_model(
            identity_hash=identity,
            chatlas_root=chatlas_root,
        )
    )
    for member in dossier["relationships"]["support"]["members"]:
        identity = str(member["session"])
        model = loader(identity)
        projected.append(_project_member(member, model=model, radius=radius))
        model = None
    projected_gates: JsonObject = {}
    gates = dossier["relationships"].get("gates")
    if isinstance(gates, dict):
        for kind, items in gates.items():
            projected_items: list[JsonObject] = []
            for item in items:
                projected_item: JsonObject = {
                    key: value
                    for key, value in item.items()
                    if key not in {"proposal", "approval"}
                }
                for position in ("proposal", "approval"):
                    member = item.get(position)
                    if not isinstance(member, dict):
                        continue
                    model = loader(str(member["session"]))
                    projected_item[position] = _project_member(
                        member, model=model, radius=radius
                    )
                    model = None
                projected_items.append(projected_item)
            projected_gates[kind] = projected_items
    return {
        "status": "ok",
        "namespace": CHATLAS2_NAMESPACE,
        "action": action,
        "anchor": anchor,
        "record": dossier,
        "members": projected,
        "gates": projected_gates,
    }


def _message_support_equivalents(
    record: JsonObject, *, chatlas_root: Path | None
) -> list[str]:
    key = _support_key(record)
    matches: list[str] = []
    for entry in chatlas2_anchory_depot(chatlas_root).query(
        namespace=CHATLAS2_NAMESPACE
    ):
        try:
            stored = parse_message_support_record(entry.record)
        except CliError:
            continue
        if _support_key(stored) == key:
            matches.append(entry.anchor)
    return sorted(matches)


def chatlas2_message_support_preview(
    *,
    members: tuple[str, ...],
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
    radius: int = 4,
) -> JsonObject:
    prepared = _prepare_members(
        members, chatlas_root=chatlas_root, model_loader=model_loader
    )
    record = build_message_support_record(members=prepared)
    equivalents = _message_support_equivalents(record, chatlas_root=chatlas_root)
    payload = _project_record(
        record,
        anchor=min(equivalents) if equivalents else None,
        action="reuse" if equivalents else "mint",
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        radius=radius,
    )
    payload["equivalent_anchors"] = equivalents
    return payload


def chatlas2_message_support_register(
    *,
    members: tuple[str, ...],
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
    radius: int = 4,
) -> JsonObject:
    prepared = _prepare_members(
        members, chatlas_root=chatlas_root, model_loader=model_loader
    )
    record = build_message_support_record(members=prepared)
    equivalents = _message_support_equivalents(record, chatlas_root=chatlas_root)
    depot = chatlas2_anchory_depot(chatlas_root)
    ensure_chatlas2_namespace(depot)
    if equivalents:
        anchor = min(equivalents)
        resolution = depot.resolve(anchor, namespace=CHATLAS2_NAMESPACE)
        if resolution is None:
            raise CliError(f"Chatlas2 anchor disappeared during registration: {anchor}")
        record = dict(resolution.record)
        action = "reused"
    else:
        at = _parse_timestamp(str(prepared[0]["at"]))
        entry = depot.register(
            record,
            alloc_prefix=f"{at.year:04d}{at.month:02d}{at.day:02d}",
            tag="u",
            namespace=CHATLAS2_NAMESPACE,
        )
        anchor = entry.anchor
        record = dict(entry.record)
        action = "minted"
    return _project_record(
        record,
        anchor=anchor,
        action=action,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        radius=radius,
    )


def chatlas2_anchory_preview(
    *,
    members: tuple[str, ...],
    line_content: str,
    gates: object = None,
    predecessors: tuple[str, ...] = (),
    issue_context: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
    radius: int = 4,
) -> JsonObject:
    prepared = _prepare_members(
        members,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
    )
    prepared_gates = _prepare_gates(
        gates, chatlas_root=chatlas_root, model_loader=model_loader
    )
    placeholder = build_line_anchor_dossier(
        anchor="d00000000-0u",
        line_content=line_content,
        members=prepared,
        gates=prepared_gates,
        predecessors=predecessors,
        issue_context=issue_context,
    )
    support, exact = _equivalent_anchors(
        record=placeholder,
        line_content=line_content,
        chatlas_root=chatlas_root,
    )
    payload = _project_record(
        placeholder,
        anchor=min(exact) if exact else None,
        action="reuse" if exact else "mint",
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        radius=radius,
    )
    payload["support_equivalent_anchors"] = support
    payload["exact_line_equivalent_anchors"] = exact
    return payload


def chatlas2_anchory_register(
    *,
    members: tuple[str, ...],
    line_content: str,
    gates: object = None,
    predecessors: tuple[str, ...] = (),
    issue_context: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
    radius: int = 4,
) -> JsonObject:
    prepared = _prepare_members(
        members,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
    )
    prepared_gates = _prepare_gates(
        gates, chatlas_root=chatlas_root, model_loader=model_loader
    )
    placeholder = build_line_anchor_dossier(
        anchor="d00000000-0u",
        line_content=line_content,
        members=prepared,
        gates=prepared_gates,
        predecessors=predecessors,
        issue_context=issue_context,
    )
    _support, exact = _equivalent_anchors(
        record=placeholder,
        line_content=line_content,
        chatlas_root=chatlas_root,
    )
    depot = chatlas2_anchory_depot(chatlas_root)
    ensure_chatlas2_namespace(depot)
    if exact:
        anchor = min(exact)
        resolution = depot.resolve(anchor, namespace=CHATLAS2_NAMESPACE)
        if resolution is None:
            raise CliError(f"Chatlas2 anchor disappeared during registration: {anchor}")
        record = dict(resolution.record)
        action = "reused"
    else:
        at = _parse_timestamp(str(prepared[0]["at"]))
        alloc_prefix = f"{at.year:04d}{at.month:02d}{at.day:02d}"
        entry = depot.register_derived(
            lambda anchor: build_line_anchor_dossier(
                anchor=anchor,
                line_content=line_content,
                members=prepared,
                gates=prepared_gates,
                predecessors=predecessors,
                issue_context=issue_context,
            ),
            alloc_prefix=alloc_prefix,
            tag="u",
            namespace=CHATLAS2_NAMESPACE,
        )
        anchor = entry.anchor
        record = dict(entry.record)
        action = "minted"
    return _project_record(
        record,
        anchor=anchor,
        action=action,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        radius=radius,
    )


def chatlas2_anchory_resolve(
    anchor: str,
    *,
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
    radius: int = 4,
) -> JsonObject:
    depot = chatlas2_anchory_depot(chatlas_root)
    resolution = depot.resolve(anchor, namespace=CHATLAS2_NAMESPACE)
    if resolution is None:
        raise CliError(f"Chatlas2 anchor not found in depot {depot.root}: {anchor}")
    return _project_record(
        dict(resolution.record),
        anchor=resolution.anchor,
        action="resolved",
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        radius=radius,
    )


def _parse_batch_items(items: object) -> list[JsonObject]:
    if not isinstance(items, list) or not items:
        raise CliError("Chatlas2 Anchory batch requires a non-empty items list")
    parsed: list[JsonObject] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not {"client_id", "line_content", "members"}.issubset(
            item
        ) or not set(item).issubset(
            {"client_id", "line_content", "members", "gates", "predecessors", "issue_context"}
        ):
            raise CliError(f"Chatlas2 Anchory batch item {index} has an invalid shape")
        client_id = item.get("client_id")
        line_content = item.get("line_content")
        members = item.get("members")
        if not isinstance(client_id, str) or not client_id or client_id in seen:
            raise CliError(f"Chatlas2 Anchory batch item {index} has an invalid client_id")
        if not isinstance(line_content, str) or not line_content:
            raise CliError(f"Chatlas2 Anchory batch item {client_id!r} has no line_content")
        if not isinstance(members, list) or not members or not all(
            isinstance(member, str) and member for member in members
        ):
            raise CliError(f"Chatlas2 Anchory batch item {client_id!r} has invalid members")
        predecessors = item.get("predecessors", [])
        issue_context = item.get("issue_context", [])
        if not isinstance(predecessors, list) or not all(
            isinstance(value, str) for value in predecessors
        ):
            raise CliError(
                f"Chatlas2 Anchory batch item {client_id!r} has invalid predecessors"
            )
        if not isinstance(issue_context, list) or not all(
            isinstance(value, str) for value in issue_context
        ):
            raise CliError(
                f"Chatlas2 Anchory batch item {client_id!r} has invalid issue_context"
            )
        seen.add(client_id)
        parsed.append(
            {
                "client_id": client_id,
                "line_content": line_content,
                "members": list(members),
                "gates": deepcopy(item.get("gates")),
                "predecessors": list(predecessors),
                "issue_context": list(issue_context),
            }
        )
    return parsed


def _batch_plan_key(item: JsonObject, record: JsonObject) -> tuple[object, ...]:
    return (
        *index_line_statement_parts(str(item["line_content"])),
        _relationship_key(record),
    )


def chatlas2_anchory_batch_preview(
    *,
    items: object,
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
) -> JsonObject:
    results: list[JsonObject] = []
    planned: set[tuple[object, ...]] = set()
    mint_count = reuse_count = 0
    for item in _parse_batch_items(items):
        prepared = _prepare_members(
            item["members"],
            chatlas_root=chatlas_root,
            model_loader=model_loader,
        )
        gates = _prepare_gates(
            item["gates"], chatlas_root=chatlas_root, model_loader=model_loader
        )
        placeholder = build_line_anchor_dossier(
            anchor="d00000000-0u",
            line_content=str(item["line_content"]),
            members=prepared,
            gates=gates,
            predecessors=tuple(item["predecessors"]),
            issue_context=tuple(item["issue_context"]),
        )
        _support, exact = _equivalent_anchors(
            record=placeholder,
            line_content=str(item["line_content"]),
            chatlas_root=chatlas_root,
        )
        key = _batch_plan_key(item, placeholder)
        if exact or key in planned:
            action = "reuse"
            reuse_count += 1
        else:
            action = "mint"
            mint_count += 1
            planned.add(key)
        results.append(
            {
                "client_id": item["client_id"],
                "action": action,
                "anchor": min(exact) if exact else None,
            }
        )
    return {
        "status": "ok",
        "schema": CHATLAS2_ANCHOR_BATCH_SCHEMA,
        "mint_count": mint_count,
        "reuse_count": reuse_count,
        "items": results,
    }


def chatlas2_anchory_batch_register(
    *,
    items: object,
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
) -> JsonObject:
    results: list[JsonObject] = []
    minted_count = reused_count = 0
    for item in _parse_batch_items(items):
        result = chatlas2_anchory_register(
            members=item["members"],
            line_content=str(item["line_content"]),
            gates=item["gates"],
            predecessors=tuple(item["predecessors"]),
            issue_context=tuple(item["issue_context"]),
            chatlas_root=chatlas_root,
            model_loader=model_loader,
        )
        if result["action"] == "minted":
            minted_count += 1
        else:
            reused_count += 1
        results.append(
            {
                "client_id": item["client_id"],
                "action": result["action"],
                "anchor": result["anchor"],
                "record": result["record"],
            }
        )
    return {
        "status": "ok",
        "schema": CHATLAS2_ANCHOR_BATCH_SCHEMA,
        "minted_count": minted_count,
        "reused_count": reused_count,
        "items": results,
    }


def load_anchor_batch(path: Path) -> list[JsonObject]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"cannot read Chatlas2 Anchory batch {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != CHATLAS2_ANCHOR_BATCH_SCHEMA:
        raise CliError(
            f"Chatlas2 Anchory batch requires schema {CHATLAS2_ANCHOR_BATCH_SCHEMA!r}"
        )
    if set(payload) != {"schema", "items"}:
        raise CliError("Chatlas2 Anchory batch must contain exactly schema and items")
    return _parse_batch_items(payload["items"])


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CliError(f"Chatlas2 support member has invalid at: {value!r}") from exc


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _FULL_SHA256.fullmatch(value) is None:
        raise CliError(f"Chatlas2 support member {field} must be a SHA-256 digest")
    return value


__all__ = [
    "CHATLAS2_ANCHOR_BATCH_SCHEMA",
    "CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA",
    "CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1",
    "CHATLAS2_MESSAGE_SUPPORT_SCHEMA",
    "CHATLAS2_NAMESPACE",
    "build_line_anchor_dossier",
    "build_message_support_record",
    "chatlas2_anchory_batch_preview",
    "chatlas2_anchory_batch_register",
    "chatlas2_anchory_depot",
    "chatlas2_anchory_preview",
    "chatlas2_anchory_register",
    "chatlas2_anchory_resolve",
    "chatlas2_message_support_preview",
    "chatlas2_message_support_register",
    "ensure_chatlas2_namespace",
    "format_support_member_ref",
    "load_anchor_batch",
    "parse_line_anchor_dossier",
    "parse_message_support_record",
    "parse_support_member_ref",
]
