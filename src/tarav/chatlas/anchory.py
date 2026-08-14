# $kw: ^chatlas-anchory-amend-validation --from Chatlas.Anchory --from Index.Line --from Anchory.System --from Touched.Support.Network --note [CT] Chatlas validates resolvability and immutable line-bound support meaning inside generic Anchory amendment --note [CT] Chatlas resolves source-extracted anchors into unique support sessions for Project.Support.Chats --supp ^c20260730-33u --supp progressive detail refactor ^c20260731-37u --supp line-bound support authorized ^c20260802-103u --supp implementation authorized ^c20260803-2u
from __future__ import annotations

from collections import OrderedDict
from collections import Counter
from copy import deepcopy
import json
from dataclasses import dataclass
from pathlib import Path
import re
from statistics import fmean, pstdev
from typing import Any, Callable, Literal

from tarav._core.errors import CliError
from tarav.anchory import AnchoryDepot, scan_anchory_source
from tarav.index.model import (
    INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
    group_index_line_anchor_occurrences,
    index_line_anchor_triplet_hash,
    normalize_anchor,
    parse_depot,
)

from ._payload_helpers import (
    compact_text,
    dict_list,
    parse_event_timestamp,
    string_or_none,
)
from .normal_turn import normal_turn_ref, parse_normal_turn_ref
from .normalization.session_model.events import normal_turn_id, normal_turn_kind
from .paths import default_chatlas_root


CHATLAS_NAMESPACE = "chatlas"
CHATLAS_NS_PREFIX = "c"
CHATLAS_SUPPORT_SET_SCHEMA = "chatlas.support-set.v3"
CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA = "chatlas.line-anchor-dossier.v1"
USER_TURN_TAG = "u"
AnchoryDetail = Literal["summary", "turn", "context"]

_RECORD_FIELDS = {
    CHATLAS_SUPPORT_SET_SCHEMA: {"app", "schema", "hint", "members"},
    CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA: {
        "app",
        "schema",
        "attachment",
        "relationships",
    },
}
LINE_BOUND_SCHEMAS = frozenset({CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA})
_MEMBER_FIELDS = {"session", "turn_id", "turn_hash", "at", "types"}
_DOSSIER_MEMBER_FIELDS = {"session", "turn_id", "turn_hash", "at"}
_ATTACHMENT_FIELDS = {"canonical_schema", "triplet_hash"}
_RELATIONSHIP_FIELDS = {"support", "gates", "provenance"}
_SUPPORT_FIELDS = {"members"}
_GATE_FIELDS = {"semantic_approval", "tokenized_verbatim_approval"}
_PROVENANCE_FIELDS = {"predecessor_anchors", "issue_context"}
_SEMANTIC_APPROVAL_FIELDS = {"approval_turn", "proposal_turn"}
_TOKENIZED_APPROVAL_FIELDS = {"token", "proposal_turn", "approval_turn"}
_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ANCHOR_KEY_RE = re.compile(r"^[a-z]?\d{8}-\d+[a-z]?$", re.ASCII)
_ISSUE_ID_RE = re.compile(r"^Issue\.I[0-9]{4}$")


@dataclass(frozen=True)
class ResolvedSupportMember:
    member: dict[str, Any]
    session_model: dict[str, Any]
    event: dict[str, Any]


@dataclass(frozen=True)
class _CachedTurnIndex:
    session_model: dict[str, Any]
    turns: dict[str, tuple[dict[str, Any], ...]]


class ChatlasSupportRuntimeCache:
    """Bounded turn indexes derived from authoritative session models."""

    def __init__(self, *, capacity: int = 64) -> None:
        if capacity < 0:
            raise ValueError("Chatlas support cache capacity must be non-negative")
        self.capacity = capacity
        self._sessions: OrderedDict[str, _CachedTurnIndex] = OrderedDict()

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    def turn_events(
        self,
        session_identity: str,
        session_model: dict[str, Any],
        turn_id: str,
    ) -> tuple[dict[str, Any], ...]:
        cached = self._sessions.pop(session_identity, None)
        if cached is None or cached.session_model is not session_model:
            cached = _CachedTurnIndex(
                session_model=session_model,
                turns=_turn_index(session_model),
            )
        if self.capacity:
            self._sessions[session_identity] = cached
            while len(self._sessions) > self.capacity:
                self._sessions.popitem(last=False)
        return cached.turns.get(turn_id, ())


def chatlas_anchory_depot(chatlas_root: Path | None = None) -> AnchoryDepot:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    return AnchoryDepot(root / "anchory")


def ensure_chatlas_namespace(depot: AnchoryDepot) -> None:
    if depot.namespace_meta(CHATLAS_NAMESPACE) is None:
        depot.write_namespace_meta(
            CHATLAS_NAMESPACE,
            prefix=CHATLAS_NS_PREFIX,
            intention=(
                "anchors into Chatlas generic support records or Index-line relationship "
                "dossiers; support members are exact user turns verified by Normal.Turn.Ref"
            ),
            semantics="tarav-chatlas-md/skills/tarav-chatlas-pkg",
        )


def chatlas_anchory_stats(*, chatlas_root: Path | None = None) -> dict[str, object]:
    member_counts = [
        _support_set_member_count(entry.record)
        for entry in chatlas_anchory_depot(chatlas_root).query(
            namespace=CHATLAS_NAMESPACE
        )
    ]
    distribution = Counter(member_counts)
    if not member_counts:
        return {
            "anchor_count": 0,
            "support_turn_count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "population_stddev": None,
            "distribution": {},
        }
    return {
        "anchor_count": len(member_counts),
        "support_turn_count": sum(member_counts),
        "min": min(member_counts),
        "max": max(member_counts),
        "mean": fmean(member_counts),
        "population_stddev": pstdev(member_counts),
        "distribution": {
            str(member_count): distribution[member_count]
            for member_count in sorted(distribution)
        },
    }


def chatlas_anchory_sessions(
    *,
    sources: tuple[str | Path, ...],
    regex: str,
    glob: str = "*.md",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Resolve anchors extracted from source files into unique Chatlas sessions."""
    from .index_store import load_chatlas_session_index_rows

    if not sources:
        raise CliError("chatlas anchory sessions requires at least one source")
    if not glob:
        raise CliError("chatlas anchory sessions glob must be non-empty")

    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    files = _chatlas_anchory_source_files(sources, glob=glob)
    occurrences_by_anchor: dict[str, list[dict[str, object]]] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CliError(f"cannot read anchory source {path}: {exc}") from exc
        for match in scan_anchory_source(text, regex):
            occurrences_by_anchor.setdefault(match.anchor, []).append(
                {
                    "path": str(path),
                    "line": match.line,
                    "column": match.column,
                }
            )

    index = load_chatlas_session_index_rows(chatlas_root=root)
    rows_by_identity = {
        identity: row
        for row in index.rows
        if isinstance(identity := row.get("identity_hash"), str) and identity
    }
    depot = chatlas_anchory_depot(root)
    anchors: list[dict[str, object]] = []
    findings: list[dict[str, object]] = []
    sessions: dict[str, dict[str, object]] = {}
    resolved_anchor_count = 0

    for anchor in sorted(occurrences_by_anchor):
        occurrences = occurrences_by_anchor[anchor]
        resolution = depot.resolve(anchor, namespace=CHATLAS_NAMESPACE)
        if resolution is None:
            findings.append(
                {
                    "kind": "unresolved_anchor",
                    "anchor": anchor,
                    "occurrences": occurrences,
                }
            )
            anchors.append(
                {
                    "anchor": anchor,
                    "status": "unresolved",
                    "occurrences": occurrences,
                }
            )
            continue

        try:
            members = parse_support_set_record(resolution.record)
        except CliError as exc:
            findings.append(
                {
                    "kind": "invalid_support_record",
                    "anchor": anchor,
                    "resolved_anchor": resolution.anchor,
                    "error": str(exc),
                    "occurrences": occurrences,
                }
            )
            anchors.append(
                {
                    "anchor": anchor,
                    "status": "invalid",
                    "resolved_anchor": resolution.anchor,
                    "tag_mismatch": resolution.tag_mismatch,
                    "occurrences": occurrences,
                }
            )
            continue

        resolved_anchor_count += 1
        identities = sorted({str(member["session"]) for member in members})
        anchor_payload = {
            "anchor": anchor,
            "status": "resolved",
            "resolved_anchor": resolution.anchor,
            "tag_mismatch": resolution.tag_mismatch,
            "support_member_count": len(members),
            "session_identities": identities,
            "occurrences": occurrences,
        }
        anchors.append(anchor_payload)
        if resolution.tag_mismatch:
            findings.append(
                {
                    "kind": "tag_mismatch",
                    "anchor": anchor,
                    "resolved_anchor": resolution.anchor,
                    "occurrences": occurrences,
                }
            )

        for identity in identities:
            session = sessions.setdefault(
                identity,
                {
                    "identity_hash": identity,
                    "anchors": set(),
                    "support_member_count": 0,
                },
            )
            session["anchors"].add(anchor)  # type: ignore[union-attr]
            session["support_member_count"] += sum(
                1 for member in members if member["session"] == identity
            )

    session_payloads = [
        _chatlas_anchory_session_payload(
            identity,
            aggregate,
            row=rows_by_identity.get(identity),
            chatlas_root=root,
        )
        for identity, aggregate in sorted(sessions.items())
    ]
    return {
        "status": "needs-review" if findings else "ok",
        "command": "chatlas anchory sessions",
        "chatlas_root": str(root),
        "regex": regex,
        "glob": glob,
        "sources": [str(Path(source).expanduser().resolve()) for source in sources],
        "files": [str(path) for path in files],
        "file_count": len(files),
        "anchor_count": len(occurrences_by_anchor),
        "resolved_anchor_count": resolved_anchor_count,
        "session_count": len(session_payloads),
        "sessions": session_payloads,
        "anchors": anchors,
        "findings": findings,
    }


def _chatlas_anchory_source_files(
    sources: tuple[str | Path, ...], *, glob: str
) -> tuple[Path, ...]:
    files: set[Path] = set()
    for source in sources:
        path = Path(source).expanduser().resolve()
        if path.is_file():
            files.add(path)
            continue
        if path.is_dir():
            try:
                files.update(
                    candidate for candidate in path.rglob(glob) if candidate.is_file()
                )
            except (OSError, ValueError) as exc:
                raise CliError(
                    f"cannot expand anchory source {path} with glob {glob!r}: {exc}"
                ) from exc
            continue
        raise CliError(f"anchory source does not exist: {path}")
    return tuple(sorted(files))


def _chatlas_anchory_session_payload(
    identity: str,
    aggregate: dict[str, object],
    *,
    row: dict[str, Any] | None,
    chatlas_root: Path,
) -> dict[str, object]:
    from .chat_index import chat_index_discovery

    payload: dict[str, object] = {
        "identity_hash": identity,
        "indexed": row is not None,
        "provider": string_or_none(row.get("provider")) if row else None,
        "session_id": string_or_none(row.get("session_id")) if row else None,
        "uri": string_or_none(row.get("uri")) if row else None,
        "last_activity_at": (
            string_or_none(row.get("last_activity_at")) if row else None
        ),
        "anchors": sorted(aggregate["anchors"]),
        "support_member_count": aggregate["support_member_count"],
        "chat_index": chat_index_discovery(identity, chatlas_root=chatlas_root),
    }
    return payload


def _support_set_member_count(record: object) -> int:
    if not isinstance(record, dict) or record.get("app") != "chatlas":
        raise CliError("chatlas anchor record must have app='chatlas'")
    if record.get("schema") not in _RECORD_FIELDS:
        raise CliError(
            "chatlas anchor record has unsupported schema; "
            f"expected one of {sorted(_RECORD_FIELDS)!r}"
        )
    if record.get("schema") == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        relationships = record.get("relationships")
        support = (
            relationships.get("support") if isinstance(relationships, dict) else None
        )
        members = support.get("members") if isinstance(support, dict) else None
    else:
        members = record.get("members")
    if not isinstance(members, list) or not members:
        raise CliError("chatlas support-set record members must be a non-empty list")
    return len(members)


def format_chatlas_anchory_stats_pretty(payload: dict[str, object]) -> str:
    def number(name: str) -> str:
        value = payload.get(name)
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    lines = [
        "Chatlas Anchory Support Sets",
        f"Anchors: {number('anchor_count')}",
        f"Support turns: {number('support_turn_count')}",
        "Members per anchor:",
        f"  Min: {number('min')}",
        f"  Max: {number('max')}",
        f"  Mean: {number('mean')}",
        f"  Population stddev: {number('population_stddev')}",
        "Distribution:",
    ]
    distribution = payload.get("distribution")
    if not isinstance(distribution, dict) or not distribution:
        lines.append("  No anchors")
        return "\n".join(lines)
    for member_count, anchor_count in distribution.items():
        member_label = "member" if member_count == "1" else "members"
        anchor_label = "anchor" if anchor_count == 1 else "anchors"
        lines.append(f"  {member_count} {member_label}: {anchor_count} {anchor_label}")
    return "\n".join(lines)


def _parse_member_types(raw_types: object, *, index: int) -> dict[str, Any] | None:
    """Validate and return a member's optional `types` map, or None when absent.

    Dumb by design (Impl.Req 598): a present `types` must be a non-empty object
    keyed by non-empty Turn.Type names; cargo values are stored verbatim without
    schema validation. An empty map is rejected — absence, not `{}`, is how a
    base support turn is expressed.
    """
    if raw_types is None:
        return None
    if not isinstance(raw_types, dict) or not raw_types:
        raise CliError(
            f"chatlas support-set member {index} types must be a non-empty object "
            "(omit the field for a base support turn)"
        )
    for type_name in raw_types:
        if not isinstance(type_name, str) or not type_name.strip():
            raise CliError(
                f"chatlas support-set member {index} has an invalid Turn.Type name"
            )
    return dict(raw_types)


def parse_support_set_record(record: object) -> list[dict[str, Any]]:
    if not isinstance(record, dict) or record.get("app") != "chatlas":
        raise CliError("chatlas anchor record must have app='chatlas'")
    schema = record.get("schema")
    fields = _RECORD_FIELDS.get(schema) if isinstance(schema, str) else None
    if fields is None:
        raise CliError(
            "chatlas anchor record has unsupported schema; "
            f"expected one of {sorted(_RECORD_FIELDS)!r}"
        )
    unknown = set(record) - fields
    if unknown:
        raise CliError(
            "chatlas support-set record has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    if schema == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        return list(
            parse_line_anchor_dossier(record)["relationships"]["support"]["members"]
        )
    hint = record.get("hint")
    if not isinstance(hint, str) or not hint.strip():
        raise CliError("chatlas support-set record hint must be a non-empty sentence")
    raw_members = record.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise CliError("chatlas support-set record members must be a non-empty list")
    members: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_member in enumerate(raw_members):
        if not isinstance(raw_member, dict):
            raise CliError(f"chatlas support-set member {index} must be an object")
        member_unknown = set(raw_member) - _MEMBER_FIELDS
        if member_unknown:
            raise CliError(
                f"chatlas support-set member {index} has unknown fields: "
                + ", ".join(sorted(member_unknown))
            )
        member: dict[str, Any] = {}
        for field in ("session", "turn_id", "turn_hash", "at"):
            value = string_or_none(raw_member.get(field))
            if value is None:
                raise CliError(
                    f"chatlas support-set member {index} requires non-empty {field!r}"
                )
            member[field] = value
        member_types = _parse_member_types(raw_member.get("types"), index=index)
        if member_types is not None:
            member["types"] = member_types
        identity = (member["session"], member["turn_id"])
        if identity in seen:
            raise CliError(
                f"chatlas support-set member {index} is a duplicate: "
                f"{member['session']}:{member['turn_id']}"
            )
        seen.add(identity)
        members.append(member)
    return members


def _parse_dossier_turn_ref(value: object, *, field: str) -> dict[str, str]:
    return parse_normal_turn_ref(value, field=field)


def _parse_unique_refs(raw: object, *, field: str) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        raise CliError(f"{field} must be a non-empty list")
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, value in enumerate(raw):
        ref = _parse_dossier_turn_ref(value, field=f"{field} item {index}")
        identity = (ref["session"], ref["turn_id"])
        if identity in seen:
            raise CliError(f"{field} repeats {ref['session']}:{ref['turn_id']}")
        seen.add(identity)
        refs.append(ref)
    return refs


def _parse_gate_list(
    raw: object,
    *,
    kind: str,
    fields: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise CliError(f"chatlas line dossier gate {kind} must be a list")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(raw):
        if not isinstance(value, dict):
            raise CliError(
                f"chatlas line dossier gate {kind} item {index} must be an object"
            )
        unknown = set(value) - fields
        if unknown:
            raise CliError(
                f"chatlas line dossier gate {kind} item {index} has unknown fields: "
                + ", ".join(sorted(unknown))
            )
        item: dict[str, Any] = {}
        if kind == "tokenized_verbatim_approval":
            token = string_or_none(value.get("token"))
            if token is None:
                raise CliError(
                    f"chatlas line dossier gate {kind} item {index} requires token"
                )
            item["token"] = token
        for position in ("proposal_turn", "approval_turn"):
            if position not in value:
                if kind == "semantic_approval" and position == "proposal_turn":
                    continue
                raise CliError(
                    f"chatlas line dossier gate {kind} item {index} requires {position}"
                )
            item[position] = _parse_dossier_turn_ref(
                value[position], field=f"{kind} item {index} {position}"
            )
        key = json.dumps(item, sort_keys=True, separators=(",", ":"))
        if key in seen:
            raise CliError(f"chatlas line dossier gate {kind} repeats item {index}")
        seen.add(key)
        parsed.append(item)
    return parsed


def parse_line_anchor_dossier(record: object) -> dict[str, Any]:
    if not isinstance(record, dict) or record.get("app") != "chatlas":
        raise CliError("chatlas anchor record must have app='chatlas'")
    if record.get("schema") != CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        raise CliError(
            f"Index.Line.Anchor requires schema {CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA!r}"
        )
    unknown = set(record) - _RECORD_FIELDS[CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA]
    if unknown:
        raise CliError(
            "chatlas line anchor dossier has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    attachment = record.get("attachment")
    if not isinstance(attachment, dict):
        raise CliError("chatlas line anchor dossier requires object attachment")
    attachment_unknown = set(attachment) - _ATTACHMENT_FIELDS
    if attachment_unknown:
        raise CliError(
            "chatlas line anchor dossier attachment has unknown fields: "
            + ", ".join(sorted(attachment_unknown))
        )
    if attachment.get("canonical_schema") != INDEX_LINE_ANCHOR_TRIPLET_SCHEMA:
        raise CliError(
            "chatlas line anchor dossier attachment canonical_schema must be "
            f"{INDEX_LINE_ANCHOR_TRIPLET_SCHEMA!r}"
        )
    triplet_hash = attachment.get("triplet_hash")
    if not isinstance(triplet_hash, str) or not _CONTENT_HASH_RE.fullmatch(
        triplet_hash
    ):
        raise CliError(
            "chatlas line anchor dossier triplet_hash must be lowercase sha256:<hex>"
        )
    relationships = record.get("relationships")
    if not isinstance(relationships, dict):
        raise CliError("chatlas line anchor dossier requires object relationships")
    relationship_unknown = set(relationships) - _RELATIONSHIP_FIELDS
    if relationship_unknown or set(relationships) != _RELATIONSHIP_FIELDS:
        raise CliError(
            "chatlas line anchor dossier relationships must contain exactly support, gates, provenance"
        )
    support = relationships.get("support")
    if not isinstance(support, dict) or set(support) != _SUPPORT_FIELDS:
        raise CliError(
            "chatlas line anchor dossier support must contain exactly members"
        )
    members = _parse_unique_refs(
        support.get("members"), field="relationships.support.members"
    )
    gates = relationships.get("gates")
    if not isinstance(gates, dict) or set(gates) != _GATE_FIELDS:
        raise CliError(
            "chatlas line anchor dossier gates must contain exactly semantic_approval and tokenized_verbatim_approval"
        )
    parsed_gates = {
        "semantic_approval": _parse_gate_list(
            gates.get("semantic_approval"),
            kind="semantic_approval",
            fields=_SEMANTIC_APPROVAL_FIELDS,
        ),
        "tokenized_verbatim_approval": _parse_gate_list(
            gates.get("tokenized_verbatim_approval"),
            kind="tokenized_verbatim_approval",
            fields=_TOKENIZED_APPROVAL_FIELDS,
        ),
    }
    provenance = relationships.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != _PROVENANCE_FIELDS:
        raise CliError(
            "chatlas line anchor dossier provenance must contain exactly predecessor_anchors and issue_context"
        )
    predecessors = _parse_predecessor_anchors(provenance.get("predecessor_anchors"))
    issues = _parse_issue_context(provenance.get("issue_context"))
    return {
        "app": "chatlas",
        "schema": CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
        "attachment": {
            "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
            "triplet_hash": triplet_hash,
        },
        "relationships": {
            "support": {"members": members},
            "gates": parsed_gates,
            "provenance": {
                "predecessor_anchors": list(predecessors),
                "issue_context": list(issues),
            },
        },
    }


def parse_line_attachment(record: object) -> dict[str, str] | None:
    if isinstance(record, dict) and record.get("schema") == CHATLAS_SUPPORT_SET_SCHEMA:
        return None
    dossier = parse_line_anchor_dossier(record)
    return dict(dossier["attachment"])


def _parse_predecessor_anchors(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise CliError("chatlas line anchor predecessor_anchors must be a list")
    predecessors: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not _ANCHOR_KEY_RE.fullmatch(value):
            raise CliError(
                f"chatlas line support predecessor {index} is not an anchor key"
            )
        if value in predecessors:
            raise CliError(
                f"chatlas line support predecessors contain duplicate {value!r}"
            )
        predecessors.append(value)
    return tuple(predecessors)


def _parse_issue_context(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise CliError("chatlas line dossier issue_context must be a list")
    issues: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not _ISSUE_ID_RE.fullmatch(value):
            raise CliError(
                f"chatlas line dossier issue_context item {index} must match Issue.I####"
            )
        if value in issues:
            raise CliError(f"chatlas line dossier repeats issue context {value!r}")
        issues.append(value)
    return tuple(issues)


def parse_line_gate_relationships(record: object) -> dict[str, list[dict[str, Any]]]:
    dossier = parse_line_anchor_dossier(record)
    return deepcopy(dossier["relationships"]["gates"])


def parse_line_predecessors(record: object) -> tuple[str, ...]:
    dossier = parse_line_anchor_dossier(record)
    return tuple(dossier["relationships"]["provenance"]["predecessor_anchors"])


def parse_line_issue_context(record: object) -> tuple[str, ...]:
    dossier = parse_line_anchor_dossier(record)
    return tuple(dossier["relationships"]["provenance"]["issue_context"])


def bind_support_set_to_index_line(
    record: object,
    *,
    line_content: str,
    anchor: str,
    gates: dict[str, object] | None = None,
    predecessors: tuple[str, ...] = (),
    issue_context: tuple[str, ...] = (),
) -> dict[str, object]:
    members = parse_support_set_record(record)
    clean_members = [
        {field: member[field] for field in ("session", "turn_id", "turn_hash", "at")}
        for member in members
    ]
    raw_gates = gates or {
        "semantic_approval": [],
        "tokenized_verbatim_approval": [],
    }
    bound: dict[str, object] = {
        "app": "chatlas",
        "schema": CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
        "attachment": {
            "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
            "triplet_hash": index_line_anchor_triplet_hash(line_content, anchor),
        },
        "relationships": {
            "support": {"members": clean_members},
            "gates": deepcopy(raw_gates),
            "provenance": {
                "predecessor_anchors": list(predecessors),
                "issue_context": list(issue_context),
            },
        },
    }
    return parse_line_anchor_dossier(bound)


def _load_session_model(
    identity_hash: str,
    *,
    chatlas_root: Path | None,
) -> dict[str, Any]:
    from .index_query import select_materialization_row, select_one_chatlas_index_row
    from .views import load_chatlas_session_model

    session = select_one_chatlas_index_row(
        command="chatlas anchory",
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )
    session = select_materialization_row(session)
    return load_chatlas_session_model(session, chatlas_root=chatlas_root)


def _is_user_turn_message(event: dict[str, Any]) -> bool:
    payload = event.get("payload")
    return (
        string_or_none(event.get("kind")) == "message"
        and isinstance(payload, dict)
        and string_or_none(payload.get("role")) == "user"
        and normal_turn_kind(event) == "user"
    )


def turn_landing_event(
    session_model: dict[str, Any],
    turn_id: str,
    *,
    require_visible_user: bool,
) -> dict[str, Any] | None:
    """The event a `Normal.Turn` member resolves to.

    A turn spans many events; the landing point is the turn's own user message
    — the touch the `Touched.Index` grounds on. For a general event support set
    the first event of the turn stands in, since no user message need exist.
    """
    in_turn = _turn_index(session_model).get(turn_id, ())
    return _landing_event_from_turn(
        in_turn,
        require_visible_user=require_visible_user,
    )


def _turn_index(
    session_model: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], ...]]:
    chat = session_model.get("chat")
    events = dict_list(chat.get("events")) if isinstance(chat, dict) else []
    turns: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        turn_id = normal_turn_id(event)
        if turn_id is not None:
            turns.setdefault(turn_id, []).append(event)
    return {turn_id: tuple(in_turn) for turn_id, in_turn in turns.items()}


def _landing_event_from_turn(
    in_turn: tuple[dict[str, Any], ...],
    *,
    require_visible_user: bool,
) -> dict[str, Any] | None:
    if not in_turn:
        return None
    if not require_visible_user:
        return in_turn[0]
    for event in in_turn:
        if _is_user_turn_message(event):
            return event
    return in_turn[0]


def _validate_support_turn(
    member: dict[str, str],
    in_turn: tuple[dict[str, Any], ...],
    *,
    index: int,
    require_visible_user: bool,
) -> None:
    event = _landing_event_from_turn(
        in_turn,
        require_visible_user=require_visible_user,
    )
    if event is None:
        raise CliError(
            f"chatlas support-set member {index} turn is unavailable: "
            f"{member['session']}:{member['turn_id']}"
        )
    actual_ref = normal_turn_ref(member["session"], list(in_turn))
    if actual_ref["turn_hash"] != member["turn_hash"]:
        raise CliError(
            f"chatlas support-set member {index} turn_hash mismatch for "
            f"{member['session']}:{member['turn_id']}: "
            f"record={member['turn_hash']!r}, actual={actual_ref['turn_hash']!r}"
        )
    timestamp = string_or_none(event.get("timestamp"))
    if timestamp != member["at"]:
        raise CliError(
            f"chatlas support-set member {index} timestamp mismatch for "
            f"{member['session']}:{member['turn_id']}: "
            f"record={member['at']!r}, event={timestamp!r}"
        )
    if require_visible_user:
        payload = event.get("payload")
        surfaces = event.get("surfaces")
        role = (
            string_or_none(payload.get("role")) if isinstance(payload, dict) else None
        )
        transcript = (
            string_or_none(surfaces.get("transcript"))
            if isinstance(surfaces, dict)
            else None
        )
        if (
            string_or_none(event.get("kind")) != "message"
            or role != "user"
            or transcript != "visible"
        ):
            raise CliError(
                f"chatlas support-set member {index} does not identify a "
                f"visible user turn: {member['session']}:{member['turn_id']}"
            )


def _resolve_support_set_record(
    record: object,
    *,
    chatlas_root: Path | None = None,
    model_loader: Callable[[str], dict[str, Any]] | None = None,
    require_visible_user: bool,
    runtime_cache: ChatlasSupportRuntimeCache | None = None,
) -> list[ResolvedSupportMember]:
    members = parse_support_set_record(record)
    cache: dict[str, dict[str, Any]] = {}
    resolved: list[ResolvedSupportMember] = []
    for index, member in enumerate(members):
        session_identity = member["session"]
        if session_identity not in cache:
            try:
                cache[session_identity] = (
                    model_loader(session_identity)
                    if model_loader is not None
                    else _load_session_model(
                        session_identity, chatlas_root=chatlas_root
                    )
                )
            except Exception as exc:
                raise CliError(
                    f"chatlas support-set member {index} session is unavailable: "
                    f"{session_identity}"
                ) from exc
        session_model = cache[session_identity]
        in_turn = (
            runtime_cache.turn_events(
                session_identity,
                session_model,
                member["turn_id"],
            )
            if runtime_cache is not None
            else _turn_index(session_model).get(member["turn_id"], ())
        )
        event = _landing_event_from_turn(
            in_turn,
            require_visible_user=require_visible_user,
        )
        if event is None:
            raise CliError(
                f"chatlas support-set member {index} turn is unavailable: "
                f"{session_identity}:{member['turn_id']}"
            )
        _validate_support_turn(
            member,
            in_turn,
            index=index,
            require_visible_user=require_visible_user,
        )
        resolved.append(
            ResolvedSupportMember(
                member=dict(member),
                session_model=session_model,
                event=event,
            )
        )
    return resolved


def resolve_support_set_record(
    record: object,
    *,
    chatlas_root: Path | None = None,
    model_loader: Callable[[str], dict[str, Any]] | None = None,
    runtime_cache: ChatlasSupportRuntimeCache | None = None,
) -> list[ResolvedSupportMember]:
    return _resolve_support_set_record(
        record,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        require_visible_user=True,
        runtime_cache=runtime_cache,
    )


def resolve_event_support_set_record(
    record: object,
    *,
    chatlas_root: Path | None = None,
    model_loader: Callable[[str], dict[str, Any]] | None = None,
    runtime_cache: ChatlasSupportRuntimeCache | None = None,
) -> list[ResolvedSupportMember]:
    return _resolve_support_set_record(
        record,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
        require_visible_user=False,
        runtime_cache=runtime_cache,
    )


def _support_set_meaning(record: object) -> list[tuple[str, str, str]]:
    return [
        (member["session"], member["turn_id"], member["turn_hash"])
        for member in parse_support_set_record(record)
    ]


def support_equivalence_key(record: object) -> tuple[object, ...]:
    """Ordered semantic-support meaning, independent from gates and attachment."""

    return tuple(_support_set_meaning(record))


def exact_line_equivalence_key(record: object) -> tuple[object, ...] | None:
    """Stored dossier attachment plus independently typed relationships."""

    if (
        not isinstance(record, dict)
        or record.get("schema") != CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
    ):
        return None
    dossier = parse_line_anchor_dossier(record)
    return (
        dossier["attachment"]["triplet_hash"],
        _line_relationship_equivalence_key(dossier),
    )


def _line_relationship_equivalence_key(record: object) -> tuple[object, ...]:
    dossier = parse_line_anchor_dossier(record)
    relationships = dossier["relationships"]
    return (
        support_equivalence_key(dossier),
        json.dumps(relationships["gates"], sort_keys=True, separators=(",", ":")),
        tuple(relationships["provenance"]["predecessor_anchors"]),
        tuple(relationships["provenance"]["issue_context"]),
    )


def _depot_equivalence_scan(
    record: dict[str, object],
    *,
    chatlas_root: Path | None,
    entries: list[Any] | None = None,
    line_content: str | None = None,
) -> tuple[list[str], list[str]]:
    """One depot pass yielding both equivalence classes for a proposed record."""
    support_key = support_equivalence_key(record)
    line_key = (
        _line_relationship_equivalence_key(record)
        if record.get("schema") == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
        else None
    )
    if entries is None:
        entries = list(
            chatlas_anchory_depot(chatlas_root).query(namespace=CHATLAS_NAMESPACE)
        )
    support_equivalent: list[str] = []
    exact_line_equivalent: list[str] = []
    for entry in entries:
        try:
            entry_support_key = support_equivalence_key(entry.record)
        except CliError:
            continue
        if entry_support_key != support_key:
            continue
        support_equivalent.append(entry.anchor)
        if line_key is None or line_content is None:
            continue
        if (
            not isinstance(entry.record, dict)
            or entry.record.get("schema") != CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
        ):
            continue
        try:
            attachment = parse_line_attachment(entry.record)
            entry_line_key = _line_relationship_equivalence_key(entry.record)
        except CliError:
            continue
        expected_hash = index_line_anchor_triplet_hash(line_content, entry.anchor)
        if (
            attachment is not None
            and attachment["triplet_hash"] == expected_hash
            and entry_line_key == line_key
        ):
            exact_line_equivalent.append(entry.anchor)
    return support_equivalent, exact_line_equivalent


def validate_support_set_amendment(
    current_record: object,
    proposed_record: object,
    *,
    chatlas_root: Path | None = None,
    model_loader: Callable[[str], dict[str, Any]] | None = None,
) -> None:
    if not isinstance(current_record, dict) or not isinstance(proposed_record, dict):
        raise CliError("Chatlas anchor amendment requires object records")
    if current_record.get("schema") != proposed_record.get("schema"):
        raise CliError(
            "Chatlas anchor amendment cannot change relationship identity; "
            "mint a new anchor for another schema"
        )
    resolve_support_set_record(
        proposed_record,
        chatlas_root=chatlas_root,
        model_loader=model_loader,
    )
    if current_record.get("schema") == CHATLAS_SUPPORT_SET_SCHEMA:
        if parse_support_set_record(current_record) != parse_support_set_record(
            proposed_record
        ):
            raise CliError(
                "generic Chatlas support-set amendment cannot change support-set meaning"
            )
    else:
        parse_line_anchor_dossier(proposed_record)


def validate_chatlas_anchory_amendment(
    depot_root: Path,
    current_record: dict[str, object],
    proposed_record: dict[str, object],
) -> None:
    if current_record.get("app") != "chatlas":
        return
    validate_support_set_amendment(
        current_record,
        proposed_record,
        chatlas_root=depot_root.parent,
    )


def event_neighborhood(
    session_model: dict[str, Any],
    *,
    turn_id: str,
    radius: int = 4,
) -> dict[str, Any]:
    if radius < 0:
        raise CliError("chatlas anchory radius must be non-negative")

    from .normalization.session_model._views import _messages_from_events
    from .normalization.session_model.filters import apply_chatlas_filters

    filtered = apply_chatlas_filters(session_model, ("turns",))
    chat = filtered.get("chat")
    if not isinstance(chat, dict):
        raise CliError("chatlas session model has no chat event tape")
    events = dict_list(chat.get("events"))
    target_index = next(
        (
            index
            for index, event in enumerate(events)
            if normal_turn_id(event) == turn_id
        ),
        None,
    )
    if target_index is None:
        raise CliError(f"chatlas turn is unavailable after turn filtering: {turn_id}")
    start = max(0, target_index - radius)
    end = target_index + radius + 1
    projected = dict(filtered)
    projected_chat = dict(chat)
    selected_events = events[start:end]
    projected_chat["events"] = selected_events
    projected_chat["messages"] = _messages_from_events(selected_events)
    projected_chat["model_runs"] = []
    projected_chat["tool_invocations"] = []
    projected_chat["usage"] = []
    projected["chat"] = projected_chat
    return projected


def _parse_member_ref(value: str) -> tuple[str, str]:
    session, separator, turn_id = value.rpartition(":")
    if not separator or not session or not turn_id:
        raise CliError(
            "chatlas anchory --member must have the form <session-identity>:<turn-id>"
        )
    return session, turn_id


def _prepare_support_members(
    *,
    members: tuple[str, ...],
    chatlas_root: Path | None,
    models: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, str]], list[ResolvedSupportMember]]:
    """Resolve exact support members before a generic record or dossier is built.

    `models` may be supplied by a batch caller so one session model is loaded
    once for the whole run instead of once per item.
    """
    from .index_query import select_materialization_row, select_one_chatlas_index_row
    from .views import load_chatlas_session_model

    if not members:
        raise CliError("chatlas anchory requires at least one --member")

    record_members: list[dict[str, str]] = []
    if models is None:
        models = {}
    for index, member_ref in enumerate(members):
        session_ref, turn_id = _parse_member_ref(member_ref)
        session = select_one_chatlas_index_row(
            command=f"chatlas anchory member {index}",
            identity_hash=session_ref,
            chatlas_root=chatlas_root,
        )
        session = select_materialization_row(session)
        session_identity = string_or_none(session.get("identity_hash"))
        if session_identity is None:
            raise CliError(
                f"chatlas anchory member {index} session has no identity_hash"
            )
        session_model = models.get(session_identity)
        if session_model is None:
            session_model = load_chatlas_session_model(
                session, chatlas_root=chatlas_root
            )
            models[session_identity] = session_model
        in_turn = _turn_index(session_model).get(turn_id, ())
        event = _landing_event_from_turn(in_turn, require_visible_user=True)
        if event is None:
            raise CliError(
                f"chatlas anchory member {index} turn is unavailable: "
                f"{session_identity}:{turn_id}"
            )
        member_record = normal_turn_ref(
            session_identity,
            list(in_turn),
        )
        record_members.append(member_record)
    generic = {
        "app": "chatlas",
        "schema": CHATLAS_SUPPORT_SET_SCHEMA,
        "hint": "prepared support members",
        "members": record_members,
    }
    loaded = models
    resolved = resolve_support_set_record(
        generic, model_loader=lambda identity: loaded[identity]
    )
    return record_members, resolved


def normalize_line_gates(gates: object | None) -> dict[str, list[dict[str, Any]]]:
    if gates is None:
        return {"semantic_approval": [], "tokenized_verbatim_approval": []}
    if not isinstance(gates, dict) or set(gates) != _GATE_FIELDS:
        raise CliError(
            "chatlas line gates must contain exactly semantic_approval and tokenized_verbatim_approval"
        )
    return {
        "semantic_approval": _parse_gate_list(
            gates["semantic_approval"],
            kind="semantic_approval",
            fields=_SEMANTIC_APPROVAL_FIELDS,
        ),
        "tokenized_verbatim_approval": _parse_gate_list(
            gates["tokenized_verbatim_approval"],
            kind="tokenized_verbatim_approval",
            fields=_TOKENIZED_APPROVAL_FIELDS,
        ),
    }


def build_line_relationships(
    members: list[dict[str, str]],
    *,
    gates: object | None = None,
    predecessors: tuple[str, ...] = (),
    issue_context: tuple[str, ...] = (),
) -> dict[str, object]:
    parsed_predecessors = _parse_predecessor_anchors(list(predecessors))
    parsed_issues = _parse_issue_context(list(issue_context))
    return {
        "support": {"members": deepcopy(members)},
        "gates": normalize_line_gates(gates),
        "provenance": {
            "predecessor_anchors": list(parsed_predecessors),
            "issue_context": list(parsed_issues),
        },
    }


def build_line_anchor_dossier(
    *,
    anchor: str,
    line_content: str,
    relationships: dict[str, object],
) -> dict[str, object]:
    record = {
        "app": "chatlas",
        "schema": CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
        "attachment": {
            "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
            "triplet_hash": index_line_anchor_triplet_hash(line_content, anchor),
        },
        "relationships": deepcopy(relationships),
    }
    return parse_line_anchor_dossier(record)


def _event_text(event: dict[str, Any]) -> str:
    payload = event.get("payload")
    content = dict_list(payload.get("content")) if isinstance(payload, dict) else []
    return "\n".join(
        text
        for item in content
        if (text := string_or_none(item.get("text"))) is not None
    )


def _support_set_projection(
    record: dict[str, object],
    resolved: list[ResolvedSupportMember],
    *,
    detail: AnchoryDetail,
    radius: int,
    anchor: str | None = None,
) -> dict[str, object]:
    if detail not in {"summary", "turn", "context"}:
        raise CliError(f"unsupported Chatlas Anchory detail: {detail!r}")
    members: list[dict[str, object]] = []
    for item in resolved:
        turn_id = item.member["turn_id"]
        projected: dict[str, object] = {
            "member_ref": f"{item.member['session']}:{turn_id}",
            "member": item.member,
            "text": compact_text(_event_text(item.event)),
        }
        if detail == "turn":
            projected["normal_turn"] = {
                "turn_id": turn_id,
                "events": list(_turn_index(item.session_model).get(turn_id, ())),
            }
        elif detail == "context":
            projected["neighborhood"] = event_neighborhood(
                item.session_model,
                turn_id=turn_id,
                radius=radius,
            )
        members.append(projected)
    payload: dict[str, object] = {
        "detail": detail,
        "record": record,
        "members": members,
    }
    if record.get("schema") == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        payload["dossier"] = parse_line_anchor_dossier(record)
    if anchor is not None:
        payload["anchor"] = anchor
    return payload


def chatlas_anchory_preview(
    *,
    members: tuple[str, ...],
    hint: str | None = None,
    gates: object | None = None,
    line_content: str | None = None,
    issue_context: tuple[str, ...] = (),
    detail: AnchoryDetail = "summary",
    radius: int = 4,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    record_members, resolved = _prepare_support_members(
        members=members,
        chatlas_root=chatlas_root,
    )
    generic_record: dict[str, object] = {
        "app": "chatlas",
        "schema": CHATLAS_SUPPORT_SET_SCHEMA,
        "hint": hint or "line anchor dossier preview",
        "members": record_members,
    }
    if line_content is None:
        if hint is None or not hint.strip():
            raise CliError("generic chatlas support-set preview requires --hint")
        if gates is not None or issue_context:
            raise CliError("line relationships require --line-content")
        record = generic_record
        scan_line_content = None
    else:
        relationships = build_line_relationships(
            record_members, gates=gates, issue_context=issue_context
        )
        record = build_line_anchor_dossier(
            anchor="c00000000-0u",
            line_content=line_content,
            relationships=relationships,
        )
        scan_line_content = line_content
    payload = _support_set_projection(
        record if line_content is None else generic_record,
        resolved,
        detail=detail,
        radius=radius,
    )
    support_equivalent, exact_line_equivalent = _depot_equivalence_scan(
        record, chatlas_root=chatlas_root, line_content=scan_line_content
    )
    if line_content is not None:
        payload.pop("record", None)
        payload["relationships"] = deepcopy(record["relationships"])
        payload["attachment"] = {
            "canonical_schema": INDEX_LINE_ANCHOR_TRIPLET_SCHEMA,
            "status": "allocated-anchor-required",
        }


    payload["equivalent_anchors"] = support_equivalent
    payload["support_equivalent_anchors"] = support_equivalent
    payload["exact_line_equivalent_anchors"] = exact_line_equivalent
    return payload


def chatlas_anchory_register(
    *,
    members: tuple[str, ...],
    hint: str | None = None,
    gates: object | None = None,
    line_content: str | None = None,
    issue_context: tuple[str, ...] = (),
    detail: AnchoryDetail = "summary",
    radius: int = 4,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    record_members, resolved = _prepare_support_members(
        members=members,
        chatlas_root=chatlas_root,
    )
    primary_at = parse_event_timestamp(record_members[0]["at"])
    if primary_at is None:
        raise CliError("chatlas anchory primary member has an invalid timestamp")

    depot = chatlas_anchory_depot(chatlas_root)
    ensure_chatlas_namespace(depot)
    alloc_prefix = f"{primary_at.year:04d}{primary_at.month:02d}{primary_at.day:02d}"
    if line_content is None:
        if hint is None or not hint.strip():
            raise CliError("generic chatlas support-set registration requires --hint")
        if gates is not None or issue_context:
            raise CliError("line relationships require --line-content")
        record: dict[str, object] = {
            "app": "chatlas",
            "schema": CHATLAS_SUPPORT_SET_SCHEMA,
            "hint": hint,
            "members": record_members,
        }
        entry = depot.register(
            record,
            alloc_prefix=alloc_prefix,
            tag=USER_TURN_TAG,
            namespace=CHATLAS_NAMESPACE,
        )
    else:
        relationships = build_line_relationships(
            record_members, gates=gates, issue_context=issue_context
        )
        preview_record = build_line_anchor_dossier(
            anchor="c00000000-0u",
            line_content=line_content,
            relationships=relationships,
        )
        _support_equivalent, exact = _depot_equivalence_scan(
            preview_record,
            chatlas_root=chatlas_root,
            line_content=line_content,
        )
        if exact:
            resolution = depot.resolve(min(exact), namespace=CHATLAS_NAMESPACE)
            assert resolution is not None
            entry = resolution
        else:
            entry = depot.register_derived(
                lambda anchor: build_line_anchor_dossier(
                    anchor=anchor,
                    line_content=line_content,
                    relationships=relationships,
                ),
                alloc_prefix=alloc_prefix,
                tag=USER_TURN_TAG,
                namespace=CHATLAS_NAMESPACE,
            )
    return _support_set_projection(
        dict(entry.record),
        resolved,
        detail=detail,
        radius=radius,
        anchor=entry.anchor,
    )


def chatlas_anchory_resolve(
    anchor: str,
    *,
    radius: int = 4,
    detail: AnchoryDetail = "summary",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    depot = chatlas_anchory_depot(chatlas_root)
    resolution = depot.resolve(anchor)
    if resolution is None:
        raise CliError(f"anchor not found in depot {depot.root}: {anchor}")
    resolved = resolve_support_set_record(
        resolution.record,
        chatlas_root=chatlas_root,
    )
    return _support_set_projection(
        dict(resolution.record),
        resolved,
        detail=detail,
        radius=radius,
        anchor=anchor,
    )


def chatlas_line_anchor_reattach(
    anchor: str,
    *,
    depot_root: str | Path,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Refresh one dossier from parser-owned Index line occurrences."""

    anchor_key = normalize_anchor(anchor)
    root = Path(depot_root).expanduser().resolve()
    if not root.is_dir():
        raise CliError(f"Index depot is unavailable: {root}")
    occurrence_group = group_index_line_anchor_occurrences(
        parse_depot(root).kernel_lines(),
        anchors=(anchor_key,),
    ).get(anchor_key)
    if occurrence_group is None:
        raise CliError(
            f"anchor ^{anchor_key} is absent from the parsed Index depot: {root}"
        )
    sources = [
        {
            "path": occurrence.location(root)["path"],
            "line": occurrence.line.start_line,
        }
        for occurrence in occurrence_group.occurrences
    ]
    if occurrence_group.ambiguous:
        locations = [
            f"{location['path']}:{location['line']}"
            for location in sources
        ]
        raise CliError(
            f"anchor ^{anchor_key} resolves to {occurrence_group.projection_count} distinct Index "
            "line triplets; repair the collision before reattachment: "
            + ", ".join(locations)
        )
    observed_hash = occurrence_group.occurrences[0].triplet_hash

    depot = chatlas_anchory_depot(chatlas_root)
    resolution = depot.resolve(anchor_key, namespace=CHATLAS_NAMESPACE)
    if resolution is None:
        raise CliError(f"anchor not found in Chatlas depot: {anchor_key}")
    current = dict(resolution.record)
    if current.get("schema") != CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        raise CliError("reattachment requires a Chatlas.Line.Anchor.Dossier")
    dossier = parse_line_anchor_dossier(current)
    proposed = deepcopy(dossier)
    proposed["attachment"]["triplet_hash"] = observed_hash
    parse_line_anchor_dossier(proposed)
    if proposed == dossier:
        return {
            "status": "ok",
            "command": "chatlas anchory reattach",
            "anchor": resolution.anchor,
            "changed": False,
            "depot": str(root),
            "sources": sources,
            "attachment": deepcopy(dossier["attachment"]),
            "relationships": deepcopy(dossier["relationships"]),
        }

    def validate_reattachment(
        depot_root: Path,
        current_record: dict[str, object],
        proposed_record: dict[str, object],
    ) -> None:
        validate_chatlas_anchory_amendment(
            depot_root,
            current_record,
            proposed_record,
        )
        if parse_line_anchor_dossier(current_record) != dossier:
            raise CliError(
                "Chatlas line dossier changed during reattachment; retry from its current record"
            )
        current_relationships = parse_line_anchor_dossier(current_record)[
            "relationships"
        ]
        proposed_relationships = parse_line_anchor_dossier(proposed_record)[
            "relationships"
        ]
        if proposed_relationships != current_relationships:
            raise CliError("reattachment cannot change line dossier relationships")

    entry = depot.amend(
        resolution.anchor,
        proposed,
        namespace=CHATLAS_NAMESPACE,
        validator=validate_reattachment,
    )
    amended = parse_line_anchor_dossier(entry.record)
    return {
        "status": "ok",
        "command": "chatlas anchory reattach",
        "anchor": entry.anchor,
        "changed": True,
        "depot": str(root),
        "sources": sources,
        "attachment": deepcopy(amended["attachment"]),
        "relationships": deepcopy(amended["relationships"]),
    }


def chatlas_line_issue_enrich(
    anchor: str,
    *,
    issue_context: tuple[str, ...] = (),
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Append Issue edition context to a line-bound anchor.

    Issue context records a provenance relationship to a named Issue edition;
    it does not itself establish a review gate. Where a line has been
    materialized is recomputed from Delta containment.
    """
    depot = chatlas_anchory_depot(chatlas_root)
    resolution = depot.resolve(anchor, namespace=CHATLAS_NAMESPACE)
    if resolution is None:
        raise CliError(f"anchor not found in Chatlas depot: {anchor}")
    current = dict(resolution.record)
    if current.get("schema") != CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        raise CliError("issue enrichment requires a Chatlas.Line.Anchor.Dossier")
    existing_issues = list(parse_line_issue_context(current))
    for issue in issue_context:
        if issue not in existing_issues:
            existing_issues.append(issue)
    proposed = deepcopy(current)
    proposed["relationships"]["provenance"]["issue_context"] = existing_issues
    parse_line_anchor_dossier(proposed)
    if proposed == current:
        return {
            "status": "ok",
            "command": "chatlas anchory enrich",
            "anchor": resolution.anchor,
            "changed": False,
            "record": current,
            "issue_context": list(parse_line_issue_context(current)),
        }
    entry = depot.amend(
        resolution.anchor,
        proposed,
        namespace=CHATLAS_NAMESPACE,
        validator=validate_chatlas_anchory_amendment,
    )
    return {
        "status": "ok",
        "command": "chatlas anchory enrich",
        "anchor": entry.anchor,
        "changed": True,
        "record": dict(entry.record),
        "issue_context": list(parse_line_issue_context(entry.record)),
    }


__all__ = [
    "CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA",
    "CHATLAS_NAMESPACE",
    "CHATLAS_NS_PREFIX",
    "CHATLAS_SUPPORT_SET_SCHEMA",
    "LINE_BOUND_SCHEMAS",
    "AnchoryDetail",
    "ResolvedSupportMember",
    "bind_support_set_to_index_line",
    "build_line_anchor_dossier",
    "build_line_relationships",
    "chatlas_anchory_depot",
    "chatlas_anchory_preview",
    "chatlas_anchory_register",
    "chatlas_anchory_resolve",
    "chatlas_anchory_stats",
    "chatlas_line_anchor_reattach",
    "chatlas_line_issue_enrich",
    "ensure_chatlas_namespace",
    "event_neighborhood",
    "exact_line_equivalence_key",
    "format_chatlas_anchory_stats_pretty",
    "normalize_line_gates",
    "parse_line_anchor_dossier",
    "parse_line_attachment",
    "parse_line_gate_relationships",
    "parse_line_issue_context",
    "parse_line_predecessors",
    "parse_support_set_record",
    "resolve_event_support_set_record",
    "resolve_support_set_record",
    "support_equivalence_key",
    "validate_chatlas_anchory_amendment",
    "validate_support_set_amendment",
]
