# $kw: --from Chat.Index.Delta --from Chat.Index.HEAD --from Line.Home --from File.Numbering.Protocol --note [IMPL] one render model decides every mechanical detail so validate and apply can never disagree --supp ^c20260804-60u
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav.index.model import index_line_anchor_triplet_hash

from tarav.chatlas.anchory import (
    LINE_BOUND_SCHEMAS,
    chatlas_anchory_depot,
    parse_line_attachment,
)
from tarav.chatlas.anchory_batch import chatlas_anchory_batch_preview
from tarav.chatlas.chat_index import (
    HEAD_FILENAME,
    chat_index_source_model,
    chat_index_surface_path,
    compare_v2_source_tail,
    load_chat_index_capture,
    select_chat_index_session,
    session_locator,
)
from tarav.chatlas.chat_index_audit import index_lines_of
from tarav.chatlas.chat_index_plan import (
    CAPTURE_PLAN_SCHEMA,
    CapturePlan,
    PlanBlock,
    PlanLine,
    base_surface_state,
    load_capture_plan,
)



_STABLE_TAIL_STATES = {"current", "append-only"}
_MAINTAINABLE_TAIL_STATES = {*_STABLE_TAIL_STATES, "expanded", "revised"}


class RenderDelta:
    __slots__ = (
        "relative_path",
        "horizon",
        "tape_position",
        "action",
        "blocks",
        "content",
        "line_refs",
    )

    def __init__(
        self,
        *,
        relative_path: str,
        horizon: dict[str, Any],
        tape_position: int,
        action: str,
        blocks: list[PlanBlock] | None = None,
        content: str | None = None,
        line_refs: list[tuple[str, str]] | None = None,
    ) -> None:
        self.relative_path = relative_path
        self.horizon = horizon
        self.tape_position = tape_position
        self.action = action
        self.blocks = blocks
        self.content = content
        self.line_refs = line_refs or []


class RenderModel:
    """The complete resulting surface, decided before anything is written."""

    __slots__ = (
        "root",
        "session",
        "identity_hash",
        "surface_path",
        "mode",
        "plan",
        "source",
        "tail",
        "deltas",
        "head_blocks",
        "head_line_refs",
        "batch_items",
        "removed_paths",
        "managed_files",
        "base_fingerprint",
    )

    def __init__(self, **fields: Any) -> None:
        for name in self.__slots__:
            setattr(self, name, fields.get(name))


def build_render_model(
    plan: CapturePlan,
    *,
    chatlas_root: Path | None = None,
) -> RenderModel:
    """Validate a plan against live reality and decide the whole result.

    Nothing here writes: it is the shared truth `validate` reports and `apply`
    re-derives under its lock.
    """
    envelope = plan.envelope
    locator = envelope["session"]
    identity_hash = locator.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise CliError("Chat.Index capture plan envelope requires a session identity")
    root, session, resolved_identity = select_chat_index_session(
        command="chatlas chat-index validate",
        chatlas_root=chatlas_root,
        selectors={"identity_hash": identity_hash},
    )
    if resolved_identity != identity_hash:
        raise CliError("Chat.Index capture plan resolved a different session")

    planned_source = envelope["source"]
    _canonical, live_source = chat_index_source_model(session, chatlas_root=root)
    tail = compare_v2_source_tail(planned_source, live_source)
    allowed_tail_states = (
        _MAINTAINABLE_TAIL_STATES
        if envelope.get("mode") == "maintain-v2"
        else _STABLE_TAIL_STATES
    )
    if tail["state"] not in allowed_tail_states:
        raise CliError(
            "Chat.Index capture plan inspected a prefix that is no longer "
            f"reproducible ({tail['state']}); scaffold and review again"
        )

    surface_path = chat_index_surface_path(identity_hash, chatlas_root=root)
    base = base_surface_state(surface_path, identity_hash=identity_hash)
    _verify_base_surface(envelope, base)

    mode = envelope["mode"]
    prior_capture = _prior_capture(mode, surface_path, identity_hash, base)

    source_turns = {
        str(entry["turn_ref"]["turn_id"]): entry for entry in planned_source["turn_refs"]
    }
    deltas, batch_items = _plan_deltas(
        plan, source_turns=source_turns, surface_path=surface_path, prior=prior_capture
    )
    head_blocks = (
        _preserved_head_blocks(surface_path)
        if plan.preserve_head
        else plan.head_blocks
    )
    head_line_refs, head_items = _plan_head(head_blocks, deltas)
    batch_items.extend(head_items)

    _verify_existing_anchors(
        deltas, head_line_refs, head_blocks, chatlas_root=root
    )
    _verify_delta_support_horizons(batch_items, source_turns=source_turns)

    managed_files = [
            *(delta.relative_path for delta in deltas),
        HEAD_FILENAME,
    ]
    prior_managed = (
        [str(value) for value in (base or {}).get("managed_files", [])] if base else []
    )
    removed_paths = [
        path for path in prior_managed if path not in set(managed_files)
    ]

    return RenderModel(
        root=root,
        session=session,
        identity_hash=identity_hash,
        surface_path=surface_path,
        mode=mode,
        plan=plan,
        source=planned_source,
        tail=tail,
        deltas=deltas,
        head_blocks=head_blocks,
        head_line_refs=head_line_refs,
        batch_items=batch_items,
        removed_paths=removed_paths,
        managed_files=managed_files,
        base_fingerprint=None if base is None else base["fingerprint"],
    )


def _verify_base_surface(
    envelope: dict[str, Any], base: dict[str, object] | None
) -> None:
    planned = envelope.get("base_surface")
    if (planned is None) != (base is None):
        raise CliError(
            "Chat.Index managed surface appeared or disappeared since scaffold; "
            "scaffold and review again"
        )
    if planned is None or base is None:
        return
    if planned.get("fingerprint") != base["fingerprint"]:
        raise CliError(
            "Chat.Index managed surface changed since scaffold; scaffold and "
            "review again"
        )


def _prior_capture(
    mode: str,
    surface_path: Path,
    identity_hash: str,
    base: dict[str, object] | None,
) -> dict[str, Any] | None:
    if mode == "create":
        if base is not None:
            raise CliError(
                "Chat.Index capture plan mode 'create' found an existing managed "
                "surface; use 'maintain-v2'"
            )
        return None
    if base is None:
        raise CliError(
            f"Chat.Index capture plan mode {mode!r} requires an existing managed surface"
        )
    capture, error = load_chat_index_capture(
        surface_path, expected_identity_hash=identity_hash
    )
    if error is not None or capture is None:
        raise CliError(f"Chat.Index maintain-v2 base is not valid: {error}")
    return capture


def _plan_deltas(
    plan: CapturePlan,
    *,
    source_turns: dict[str, dict[str, Any]],
    surface_path: Path,
    prior: dict[str, Any] | None,
) -> tuple[list[RenderDelta], list[dict[str, Any]]]:
    prior_deltas = {
        str(delta["horizon"]["turn_id"]): delta
        for delta in (prior["deltas"] if prior is not None else [])
    }
    edited: dict[str, RenderDelta] = {}
    batch_items: list[dict[str, Any]] = []
    for edit in plan.delta_edits:
        entry = source_turns.get(edit.horizon_turn_id)
        if entry is None:
            raise CliError(
                f"Chat.Index capture plan Delta horizon {edit.horizon_turn_id!r} is "
                "absent from the inspected source prefix"
            )
        if entry.get("turn_kind") != "user":
            raise CliError(
                f"Chat.Index capture plan Delta horizon {edit.horizon_turn_id!r} is "
                "not a qualifying User.Turn"
            )
        relative_path = f"deltas/{edit.horizon_turn_id}.md"
        line_refs: list[tuple[str, str]] = []
        for block in edit.blocks:
            for index, line in enumerate(block.lines):
                if line.anchor is not None:
                    line_refs.append((line.statement_key, f"anchor:{line.anchor}"))
                    continue
                client_id = f"delta:{edit.horizon_turn_id}:{block.concept}:{index}"
                batch_items.append(
                    {
                        "client_id": client_id,
                        "line_content": line.content,
                        "members": tuple(line.support["members"]),
                        "gates": line.support["gates"],
                        "predecessors": (),
                        "tape_bound": entry["tape_position"],
                    }
                )
                line_refs.append((line.statement_key, f"client:{client_id}"))
        edited[edit.horizon_turn_id] = RenderDelta(
            relative_path=relative_path,
            horizon=entry["turn_ref"],
            tape_position=entry["tape_position"],
            action="render",
            blocks=edit.blocks,
            line_refs=line_refs,
        )

    deltas = list(edited.values())
    for turn_id, delta in prior_deltas.items():
        if turn_id in edited:


            continue
        prior_entry = source_turns.get(turn_id)
        if prior_entry is None:
            raise CliError(
                f"Chat.Index preserved Delta horizon {turn_id!r} is absent from the "
                "inspected source prefix"
            )
        relative_path = str(delta["path"])
        content = (surface_path / relative_path).read_text(encoding="utf-8")
        deltas.append(
            RenderDelta(
                relative_path=relative_path,
                horizon=prior_entry["turn_ref"],
                tape_position=int(prior_entry["tape_position"]),
                action="preserve",
                content=content,
                line_refs=[
                    (line.statement_key, f"anchor:{line.anchors[0]}")
                    for line in index_lines_of(relative_path, content.splitlines())
                    if len(line.anchors) == 1
                ],
            )
        )

    deltas.sort(key=lambda delta: delta.tape_position)
    seen = set()
    for delta in deltas:
        if delta.relative_path in seen:
            raise CliError(
                f"Chat.Index capture plan produces a duplicate Delta path: "
                f"{delta.relative_path}"
            )
        seen.add(delta.relative_path)
    return deltas, batch_items


def _plan_head(
    head_blocks: list[PlanBlock], deltas: list[RenderDelta]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve every HEAD line to the anchor it will actually carry."""
    occurrences: dict[str, str] = {}
    for delta in deltas:
        for statement_key, ref in delta.line_refs:
            occurrences.setdefault(statement_key, ref)

    refs: list[str] = []
    items: list[dict[str, Any]] = []
    for block in head_blocks:
        for index, line in enumerate(block.lines):
            existing = occurrences.get(line.statement_key)
            if existing is not None:
                if line.anchor is not None and existing != f"anchor:{line.anchor}":
                    raise CliError(
                        f"Chat.Index capture plan {line.location} names an anchor that "
                        "disagrees with its Chat.Index.Delta occurrence"
                    )
                refs.append(existing)
                continue
            if line.anchor is not None:
                refs.append(f"anchor:{line.anchor}")
                continue
            if line.support is None:
                raise CliError(
                    f"Chat.Index capture plan {line.location} has no Chat.Index.Delta "
                    "occurrence, so it may remain HEAD-first only with its own support"
                )
            client_id = f"head:{block.concept}:{index}"
            items.append(
                {
                    "client_id": client_id,
                    "line_content": line.content,
                    "members": line.support["members"],
                    "gates": line.support["gates"],
                    "predecessors": (),
                    "tape_bound": None,
                }
            )
            refs.append(f"client:{client_id}")
    return refs, items


def _preserved_head_blocks(surface_path: Path) -> list[PlanBlock]:
    """Load the existing semantic HEAD so a Delta-only maintenance plan is safe."""
    path = surface_path / HEAD_FILENAME
    if not path.is_file():
        raise CliError("Chat.Index HEAD preservation requires an existing HEAD.md")
    blocks: list[PlanBlock] = []
    concept: str | None = None
    lines: list[PlanLine] = []

    def finish() -> None:
        nonlocal lines
        if concept is not None:
            blocks.append(PlanBlock(concept=concept, lines=lines))
        lines = []

    for line_number, source in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if source.startswith("## "):
            finish()
            concept = source[3:].strip()
            continue
        if not source.startswith("- "):
            continue
        if concept is None:
            raise CliError(
                f"Chat.Index HEAD preservation found a line before a block at {path}:{line_number}"
            )
        parsed = index_lines_of(HEAD_FILENAME, [source])
        if len(parsed) != 1 or len(parsed[0].anchors) != 1:
            raise CliError(
                f"Chat.Index HEAD preservation requires one exact anchor at {path}:{line_number}"
            )
        anchor = parsed[0].anchors[0]
        content = source[: source.rfind(f" ^{anchor}")]
        lines.append(
            PlanLine(
                content=content,
                anchor=anchor,
                support=None,
                location=f"preserved HEAD {concept!r} line {line_number}",
            )
        )
    finish()
    return blocks


def _verify_existing_anchors(
    deltas: list[RenderDelta],
    head_line_refs: list[str],
    head_blocks: list[PlanBlock],
    *,
    chatlas_root: Path | None,
) -> None:
    """Every reused anchor must be a dossier attached to the exact line triplet."""
    wanted: dict[str, set[str]] = {}
    for delta in deltas:
        if delta.action != "render":
            continue
        for statement_key, ref in delta.line_refs:
            if ref.startswith("anchor:"):
                wanted.setdefault(ref[len("anchor:") :], set()).add(statement_key)
    head_keys = [line.statement_key for block in head_blocks for line in block.lines]
    for statement_key, ref in zip(head_keys, head_line_refs, strict=True):
        if ref.startswith("anchor:"):
            wanted.setdefault(ref[len("anchor:") :], set()).add(statement_key)

    depot = chatlas_anchory_depot(chatlas_root)
    for anchor, statement_keys in sorted(wanted.items()):
        resolution = depot.resolve(anchor)
        if resolution is None:
            raise CliError(
                f"Chat.Index capture plan names an unknown anchor: ^{anchor}"
            )
        record = dict(resolution.record)
        if record.get("schema") not in LINE_BOUND_SCHEMAS:
            raise CliError(
                f"Chat.Index capture plan names generic anchor ^{anchor}; an "
                "Index.Line requires a line-bound record"
            )
        attachment = parse_line_attachment(record)
        assert attachment is not None
        for statement_key in sorted(statement_keys):
            line_type, body = json.loads(statement_key)
            source = f"- [{line_type}] {body}" if line_type else f"- {body}"
            if attachment["triplet_hash"] != index_line_anchor_triplet_hash(source, anchor):
                raise CliError(
                    f"Chat.Index capture plan anchor ^{anchor} does not ground the "
                    "line it is attached to; a changed body or Line.Type requires "
                    "support reevaluation"
                )


def _verify_delta_support_horizons(
    batch_items: list[dict[str, Any]],
    *,
    source_turns: dict[str, dict[str, Any]],
) -> None:
    """A Delta line may only be grounded in evidence its horizon could see."""
    bounds = {
        item["client_id"]: item["tape_bound"]
        for item in batch_items
        if item["tape_bound"] is not None
    }
    for item in batch_items:
        bound = bounds.get(item["client_id"])
        for member in item["members"]:
            _, _, turn_id = member.partition(":")
            entry = source_turns.get(turn_id)
            if (
                entry is None
                or entry.get("turn_kind") != "user"
            ):
                raise CliError(
                    f"Chat.Index capture plan support member {member!r} is not a "
                    "qualifying User.Turn of the inspected prefix"
                )
            if bound is not None and entry["tape_position"] > bound:
                raise CliError(
                    f"Chat.Index capture plan support member {member!r} sits after "
                    "the Delta horizon it grounds"
                )


def render_surface(model: RenderModel, anchors: dict[str, str]) -> dict[str, str]:
    """The complete managed file set, byte-for-byte, as text."""
    files: dict[str, str] = {}
    for delta in model.deltas:
        if delta.action == "preserve":
            files[delta.relative_path] = delta.content or ""
            continue
        files[delta.relative_path] = _render_delta(delta, anchors)
    files[HEAD_FILENAME] = _render_head(model, anchors)
    return files


def _render_delta(delta: RenderDelta, anchors: dict[str, str]) -> str:
    heading = f"# Chat.Index.Delta/{delta.horizon['turn_id']}"
    at = delta.horizon.get("at")
    if at:
        heading = f"{heading} @ {at}"
    lines = [heading]
    refs = iter(delta.line_refs)
    for block in delta.blocks or []:
        lines.extend(["", f"## {block.concept}", ""])
        for line in block.lines:
            _statement_key, ref = next(refs)
            lines.append(f"{line.content} ^{_anchor_of(ref, anchors)}")
    return "\n".join(lines) + "\n"


def _render_head(model: RenderModel, anchors: dict[str, str]) -> str:
    lines = ["# Chat.Index.HEAD"]
    horizon = _head_horizon(model)
    if horizon is not None:
        at = horizon.get("at")
        declared = f"Evidence.Horizon: `{horizon['turn_id']}`"
        if at:
            declared = f"{declared} @ {at}"
        lines.extend(["", declared])
    refs = iter(model.head_line_refs)
    for block in model.head_blocks:
        lines.extend(["", f"## {block.concept}", ""])
        for line in block.lines:
            lines.append(f"{line.content} ^{_anchor_of(next(refs), anchors)}")
    return "\n".join(lines) + "\n"


def _head_horizon(model: RenderModel) -> dict[str, Any] | None:
    turn_refs = model.source["turn_refs"]
    return turn_refs[-1]["turn_ref"] if turn_refs else None


def _anchor_of(ref: str, anchors: dict[str, str]) -> str:
    kind, _, value = ref.partition(":")
    if kind == "anchor":
        return value
    anchor = anchors.get(value)
    if anchor is None:
        raise CliError(f"Chat.Index render is missing an anchor for {value!r}")
    return anchor


def chatlas_chat_index_validate(
    *,
    plan: str | Path,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Read-only: prove a plan renders and ground nothing while doing it."""
    loaded = load_capture_plan(Path(plan).expanduser().resolve())
    model = build_render_model(loaded, chatlas_root=chatlas_root)
    anchor_plan = chatlas_anchory_batch_preview(
        items=[_batch_item(item) for item in model.batch_items],
        chatlas_root=model.root,
    ) if model.batch_items else {
        "item_count": 0,
        "mint_count": 0,
        "reuse_count": 0,
        "items": [],
    }
    return {
        "status": "ok",
        "command": "chatlas chat-index validate",
        "schema": CAPTURE_PLAN_SCHEMA,
        "chatlas_root": str(model.root),
        "session": session_locator(model.session),
        "plan_path": str(loaded.path),
        "mode": model.mode,
        "surface_path": str(model.surface_path),
        "plan_status": loaded.status,
        "tail": model.tail,
        "anchor_plan": {
            "item_count": anchor_plan["item_count"],
            "mint_count": anchor_plan["mint_count"],
            "reuse_count": anchor_plan["reuse_count"],
            "items": [
                {
                    "client_id": item["client_id"],
                    "action": item["action"],
                    "anchor": item["anchor"],
                }
                for item in anchor_plan["items"]
            ],
        },
        "files": _file_inventory(model),
        "removed_paths": model.removed_paths,
        "ok": True,
    }


def _batch_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in item.items() if key != "tape_bound"
    }


def _file_inventory(model: RenderModel) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    for delta in model.deltas:
        inventory.append(
            {
                "relative_path": delta.relative_path,
                "action": delta.action,
                "line_count": len(delta.line_refs),
                "horizon_turn_id": delta.horizon["turn_id"],
                "tape_position": delta.tape_position,
            }
        )
    inventory.append(
        {
            "relative_path": HEAD_FILENAME,
            "action": "render",
            "line_count": len(model.head_line_refs),
        }
    )
    return inventory


__all__ = [
    "HEAD_FILENAME",
    "RenderDelta",
    "RenderModel",
    "build_render_model",
    "chatlas_chat_index_validate",
    "render_surface",
]
