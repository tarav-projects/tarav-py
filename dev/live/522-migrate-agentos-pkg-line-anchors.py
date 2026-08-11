#!/usr/bin/env python3
"""One-shot migration of one Index depot's cited anchors to dossier v1."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.index.model import KernelLine, index_line_statement_parts, parse_depot
from agentos.chatlas.anchory import (
    CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
    CHATLAS_NAMESPACE,
    CHATLAS_SUPPORT_SET_SCHEMA,
    build_line_anchor_dossier,
    build_line_relationships,
    chatlas_anchory_depot,
    parse_line_anchor_dossier,
)
from agentos.chatlas.normal_turn import parse_normal_turn_ref


LEGACY_LINE_SCHEMAS = {
    CHATLAS_SUPPORT_SET_SCHEMA,
    "chatlas.support-set.v4",
    "chatlas.support-set.v5",
    "chatlas.support-set.v6",
}
LEGACY_RECORD_FIELDS = {
    CHATLAS_SUPPORT_SET_SCHEMA: {"app", "schema", "hint", "members"},
    "chatlas.support-set.v4": {
        "app", "schema", "hint", "subject", "predecessors", "members"
    },
    "chatlas.support-set.v5": {
        "app", "schema", "hint", "subject", "predecessors", "members",
        "issue_context", "observations",
    },
    "chatlas.support-set.v6": {
        "app", "schema", "hint", "subject", "predecessors", "members",
        "issue_context",
    },
}
OLD_CONTENT_SCHEMA = "agentos.index-line-content.v1"


def _old_content_hash(source: str) -> str:
    line_type, body = index_line_statement_parts(source)
    canonical = f"{line_type or ''}\0{body}"
    return "sha256:" + sha256(
        f"{OLD_CONTENT_SCHEMA}\0{canonical}".encode("utf-8")
    ).hexdigest()


def _legacy_members(record: dict[str, Any], anchor: str) -> tuple[list[dict[str, str]], dict[str, list[dict[str, Any]]]]:
    raw_members = record.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raise CliError(f"^{anchor} has no legacy support members")
    members: list[dict[str, str]] = []
    semantic: list[dict[str, Any]] = []
    tokenized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_members):
        if not isinstance(raw, dict):
            raise CliError(f"^{anchor} member {index} is not an object")
        unknown_member_fields = set(raw) - {"session", "turn_id", "turn_hash", "at", "types"}
        if unknown_member_fields:
            raise CliError(
                f"^{anchor} member {index} has unprojectable fields: "
                f"{sorted(unknown_member_fields)}"
            )
        ref = parse_normal_turn_ref(
            {key: raw.get(key) for key in ("session", "turn_id", "turn_hash", "at")},
            field=f"^{anchor} member {index}",
        )
        identity = (ref["session"], ref["turn_id"])
        if identity in seen:
            raise CliError(f"^{anchor} repeats support member {identity[0]}:{identity[1]}")
        seen.add(identity)
        members.append(ref)
        types = raw.get("types")
        if types is None:
            continue
        if not isinstance(types, dict) or not types:
            raise CliError(f"^{anchor} member {index} has malformed legacy types")
        unknown = set(types) - {"semantic.approval.turn", "tokenized.approval.turn"}
        if unknown:
            raise CliError(f"^{anchor} member {index} has unprojectable types: {sorted(unknown)}")
        semantic_cargo = types.get("semantic.approval.turn")
        if semantic_cargo is not None:
            if not isinstance(semantic_cargo, dict):
                raise CliError(f"^{anchor} semantic approval cargo is not an object")
            unknown_cargo = set(semantic_cargo) - {"verbatim_turn", "approval_turn"}
            if unknown_cargo:
                raise CliError(
                    f"^{anchor} semantic approval cargo has unprojectable fields: "
                    f"{sorted(unknown_cargo)}"
                )
            gate: dict[str, Any] = {"approval_turn": deepcopy(semantic_cargo.get("approval_turn", ref))}
            proposal = semantic_cargo.get("verbatim_turn")
            if proposal is not None:
                gate["proposal_turn"] = deepcopy(proposal)
            semantic.append(gate)
        token_cargo = types.get("tokenized.approval.turn")
        if token_cargo is not None:
            if not isinstance(token_cargo, dict):
                raise CliError(f"^{anchor} tokenized approval cargo is not an object")
            if set(token_cargo) != {"token", "verbatim_turn", "approval_turn"}:
                raise CliError(f"^{anchor} tokenized approval cargo has an unknown shape")
            tokenized.append(
                {
                    "token": token_cargo["token"],
                    "proposal_turn": deepcopy(token_cargo["verbatim_turn"]),
                    "approval_turn": deepcopy(token_cargo["approval_turn"]),
                }
            )
    return members, {
        "semantic_approval": semantic,
        "tokenized_verbatim_approval": tokenized,
    }


def migrate_record(
    *, anchor: str, source: str, record: dict[str, Any]
) -> dict[str, object]:
    schema = record.get("schema")
    if schema == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        parsed = parse_line_anchor_dossier(record)
        expected = build_line_anchor_dossier(
            anchor=anchor,
            line_content=source,
            relationships=parsed["relationships"],
        )
        if expected["attachment"] != parsed["attachment"]:
            raise CliError(f"^{anchor} dossier attachment already drifts from its Index triplet")
        return parsed
    if record.get("app") != "chatlas" or schema not in LEGACY_LINE_SCHEMAS:
        raise CliError(f"^{anchor} has unsupported migration schema {schema!r}")
    expected_fields = LEGACY_RECORD_FIELDS[str(schema)]
    if set(record) != expected_fields:
        raise CliError(
            f"^{anchor} legacy record fields differ from {schema}: "
            f"missing={sorted(expected_fields - set(record))}, "
            f"unknown={sorted(set(record) - expected_fields)}"
        )
    if schema != CHATLAS_SUPPORT_SET_SCHEMA:
        subject = record.get("subject")
        if (
            not isinstance(subject, dict)
            or set(subject) != {"kind", "canonical_schema", "content_hash"}
            or subject.get("kind") != "index.line"
            or subject.get("canonical_schema") != OLD_CONTENT_SCHEMA
            or subject.get("content_hash") != _old_content_hash(source)
        ):
            raise CliError(f"^{anchor} legacy subject does not match its current typed statement")
    if schema == "chatlas.support-set.v5" and record.get("observations"):
        raise CliError(f"^{anchor} carries observations with no lossless v1 projection")
    members, gates = _legacy_members(record, anchor)
    predecessors = record.get("predecessors", [])
    issues = record.get("issue_context", [])
    if not isinstance(predecessors, list):
        raise CliError(f"^{anchor} legacy predecessors are not a list")
    if not isinstance(issues, list):
        raise CliError(f"^{anchor} legacy issue_context is not a list")
    relationships = build_line_relationships(
        members,
        gates=gates,
        predecessors=tuple(predecessors),
        issue_context=tuple(issues),
    )
    return build_line_anchor_dossier(
        anchor=anchor,
        line_content=source,
        relationships=relationships,
    )


def plan_migration(
    *, index_depot: Path, chatlas_root: Path
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    model = parse_depot(index_depot)
    occurrences: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for document in model.documents:
        if document.path is None:
            continue
        for node in document.nodes:
            if not isinstance(node, KernelLine):
                continue
            for span in node.spans:
                if span.kind == "anchor":
                    occurrences[str(span.parsed["anchor"])].append(
                        (str(document.path.relative_to(index_depot)), node.start_line, node.src)
                    )
    depot = chatlas_anchory_depot(chatlas_root)
    changes: dict[str, dict[str, object]] = {}
    source_schemas: Counter[str] = Counter()
    already_current = 0
    for anchor, rows in sorted(occurrences.items()):
        statements = {index_line_statement_parts(source) for _path, _line, source in rows}
        if len(statements) != 1:
            raise CliError(f"^{anchor} occurs on divergent Index statements: {rows}")
        resolution = depot.resolve(anchor, namespace=CHATLAS_NAMESPACE)
        if resolution is None:
            raise CliError(f"^{anchor} does not resolve in the Chatlas depot")
        record = dict(resolution.record)
        source_schemas[str(record.get("schema"))] += 1
        migrated = migrate_record(anchor=anchor, source=rows[0][2], record=record)
        if migrated == record:
            already_current += 1
        else:
            changes[anchor] = migrated
    report: dict[str, object] = {
        "status": "ok",
        "index_depot": str(index_depot),
        "document_count": len(model.documents),
        "occurrence_count": sum(len(rows) for rows in occurrences.values()),
        "anchor_count": len(occurrences),
        "source_schemas": dict(sorted(source_schemas.items())),
        "already_current_count": already_current,
        "change_count": len(changes),
    }
    return report, changes


def apply_migration(
    *, index_depot: Path, chatlas_root: Path
) -> dict[str, object]:
    report, changes = plan_migration(index_depot=index_depot, chatlas_root=chatlas_root)
    depot = chatlas_anchory_depot(chatlas_root)
    for anchor, record in changes.items():
        depot.amend(anchor, record, namespace=CHATLAS_NAMESPACE)
    verified, remaining = plan_migration(index_depot=index_depot, chatlas_root=chatlas_root)
    if remaining:
        raise CliError(f"migration verification still plans {len(remaining)} changes")
    return {**report, "applied_count": len(changes), "verified": verified}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-depot", type=Path, required=True)
    parser.add_argument("--chatlas-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    index_depot = args.index_depot.expanduser().resolve()
    chatlas_root = args.chatlas_root.expanduser().resolve()
    report = (
        apply_migration(index_depot=index_depot, chatlas_root=chatlas_root)
        if args.apply
        else plan_migration(index_depot=index_depot, chatlas_root=chatlas_root)[0]
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
