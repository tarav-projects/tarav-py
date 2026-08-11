# $kw: --from Chat.Index --from Chat.Index.Delta --from Chat.Index.HEAD --from Index.Line --note [IMPL] the plan carries semantics only; descriptors, headings, anchors, and ordering stay CPU-derived --supp ^c20260804-60u
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.index.model import canonical_index_line_statement
from agentos.index.model.identity import ANCHOR_RE, TYPE_BRACKET_RE

from agentos.chatlas.chat_index import (
    chat_index_source_model,
    chat_index_surface_path,
    compare_v2_source_tail,
    source_prefix_at_horizon,
    load_chat_index_capture,
    select_chat_index_session,
    session_locator,
)
from agentos.chatlas.normalization.session_model.messages import (
    transcript_visible_messages,
)


CAPTURE_PLAN_SCHEMA = "agentos.chat-index.capture-plan.v1"
PLAN_FILENAME = "plan.json"
EVIDENCE_FILENAME = "evidence.json"
EVIDENCE_SCHEMA = "agentos.chat-index.capture-evidence.v1"

MODES = ("create", "maintain-v2")

_ENVELOPE_FIELDS = {
    "session",
    "mode",
    "source",
    "base_surface",
    "prior_capture",
    "tail",
    "scaffolded_at",
}
_PLAN_FIELDS = {"schema", "chatlas", "delta_edits", "head", "status"}
_BLOCK_FIELDS = {"concept", "lines"}
_LINE_FIELDS = {"content", "support"}
_SUPPORT_FIELDS = {"anchor", "members", "gates"}


class PlanLine:
    """One agent-authored semantic line inside a plan block."""

    __slots__ = ("content", "statement_key", "anchor", "support", "location")

    def __init__(
        self,
        *,
        content: str,
        anchor: str | None,
        support: dict[str, Any] | None,
        location: str,
    ) -> None:
        self.content = content
        self.statement_key = canonical_index_line_statement(content)
        self.anchor = anchor
        self.support = support
        self.location = location


class PlanBlock:
    __slots__ = ("concept", "lines")

    def __init__(self, *, concept: str, lines: list[PlanLine]) -> None:
        self.concept = concept
        self.lines = lines


class DeltaEdit:
    __slots__ = ("horizon_turn_id", "blocks")

    def __init__(self, *, horizon_turn_id: str, blocks: list[PlanBlock]) -> None:
        self.horizon_turn_id = horizon_turn_id
        self.blocks = blocks


class CapturePlan:
    __slots__ = (
        "envelope",
        "delta_edits",
        "head_blocks",
        "preserve_head",
        "status",
        "path",
    )

    def __init__(
        self,
        *,
        envelope: dict[str, Any],
        delta_edits: list[DeltaEdit],
        head_blocks: list[PlanBlock],
        preserve_head: bool,
        status: str,
        path: Path | None = None,
    ) -> None:
        self.envelope = envelope
        self.delta_edits = delta_edits
        self.head_blocks = head_blocks
        self.preserve_head = preserve_head
        self.status = status
        self.path = path


def surface_files(surface_path: Path) -> list[str]:
    """Every file the surface actually holds, as the surface holds it."""
    if not surface_path.is_dir():
        return []
    return sorted(
        str(path.relative_to(surface_path))
        for path in surface_path.rglob("*")
        if path.is_file()
    )


def surface_fingerprint(surface_path: Path, managed_files: list[str]) -> str:
    """Content fingerprint of one managed surface, order-independent."""
    digest = hashlib.sha256()
    for relative_path in sorted(managed_files):
        path = surface_path / relative_path
        content = path.read_bytes() if path.is_file() else b""
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def base_surface_state(
    surface_path: Path, *, identity_hash: str
) -> dict[str, object] | None:
    """The existing managed surface, fingerprinted over what is really there.

    The file list is the directory listing rather than a declaration, so a
    stray or deleted file changes the fingerprint instead of being reconciled
    against a manifest that could disagree with it.
    """
    managed_files = surface_files(surface_path)
    if not managed_files:
        return None
    _capture, error = load_chat_index_capture(
        surface_path, expected_identity_hash=identity_hash
    )
    return {
        "readable": error is None,
        "error": error,
        "managed_files": managed_files,
        "fingerprint": surface_fingerprint(surface_path, managed_files),
    }


def chatlas_chat_index_scaffold(
    *,
    stage: str | Path,
    mode: str | None = None,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    """Write transient capture working input: CPU envelope plus chat evidence.

    The stage is never a Chatlas Product and never a managed surface; it exists
    so an agent can author semantics against evidence it did not have to gather.
    """
    root, session, identity_hash = select_chat_index_session(
        command="chatlas chat-index scaffold",
        chatlas_root=chatlas_root,
        selectors=selectors,
    )
    stage_path = Path(stage).expanduser().resolve()
    if stage_path.exists() and any(stage_path.iterdir()):
        raise CliError(f"chatlas chat-index scaffold stage is not empty: {stage_path}")
    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    base = base_surface_state(surface_path, identity_hash=identity_hash)
    resolved_mode = _resolve_mode(mode, base)

    canonical, source = chat_index_source_model(session, chatlas_root=root)
    prior_capture: dict[str, object] | None = None
    tail: dict[str, object] | None = None
    if base is not None and base["readable"]:
        capture, _error = load_chat_index_capture(
            surface_path, expected_identity_hash=identity_hash
        )
        assert capture is not None
        prior_capture = {"delta_count": len(capture["deltas"])}
        tail = compare_v2_source_tail(
            source_prefix_at_horizon(source, capture["head"]["horizon"]), source
        )

    envelope = {
        "session": session_locator(session),
        "mode": resolved_mode,
        "source": source,
        "base_surface": base,
        "prior_capture": prior_capture,
        "tail": tail,
        "scaffolded_at": _now(),
    }
    plan = {
        "schema": CAPTURE_PLAN_SCHEMA,
        "chatlas": envelope,
        "delta_edits": [],
        "head": {"preserve": resolved_mode == "maintain-v2", "blocks": []},
        "status": "draft",
    }
    evidence = _scaffold_evidence(canonical, tail=tail, identity_hash=identity_hash)

    stage_path.mkdir(parents=True, exist_ok=True)
    _write_json(stage_path / PLAN_FILENAME, plan)
    _write_json(stage_path / EVIDENCE_FILENAME, evidence)
    return {
        "status": "ok",
        "command": "chatlas chat-index scaffold",
        "schema": CAPTURE_PLAN_SCHEMA,
        "chatlas_root": str(root),
        "session": session_locator(session),
        "stage": str(stage_path),
        "plan_path": str(stage_path / PLAN_FILENAME),
        "evidence_path": str(stage_path / EVIDENCE_FILENAME),
        "mode": resolved_mode,
        "surface_path": str(surface_path),
        "base_surface": base,
        "tail": tail,
        "evidence_turn_count": len(evidence["turns"]),
        "source_turn_count": source["turn_count"],
    }


def _resolve_mode(mode: str | None, base: dict[str, object] | None) -> str:
    if mode is not None and mode not in MODES:
        raise CliError(
            "chatlas chat-index mode must be one of " + ", ".join(MODES)
        )
    if base is None:
        detected = "create"
    elif base["readable"]:
        detected = "maintain-v2"
    else:
        raise CliError(
            "chatlas chat-index scaffold found an unreadable existing surface: "
            f"{base['error']}"
        )
    if mode is None:
        return detected
    if mode != detected:
        raise CliError(
            f"chatlas chat-index scaffold mode {mode!r} disagrees with the existing "
            f"surface, which requires {detected!r}"
        )
    return mode


def _scaffold_evidence(
    canonical: dict[str, Any],
    *,
    tail: dict[str, object] | None,
    identity_hash: str,
) -> dict[str, Any]:
    """Chat-only evidence for the turns this capture actually has to read."""
    pending: set[tuple[object, ...]] | None = None
    if tail is not None and tail["state"] in {"append-only", "expanded", "revised"}:
        pending = {
            (
                entry["turn_ref"]["turn_id"],
                entry["tape_position"],
            )
            for entry in tail["turn_refs"]
            if isinstance(entry, dict)
        }
    turns: list[dict[str, object]] = []
    for turn in canonical["turns"]:
        key = (turn["turn_ref"]["turn_id"], turn["tape_position"])
        if pending is not None and key not in pending:
            continue
        turns.append(
            {
                "turn_ref": turn["turn_ref"],
                "tape_position": turn["tape_position"],
                "role": turn["role"],
                "producer_type": turn["producer_type"],
                "messages": transcript_visible_messages(
                    turn["normal_turn"].get("events")
                ),
            }
        )
    return {
        "schema": EVIDENCE_SCHEMA,
        "session_identity": identity_hash,
        "scope": "pending" if pending is not None else "complete-prefix",
        "turn_count": len(turns),
        "turns": turns,
    }


def load_capture_plan(path: Path) -> CapturePlan:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"cannot read Chat.Index capture plan: {path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid Chat.Index capture plan JSON: {path}") from exc
    plan = parse_capture_plan(payload)
    plan.path = path
    return plan


def parse_capture_plan(payload: object) -> CapturePlan:
    """Structural plan validation; semantic checks need the live session."""
    if not isinstance(payload, dict):
        raise CliError("Chat.Index capture plan must be a JSON object")
    if payload.get("schema") != CAPTURE_PLAN_SCHEMA:
        raise CliError(
            f"Chat.Index capture plan requires schema {CAPTURE_PLAN_SCHEMA!r}; "
            f"got {payload.get('schema')!r}"
        )
    unknown = set(payload) - _PLAN_FIELDS
    if unknown:
        raise CliError(
            "Chat.Index capture plan has unknown fields: " + ", ".join(sorted(unknown))
        )
    envelope = payload.get("chatlas")
    if not isinstance(envelope, dict):
        raise CliError("Chat.Index capture plan requires its CPU-owned chatlas envelope")
    missing = sorted(_ENVELOPE_FIELDS - set(envelope))
    if missing:
        raise CliError(
            "Chat.Index capture plan envelope is missing CPU-owned fields: "
            + ", ".join(missing)
        )
    if envelope.get("mode") not in MODES:
        raise CliError(
            "Chat.Index capture plan envelope mode must be one of " + ", ".join(MODES)
        )
    if not isinstance(envelope.get("source"), dict):
        raise CliError("Chat.Index capture plan envelope requires a source descriptor")

    raw_edits = payload.get("delta_edits")
    if not isinstance(raw_edits, list):
        raise CliError("Chat.Index capture plan delta_edits must be an array")
    edits: list[DeltaEdit] = []
    seen_horizons: set[str] = set()
    for index, raw_edit in enumerate(raw_edits):
        if not isinstance(raw_edit, dict):
            raise CliError(f"Chat.Index capture plan delta edit {index} must be an object")
        if set(raw_edit) - {"horizon_turn_id", "blocks"}:
            raise CliError(
                f"Chat.Index capture plan delta edit {index} has unknown fields"
            )
        horizon_turn_id = raw_edit.get("horizon_turn_id")
        if not isinstance(horizon_turn_id, str) or not horizon_turn_id:
            raise CliError(
                f"Chat.Index capture plan delta edit {index} requires horizon_turn_id"
            )
        if horizon_turn_id in seen_horizons:
            raise CliError(
                "Chat.Index capture plan edits the same Delta twice: "
                f"{horizon_turn_id!r}"
            )
        seen_horizons.add(horizon_turn_id)
        edits.append(
            DeltaEdit(
                horizon_turn_id=horizon_turn_id,
                blocks=_parse_blocks(
                    raw_edit.get("blocks"),
                    location=f"delta {horizon_turn_id}",
                    require_support=True,
                ),
            )
        )

    head = payload.get("head")
    if not isinstance(head, dict) or set(head) - {"blocks", "preserve"}:
        raise CliError(
            "Chat.Index capture plan head must be an object with blocks and optional preserve"
        )
    preserve_head = head.get("preserve", False)
    if not isinstance(preserve_head, bool):
        raise CliError("Chat.Index capture plan head preserve must be boolean")
    head_blocks = _parse_blocks(
        head.get("blocks"), location="head", require_support=False
    )
    if preserve_head and head_blocks:
        raise CliError(
            "Chat.Index capture plan head cannot preserve and replace blocks together"
        )
    if preserve_head and envelope.get("mode") != "maintain-v2":
        raise CliError("Chat.Index HEAD preservation requires maintain-v2 mode")




    status = payload.get("status")
    if status not in {"draft", "ready"}:
        raise CliError("Chat.Index capture plan status must be 'draft' or 'ready'")

    return CapturePlan(
        envelope=envelope,
        delta_edits=edits,
        head_blocks=head_blocks,
        preserve_head=preserve_head,
        status=status,
    )


def _parse_blocks(
    raw_blocks: object, *, location: str, require_support: bool
) -> list[PlanBlock]:
    if not isinstance(raw_blocks, list):
        raise CliError(f"Chat.Index capture plan {location} blocks must be an array")
    blocks: list[PlanBlock] = []
    seen_concepts: set[str] = set()
    for index, raw_block in enumerate(raw_blocks):
        if not isinstance(raw_block, dict):
            raise CliError(
                f"Chat.Index capture plan {location} block {index} must be an object"
            )
        if set(raw_block) - _BLOCK_FIELDS:
            raise CliError(
                f"Chat.Index capture plan {location} block {index} has unknown fields"
            )
        concept = raw_block.get("concept")
        if not isinstance(concept, str) or not concept.strip():
            raise CliError(
                f"Chat.Index capture plan {location} block {index} requires a concept"
            )
        if concept in seen_concepts:
            raise CliError(
                f"Chat.Index capture plan {location} repeats block {concept!r}"
            )
        seen_concepts.add(concept)
        raw_lines = raw_block.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            raise CliError(
                f"Chat.Index capture plan {location} block {concept!r} requires lines"
            )
        lines: list[PlanLine] = []
        for line_index, raw_line in enumerate(raw_lines):
            lines.append(
                _parse_line(
                    raw_line,
                    location=f"{location} block {concept!r} line {line_index}",
                    require_support=require_support,
                )
            )
        blocks.append(PlanBlock(concept=concept, lines=lines))
    return blocks


def _repaired_line_content(content: str) -> str | None:
    """The authored content in canonical form, or None when it needs an author.

    Only mechanical damage is repaired: surrounding padding and the trailing
    Support.Reference the renderer owns. A missing Line.Type is a semantic
    choice the author still owes, so it never produces a suggestion.
    """
    candidate = content.strip()
    while True:
        head, separator, tail = candidate.rpartition(" ")
        if not separator or not ANCHOR_RE.fullmatch(tail):
            break
        candidate = head.rstrip()
    if candidate == content:
        return None
    if TYPE_BRACKET_RE.match(candidate) is None:
        return None
    if any(ANCHOR_RE.fullmatch(token) for token in candidate.split()):
        return None
    return candidate


def _content_error(message: str, content: str) -> CliError:
    """Reject authored content and, when it is mechanical, show the fix."""
    repaired = _repaired_line_content(content)
    if repaired is not None:
        message = f"{message}; author it as {repaired!r}"
    return CliError(message)


def _parse_line(raw_line: object, *, location: str, require_support: bool) -> PlanLine:
    if not isinstance(raw_line, dict):
        raise CliError(f"Chat.Index capture plan {location} must be an object")
    if set(raw_line) - _LINE_FIELDS:
        raise CliError(f"Chat.Index capture plan {location} has unknown fields")
    content = raw_line.get("content")
    if not isinstance(content, str) or not content.strip():
        raise CliError(f"Chat.Index capture plan {location} requires content")
    if content != content.strip():
        raise _content_error(
            f"Chat.Index capture plan {location} content must not be padded", content
        )
    if not content.startswith("- ["):
        raise _content_error(
            f"Chat.Index capture plan {location} content must be a typed Index.Line "
            "starting with a '- [XX] ' Line.Type prefix",
            content,
        )
    if any(ANCHOR_RE.fullmatch(token) for token in content.split()):


        raise _content_error(
            f"Chat.Index capture plan {location} content must not carry an anchor; "
            "the renderer owns Delta Support.References",
            content,
        )
    raw_support = raw_line.get("support")
    if raw_support is None:
        if require_support:
            raise CliError(f"Chat.Index capture plan {location} requires support")
        return PlanLine(content=content, anchor=None, support=None, location=location)
    if not isinstance(raw_support, dict) or set(raw_support) - _SUPPORT_FIELDS:
        raise CliError(f"Chat.Index capture plan {location} support has unknown fields")
    anchor = raw_support.get("anchor")
    if anchor is not None:
        if set(raw_support) != {"anchor"}:
            raise CliError(
                f"Chat.Index capture plan {location} support names an existing anchor "
                "and a proposed record; choose one"
            )
        if not isinstance(anchor, str) or not ANCHOR_RE.fullmatch(f"^{anchor}"):
            raise CliError(
                f"Chat.Index capture plan {location} support anchor is not an anchor key"
            )
        return PlanLine(content=content, anchor=anchor, support=None, location=location)
    members = raw_support.get("members")
    if not isinstance(members, list) or not members or not all(
        isinstance(member, str) and member for member in members
    ):
        raise CliError(
            f"Chat.Index capture plan {location} support requires ordered members"
        )
    gates = raw_support.get("gates")
    if gates is not None and not isinstance(gates, dict):
        raise CliError(
            f"Chat.Index capture plan {location} support gates must be an object"
        )
    return PlanLine(
        content=content,
        anchor=None,
        support={
            "members": tuple(members),
            "gates": gates,
        },
        location=location,
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "CAPTURE_PLAN_SCHEMA",
    "EVIDENCE_FILENAME",
    "EVIDENCE_SCHEMA",
    "MODES",
    "PLAN_FILENAME",
    "CapturePlan",
    "DeltaEdit",
    "PlanBlock",
    "PlanLine",
    "base_surface_state",
    "chatlas_chat_index_scaffold",
    "load_capture_plan",
    "parse_capture_plan",
    "surface_fingerprint",
]
