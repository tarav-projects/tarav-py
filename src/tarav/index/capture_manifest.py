# $kw: Index.Capture/Manifest --from Index.Line.Record.Model --from Chat.Message.Ref
# --note [DC] one Capture.Manifest derives Anchory, source, LineRecord, and Chat.Index effects from one reviewed intent ^c20260821-37u
# --note [CT] preview resolves every reference, content expectation, gate, target, record conflict, and Chat.Index session before stable writes ^c20260821-38u
# --note [DC] message side is derived from relationship position and verified against Chat.Surface rather than repeated in the manifest ^c20260821-39u
# --note [CT] expect.contains_all is a conjunctive normalized content check that fails the complete batch before anchor registration ^c20260821-40u
# --note [CT] text and JSON render the same bounded Index.Capture.Run while complete effect totals remain visible ^c20260821-41u
# --note [CT] landing revalidates, registers dossiers, patches exact parser-resolved lines, creates records, applies Chat.Index, and audits the result ^c20260821-42u
# --note [CT] tokenized verbatim approvals become LineRecord.review gates so capture and review lint consume the same evidence ^c20260821-48u
# --note [CT] one capture run materializes each session's Chat.Message projection once and reuses exact resolved references across the batch ^c20260821-58u
"""Typed, fail-closed orchestration for complete Index capture."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_text
from tarav.chatlas.lossless import (
    CapturePlan,
    CapturePlanLine,
    apply_chat_index_capture_plan,
    chat_index_surface_path,
    chat_message_at,
    list_chat_messages,
    lossless_anchory_batch_preview,
    lossless_anchory_batch_register,
    provide_normal_model,
    provide_normal_model_reader,
    resolve_chat_message_ref,
    surface_state,
    validate_chat_index_capture_plan,
)

from .config import Geography
from .gates import GateRef
from .record.model import LineRecord, SupportRef
from .record.store import IndexStore
from .scope import ScopeKind, parse_scope
from .surfaces import (
    SurfaceLine,
    discover_surfaces,
    read_markdown_heading_lines,
    read_surface,
    resolve_surface_path,
)


CAPTURE_MANIFEST_SCHEMA = "tarav.index.capture-manifest.v1"
ModelLoader = Callable[[str], dict[str, object]]
ReaderLoader = Callable[[str], object]


@dataclass(frozen=True, slots=True)
class CaptureMessageRef:
    session: str
    message_address: str
    message_hash: str
    contains_all: tuple[str, ...] = ()
    at_hint: str | None = None

    @property
    def compact(self) -> str:
        return f"{self.session}:{self.message_address}:{self.message_hash}"


@dataclass(frozen=True, slots=True)
class CaptureTarget:
    surface: str
    block: str


@dataclass(frozen=True, slots=True)
class CaptureGate:
    kind: str
    approval: CaptureMessageRef
    proposal: CaptureMessageRef | None = None
    token: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureItem:
    client_id: str
    action: str
    target: CaptureTarget
    line_type: str | None
    body: str
    support: tuple[CaptureMessageRef, ...]
    gates: tuple[CaptureGate, ...] = ()
    predecessors: tuple[str, ...] = ()
    issue_context: tuple[str, ...] = ()

    @property
    def line_content(self) -> str:
        prefix = f"- [{self.line_type}] " if self.line_type else "- "
        return f"{prefix}{self.body}"

    @property
    def statement(self) -> str:
        return f"[{self.line_type}] {self.body}" if self.line_type else self.body

    @property
    def concept(self) -> str:
        if "#" in self.target.block:
            return self.target.block.rsplit("#", 1)[1]
        return self.target.block.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class CaptureManifest:
    chat_index_session: str
    items: tuple[CaptureItem, ...]
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class PreparedItem:
    item: CaptureItem
    line: SurfaceLine
    anchor_action: str
    anchor: str | None
    record_action: str
    host_kind: str
    source_lineno: int


@dataclass(frozen=True, slots=True)
class PreparedCapture:
    manifest: CaptureManifest
    items: tuple[PreparedItem, ...]
    models: dict[str, dict[str, object]]
    model_loader: ModelLoader
    reader_loader: ReaderLoader
    base_surface: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ManifestCaptureReport:
    mode: str
    manifest: str | None
    project_root: str
    status: str
    item_count: int
    items: tuple[dict[str, object], ...]
    effects: dict[str, object]
    audit: dict[str, object] | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "class": "Index.Capture.Run",
            "mode": self.mode,
            "status": self.status,
            "manifest": self.manifest,
            "project_root": self.project_root,
            "item_count": self.item_count,
            "showing": len(self.items),
            "items": list(self.items),
            "effects": dict(self.effects),
            "audit": self.audit,
        }


def load_capture_manifest(path: Path) -> CaptureManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"cannot read Capture.Manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid Capture.Manifest JSON: {path}: {exc}") from exc
    manifest = parse_capture_manifest(payload)
    return CaptureManifest(
        chat_index_session=manifest.chat_index_session,
        items=manifest.items,
        path=path.expanduser().resolve(),
    )


def parse_capture_manifest(value: object) -> CaptureManifest:
    if not isinstance(value, dict) or set(value) != {"schema", "chat_index", "items"}:
        raise CliError(
            "Capture.Manifest must contain exactly schema, chat_index, and items"
        )
    if value.get("schema") != CAPTURE_MANIFEST_SCHEMA:
        raise CliError(f"Capture.Manifest requires schema {CAPTURE_MANIFEST_SCHEMA!r}")
    chat_index = value.get("chat_index")
    if not isinstance(chat_index, dict) or set(chat_index) != {"session"}:
        raise CliError("Capture.Manifest chat_index must contain exactly session")
    session = _nonempty(chat_index.get("session"), "chat_index.session")
    raw_items = value.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise CliError("Capture.Manifest requires a non-empty items array")
    items = tuple(_parse_item(item, index) for index, item in enumerate(raw_items))
    ids = [item.client_id for item in items]
    if len(ids) != len(set(ids)):
        raise CliError("Capture.Manifest client_id values must be unique")
    return CaptureManifest(chat_index_session=session, items=items)


def _parse_item(value: object, index: int) -> CaptureItem:
    allowed = {
        "client_id",
        "action",
        "target",
        "line",
        "support",
        "gates",
        "predecessors",
        "issue_context",
    }
    required = {"client_id", "action", "target", "line", "support"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or not set(value).issubset(allowed)
    ):
        raise CliError(f"Capture.Manifest item {index} has an invalid shape")
    client_id = _nonempty(value.get("client_id"), f"items[{index}].client_id")
    action = value.get("action")
    if action != "ground":
        raise CliError(f"Capture.Manifest item {client_id!r} action must be 'ground'")
    target = value.get("target")
    if not isinstance(target, dict) or set(target) != {"surface", "block"}:
        raise CliError(f"Capture.Manifest item {client_id!r} target is invalid")
    parsed_target = CaptureTarget(
        surface=_nonempty(target.get("surface"), f"items[{index}].target.surface"),
        block=_nonempty(target.get("block"), f"items[{index}].target.block"),
    )
    line = value.get("line")
    if not isinstance(line, dict) or set(line) != {"type", "body"}:
        raise CliError(f"Capture.Manifest item {client_id!r} line is invalid")
    line_type = line.get("type")
    if line_type is not None and (
        not isinstance(line_type, str) or not line_type.strip()
    ):
        raise CliError(f"Capture.Manifest item {client_id!r} line.type is invalid")
    body = _nonempty(line.get("body"), f"items[{index}].line.body")
    if body != " ".join(body.split()):
        raise CliError(
            f"Capture.Manifest item {client_id!r} line.body is not canonical"
        )
    support = _parse_ref_list(value.get("support"), f"items[{index}].support")
    gates = _parse_gates(value.get("gates", {}), index=index)
    predecessors = _string_list(
        value.get("predecessors", []), f"items[{index}].predecessors"
    )
    issues = _string_list(
        value.get("issue_context", []), f"items[{index}].issue_context"
    )
    return CaptureItem(
        client_id=client_id,
        action="ground",
        target=parsed_target,
        line_type=line_type.strip() if isinstance(line_type, str) else None,
        body=body,
        support=support,
        gates=gates,
        predecessors=predecessors,
        issue_context=issues,
    )


def _parse_gates(value: object, *, index: int) -> tuple[CaptureGate, ...]:
    if not isinstance(value, dict) or not set(value).issubset(
        {"semantic_approval", "tokenized_verbatim_approval"}
    ):
        raise CliError(f"Capture.Manifest item {index} gates are invalid")
    parsed: list[CaptureGate] = []
    for kind in ("semantic_approval", "tokenized_verbatim_approval"):
        raw = value.get(kind, [])
        if not isinstance(raw, list):
            raise CliError(
                f"Capture.Manifest item {index} gate {kind} must be an array"
            )
        for position, entry in enumerate(raw):
            required = {"approval"}
            allowed = {"approval", "proposal"}
            if kind == "tokenized_verbatim_approval":
                required |= {"proposal", "token"}
                allowed |= {"token"}
            if (
                not isinstance(entry, dict)
                or not required.issubset(entry)
                or not set(entry).issubset(allowed)
            ):
                raise CliError(
                    f"Capture.Manifest item {index} gate {kind}[{position}] is invalid"
                )
            token = entry.get("token")
            if token is not None and (not isinstance(token, str) or not token):
                raise CliError(f"Capture.Manifest item {index} gate token is invalid")
            parsed.append(
                CaptureGate(
                    kind=kind,
                    proposal=(
                        _parse_message_ref(
                            entry["proposal"],
                            f"items[{index}].gates.{kind}[{position}].proposal",
                        )
                        if "proposal" in entry
                        else None
                    ),
                    approval=_parse_message_ref(
                        entry["approval"],
                        f"items[{index}].gates.{kind}[{position}].approval",
                    ),
                    token=token,
                )
            )
    return tuple(parsed)


def _parse_ref_list(value: object, field: str) -> tuple[CaptureMessageRef, ...]:
    if not isinstance(value, list) or not value:
        raise CliError(f"Capture.Manifest {field} must be a non-empty array")
    refs = tuple(
        _parse_message_ref(item, f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    identities = [(ref.session, ref.message_address, ref.message_hash) for ref in refs]
    if len(identities) != len(set(identities)):
        raise CliError(f"Capture.Manifest {field} repeats a message reference")
    return refs


def _parse_message_ref(value: object, field: str) -> CaptureMessageRef:
    allowed = {"session", "message_address", "message_hash", "hints", "expect"}
    required = {"session", "message_address", "message_hash"}
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or not set(value).issubset(allowed)
    ):
        raise CliError(f"Capture.Manifest {field} has an invalid shape")
    hints = value.get("hints", {})
    if not isinstance(hints, dict) or not set(hints).issubset({"at"}):
        raise CliError(f"Capture.Manifest {field}.hints is invalid")
    at_hint = hints.get("at")
    if at_hint is not None and (not isinstance(at_hint, str) or not at_hint):
        raise CliError(f"Capture.Manifest {field}.hints.at is invalid")
    expect = value.get("expect", {})
    if not isinstance(expect, dict) or not set(expect).issubset({"contains_all"}):
        raise CliError(f"Capture.Manifest {field}.expect is invalid")
    contains = expect.get("contains_all", [])
    if not isinstance(contains, list) or not all(
        isinstance(item, str) and item for item in contains
    ):
        raise CliError(f"Capture.Manifest {field}.expect.contains_all is invalid")
    return CaptureMessageRef(
        session=_nonempty(value.get("session"), f"{field}.session"),
        message_address=_digest(
            value.get("message_address"), f"{field}.message_address"
        ),
        message_hash=_digest(value.get("message_hash"), f"{field}.message_hash"),
        contains_all=tuple(contains),
        at_hint=at_hint,
    )


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CliError(
            f"Capture.Manifest {field} must be an array of non-empty strings"
        )
    if len(value) != len(set(value)):
        raise CliError(f"Capture.Manifest {field} contains duplicates")
    return tuple(value)


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"Capture.Manifest {field} must be a non-empty string")
    return value.strip()


def _digest(value: object, field: str) -> str:
    text = _nonempty(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise CliError(f"Capture.Manifest {field} must be a lowercase SHA-256 digest")
    return text


def capture_manifest(
    geo: Geography,
    manifest: CaptureManifest | Path,
    *,
    land: bool,
    chatlas_root: Path | None = None,
    model_loader: ModelLoader | None = None,
    reader_loader: ReaderLoader | None = None,
    limit: int = 20,
) -> ManifestCaptureReport:
    if limit < 0:
        raise ValueError("capture report limit must be non-negative")
    parsed = load_capture_manifest(manifest) if isinstance(manifest, Path) else manifest
    raw_model_loader = model_loader or (
        lambda identity: provide_normal_model(
            identity_hash=identity,
            chatlas_root=chatlas_root,
        )
    )
    raw_reader_loader = reader_loader or (
        lambda identity: provide_normal_model_reader(
            identity_hash=identity,
            chatlas_root=chatlas_root,
        )
    )
    model_cache: dict[str, dict[str, object]] = {}
    reader_cache: dict[str, object] = {}

    def load_model(identity: str) -> dict[str, object]:
        if identity not in model_cache:
            model_cache[identity] = raw_model_loader(identity)
        return model_cache[identity]

    def load_reader(identity: str) -> object:
        if identity not in reader_cache:
            reader_cache[identity] = raw_reader_loader(identity)
        return reader_cache[identity]

    prepared = _prepare_capture(
        geo,
        parsed,
        chatlas_root=chatlas_root,
        model_loader=load_model,
        reader_loader=load_reader,
    )
    if not land:
        return _preview_report(geo, prepared, limit=limit)

    registered = lossless_anchory_batch_register(
        items=_anchory_items(parsed),
        chatlas_root=chatlas_root,
        model_loader=prepared.model_loader,
    )
    anchors = {
        str(item["client_id"]): str(item["anchor"]) for item in registered["items"]
    }
    plan = _chat_index_plan(prepared, anchors)
    validation = validate_chat_index_capture_plan(
        plan,
        chatlas_root=chatlas_root,
        reader_loader=prepared.reader_loader,
    )
    source_changes = _patch_sources(geo, prepared, anchors)
    record_changes = _land_records(geo, prepared, registered)
    chat_index = apply_chat_index_capture_plan(
        plan,
        chatlas_root=chatlas_root,
        reader_loader=prepared.reader_loader,
    )
    audit = _audit_capture(geo, prepared, anchors, chat_index)
    if not audit["ok"]:
        raise CliError("Capture.Manifest final audit failed")
    all_items = tuple(
        _item_report(item, anchor=anchors[item.item.client_id], mode="land")
        for item in prepared.items
    )
    return ManifestCaptureReport(
        mode="land",
        manifest=str(parsed.path) if parsed.path else None,
        project_root=str(geo.project_root),
        status="ok",
        item_count=len(all_items),
        items=all_items[:limit],
        effects={
            "anchors": {
                "minted": registered["minted_count"],
                "reused": registered["reused_count"],
            },
            "sources": source_changes,
            "records": record_changes,
            "chat_index": {
                "changed": chat_index.get("changed", False),
                "head_only_gaps": len(validation["head_only_gaps"]),
            },
        },
        audit=audit,
    )


def _prepare_capture(
    geo: Geography,
    manifest: CaptureManifest,
    *,
    chatlas_root: Path | None,
    model_loader: ModelLoader,
    reader_loader: ReaderLoader,
) -> PreparedCapture:
    models: dict[str, dict[str, object]] = {}
    messages_by_session: dict[str, list[dict[str, object]]] = {}
    positions_by_session: dict[str, dict[str, int]] = {}
    resolved_messages: dict[
        tuple[str, str, str], tuple[dict[str, object], str, int]
    ] = {}
    message_positions: dict[tuple[str, str], int] = {}
    message_texts: dict[tuple[str, str, str], str] = {}

    def resolve(ref: CaptureMessageRef, *, side: str, field: str) -> None:
        if ref.session not in models:
            models[ref.session] = model_loader(ref.session)
        model = models[ref.session]
        if ref.session not in messages_by_session:
            messages = list_chat_messages(model)
            messages_by_session[ref.session] = messages
            positions_by_session[ref.session] = {
                str(message.get("message_address")): index
                for index, message in enumerate(messages)
            }
        messages = messages_by_session[ref.session]
        key = (ref.session, ref.message_address, ref.message_hash)
        resolved = resolved_messages.get(key)
        if resolved is None:
            result = resolve_chat_message_ref(
                messages,
                {
                    "message_address": ref.message_address,
                    "message_hash": ref.message_hash,
                },
            )
            if result["standing"] != "MATCHED":
                raise CliError(f"Capture.Manifest {field} is {result['standing']}")
            message = result["message"]
            if not isinstance(message, dict):
                raise CliError(f"Capture.Manifest {field} has no message")
            text = message.get("text")
            if not isinstance(text, str):
                raise CliError(f"Capture.Manifest {field} has no text")
            position = positions_by_session[ref.session].get(ref.message_address)
            if position is None:
                raise CliError(f"Capture.Manifest {field} has no message position")
            resolved = (message, text, position)
            resolved_messages[key] = resolved
        message, text, position = resolved
        if message.get("side") != side:
            actual = message.get("side") if isinstance(message, dict) else None
            raise CliError(
                f"Capture.Manifest {field} must resolve to {side}; got {actual!r}"
            )
        normalized = _normalized(text)
        missing = [
            part for part in ref.contains_all if _normalized(part) not in normalized
        ]
        if missing:
            raise CliError(
                f"Capture.Manifest {field} failed expect.contains_all: {missing!r}"
            )
        message_texts[key] = text
        message_positions[(ref.session, ref.message_address)] = position
        if ref.at_hint is not None:
            actual_at = chat_message_at(model, message)
            if actual_at is None:
                raise CliError(
                    f"Capture.Manifest {field} timestamp hint cannot be checked"
                )

    for item in manifest.items:
        for position, ref in enumerate(item.support):
            resolve(ref, side="user", field=f"{item.client_id}.support[{position}]")
        for position, gate in enumerate(item.gates):
            if gate.proposal is not None:
                resolve(
                    gate.proposal,
                    side="agent",
                    field=f"{item.client_id}.{gate.kind}[{position}].proposal",
                )
            resolve(
                gate.approval,
                side="user",
                field=f"{item.client_id}.{gate.kind}[{position}].approval",
            )
            if gate.proposal is not None:
                if gate.proposal.session != gate.approval.session:
                    raise CliError(
                        f"Capture.Manifest {item.client_id} gate spans sessions"
                    )
                proposal_position = message_positions[
                    (gate.proposal.session, gate.proposal.message_address)
                ]
                approval_position = message_positions[
                    (gate.approval.session, gate.approval.message_address)
                ]
                if proposal_position >= approval_position:
                    raise CliError(
                        f"Capture.Manifest {item.client_id} approval must follow proposal"
                    )
                proposal_text = message_texts[
                    (
                        gate.proposal.session,
                        gate.proposal.message_address,
                        gate.proposal.message_hash,
                    )
                ]
                if _normalized(item.statement) not in _normalized(proposal_text):
                    raise CliError(
                        f"Capture.Manifest {item.client_id} proposal does not contain the line"
                    )
            if gate.token is not None:
                assert gate.proposal is not None
                proposal_text = message_texts[
                    (
                        gate.proposal.session,
                        gate.proposal.message_address,
                        gate.proposal.message_hash,
                    )
                ]
                approval_text = message_texts[
                    (
                        gate.approval.session,
                        gate.approval.message_address,
                        gate.approval.message_hash,
                    )
                ]
                if gate.token not in proposal_text or gate.token not in approval_text:
                    raise CliError(
                        f"Capture.Manifest {item.client_id} gate token is absent from proposal or approval"
                    )

    discovered = set(discover_surfaces(geo, geo.project_root))
    cached_lines: dict[tuple[str, str], list[SurfaceLine]] = {}
    selected: list[tuple[CaptureItem, SurfaceLine, str]] = []
    for item in manifest.items:
        surface = item.target.surface
        host_kind = "discovered"
        cache_key = (surface, host_kind)
        if surface not in discovered:
            scope = parse_scope(item.target.block)
            path = resolve_surface_path(surface, geo.project_root)
            if (
                path.suffix.lower() not in {".md", ".markdown"}
                or scope.kind is not ScopeKind.ANNOTATION
                or scope.file != surface
                or not scope.region
            ):
                raise CliError(
                    "Capture.Manifest target is neither discovered nor an explicit "
                    f"Markdown heading locator: {surface} {item.target.block}"
                )
            host_kind = "markdown-heading"
            cache_key = (surface, item.target.block)
        lines = cached_lines.setdefault(
            cache_key,
            _read_target_lines(geo, item, host_kind=host_kind),
        )
        matches = [
            line
            for line in lines
            if line.scope.address == item.target.block
            and line.line_type == item.line_type
            and line.body == item.body
        ]
        if len(matches) != 1:
            raise CliError(
                f"Capture.Manifest {item.client_id} target resolved {len(matches)} exact lines"
            )
        selected.append((item, matches[0], host_kind))

    selected_with_locations = [
        (
            item,
            line,
            host_kind,
            _source_lineno(geo, item, line, host_kind=host_kind),
        )
        for item, line, host_kind in selected
    ]
    physical_targets = [
        (item.target.surface, source_lineno)
        for item, _line, _host_kind, source_lineno in selected_with_locations
    ]
    if len(physical_targets) != len(set(physical_targets)):
        raise CliError(
            "Capture.Manifest cannot ground several Index lines on one physical source line"
        )

    anchor_preview = lossless_anchory_batch_preview(
        items=_anchory_items(manifest),
        chatlas_root=chatlas_root,
        model_loader=model_loader,
    )
    preview_by_id = {str(item["client_id"]): item for item in anchor_preview["items"]}
    prepared_items: list[PreparedItem] = []
    store = IndexStore(geo)
    records_by_label = {
        record.line.label: record for record in store.all() if record.line.label
    }
    for item, line, host_kind, source_lineno in selected_with_locations:
        anchor_item = preview_by_id[item.client_id]
        anchor = anchor_item.get("anchor")
        normalized_anchor = f"^{anchor}" if isinstance(anchor, str) else None
        if line.labels and (
            normalized_anchor is None or line.labels != (normalized_anchor,)
        ):
            raise CliError(
                f"Capture.Manifest {item.client_id} target already carries a different label"
            )
        existing_record = records_by_label.get(normalized_anchor)
        expected_support = tuple(
            SupportRef(
                archive="chat",
                session_id=ref.session,
                message_id=ref.message_address,
                message_hash=ref.message_hash,
            )
            for ref in item.support
        )
        expected_review = _record_review(item)
        expected_landing = _record_landing(item)
        if existing_record is not None and (
            existing_record.line.type != item.line_type
            or existing_record.line.body != item.body
            or existing_record.scope.address != item.target.block
            or not _support_compatible(existing_record.support, expected_support)
            or (
                bool(existing_record.review)
                and bool(expected_review)
                and existing_record.review != expected_review
            )
            or (
                existing_record.landing is not None
                and expected_landing is not None
                and existing_record.landing != expected_landing
            )
        ):
            raise CliError(
                f"Capture.Manifest {item.client_id} conflicts with LineRecord "
                f"{existing_record.id}"
            )
        prepared_items.append(
            PreparedItem(
                item=item,
                line=line,
                anchor_action=str(anchor_item["action"]),
                anchor=anchor if isinstance(anchor, str) else None,
                record_action=_record_action(
                    existing_record,
                    support=expected_support,
                    review=expected_review,
                    landing=expected_landing,
                ),
                host_kind=host_kind,
                source_lineno=source_lineno,
            )
        )
    surface = chat_index_surface_path(
        manifest.chat_index_session, chatlas_root=chatlas_root
    )
    reader = reader_loader(manifest.chat_index_session)
    metadata = getattr(reader, "metadata", None)
    reader_model = metadata.get("model") if isinstance(metadata, dict) else None
    reader_session = (
        reader_model.get("session") if isinstance(reader_model, dict) else None
    )
    if (
        not isinstance(reader_session, dict)
        or reader_session.get("identity_hash") != manifest.chat_index_session
    ):
        raise CliError(
            "Capture.Manifest chat_index.session resolved a different session"
        )
    return PreparedCapture(
        manifest=manifest,
        items=tuple(prepared_items),
        models=models,
        model_loader=model_loader,
        reader_loader=reader_loader,
        base_surface=surface_state(surface),
    )


def _anchory_items(manifest: CaptureManifest) -> list[dict[str, object]]:
    return [
        {
            "client_id": item.client_id,
            "line_content": item.line_content,
            "members": [ref.compact for ref in item.support],
            "gates": _gates_payload(item.gates),
            "predecessors": list(item.predecessors),
            "issue_context": list(item.issue_context),
        }
        for item in manifest.items
    ]


def _gates_payload(gates: tuple[CaptureGate, ...]) -> dict[str, list[dict[str, str]]]:
    payload: dict[str, list[dict[str, str]]] = {
        "semantic_approval": [],
        "tokenized_verbatim_approval": [],
    }
    for gate in gates:
        item = {"approval": gate.approval.compact}
        if gate.proposal is not None:
            item["proposal"] = gate.proposal.compact
        if gate.token is not None:
            item["token"] = gate.token
        payload[gate.kind].append(item)
    return payload


def _preview_report(
    geo: Geography, prepared: PreparedCapture, *, limit: int
) -> ManifestCaptureReport:
    all_items = tuple(
        _item_report(item, anchor=item.anchor, mode="preview")
        for item in prepared.items
    )
    return ManifestCaptureReport(
        mode="preview",
        manifest=str(prepared.manifest.path) if prepared.manifest.path else None,
        project_root=str(geo.project_root),
        status="ok",
        item_count=len(all_items),
        items=all_items[:limit],
        effects={
            "anchors": {
                "mint": sum(item.anchor_action == "mint" for item in prepared.items),
                "reuse": sum(item.anchor_action == "reuse" for item in prepared.items),
            },
            "sources": {
                "ground": sum(not item.line.labels for item in prepared.items),
                "existing": sum(bool(item.line.labels) for item in prepared.items),
            },
            "records": {
                "create": sum(
                    item.record_action == "create" for item in prepared.items
                ),
                "existing": sum(
                    item.record_action == "existing" for item in prepared.items
                ),
                "update_gates": sum(
                    "gates" in item.record_action for item in prepared.items
                ),
                "update_support": sum(
                    "support" in item.record_action for item in prepared.items
                ),
            },
            "chat_index": {"plan": len(prepared.items)},
        },
    )


def _support_compatible(
    existing: tuple[SupportRef, ...], expected: tuple[SupportRef, ...]
) -> bool:
    """Allow a matching legacy coordinate to gain, but never contradict, its hash."""

    if len(existing) != len(expected):
        return False
    return all(
        current.archive == target.archive
        and current.session_id == target.session_id
        and current.message_id == target.message_id
        and (
            current.message_hash is None
            or current.message_hash == target.message_hash
        )
        for current, target in zip(existing, expected, strict=True)
    )


def _record_action(
    record: LineRecord | None,
    *,
    support: tuple[SupportRef, ...],
    review: tuple[GateRef, ...],
    landing: GateRef | None,
) -> str:
    if record is None:
        return "create"
    updates: list[str] = []
    if record.support != support:
        updates.append("support")
    if (review and not record.review) or (landing and record.landing is None):
        updates.append("gates")
    return f"update-{'-and-'.join(updates)}" if updates else "existing"


def _item_report(
    item: PreparedItem, *, anchor: str | None, mode: str
) -> dict[str, object]:
    return {
        "client_id": item.item.client_id,
        "action": item.item.action,
        "surface": item.item.target.surface,
        "block": item.item.target.block,
        "line": item.item.line_content,
        "anchor_action": item.anchor_action
        if mode == "preview"
        else ("reused" if item.anchor else "minted"),
        "anchor": f"^{anchor}" if anchor else None,
        "record_action": item.record_action,
    }


def _patch_sources(
    geo: Geography,
    prepared: PreparedCapture,
    anchors: dict[str, str],
) -> dict[str, int]:
    by_surface: dict[str, list[PreparedItem]] = {}
    for item in prepared.items:
        by_surface.setdefault(item.item.target.surface, []).append(item)
    staged: dict[Path, str] = {}
    changed = existing = files_changed = 0
    for surface, items in by_surface.items():
        path = resolve_surface_path(surface, geo.project_root)
        source = path.read_text(encoding="utf-8")
        physical = source.splitlines(keepends=True)
        for prepared_item in items:
            item = prepared_item.item
            current = _read_target_lines(
                geo,
                item,
                host_kind=prepared_item.host_kind,
            )
            matches = [
                line
                for line in current
                if line.scope.address == item.target.block
                and line.line_type == item.line_type
                and line.body == item.body
            ]
            if len(matches) != 1:
                raise CliError(
                    f"Capture.Manifest {item.client_id} source changed after preflight"
                )
            line = matches[0]
            label = f"^{anchors[item.client_id]}"
            if line.labels == (label,):
                existing += 1
                continue
            if line.labels:
                raise CliError(
                    f"Capture.Manifest {item.client_id} source acquired another label"
                )
            position = prepared_item.source_lineno - 1
            ending = "\n" if physical[position].endswith("\n") else ""
            body = physical[position][:-1] if ending else physical[position]
            if not body.rstrip().endswith(item.statement):
                raise CliError(
                    f"Capture.Manifest {item.client_id} line is not the final construct "
                    "on its physical source line"
                )
            physical[position] = f"{body.rstrip()} {label}{ending}"
            changed += 1
        staged[path] = "".join(physical)
    for path, text in staged.items():
        if path.read_text(encoding="utf-8") != text:
            atomic_write_text(path, text)
            files_changed += 1
    return {"grounded": changed, "existing": existing, "files_changed": files_changed}


def _land_records(
    geo: Geography,
    prepared: PreparedCapture,
    registered: dict[str, object],
) -> dict[str, int]:
    results = {str(item["client_id"]): item for item in registered["items"]}
    store = IndexStore(geo)
    existing_by_label = {
        record.line.label: record for record in store.all() if record.line.label
    }
    staged: list[LineRecord] = []
    existing = updated_gates = updated_support = created = 0
    for prepared_item in prepared.items:
        item = prepared_item.item
        result = results[item.client_id]
        anchor = f"^{result['anchor']}"
        support = _record_support(result["record"])
        review = _record_review(item)
        landing = _record_landing(item)
        prior = existing_by_label.get(anchor)
        if prior is not None:
            if (
                prior.line.type != item.line_type
                or prior.line.body != item.body
                or prior.scope.address != item.target.block
                or not _support_compatible(prior.support, support)
            ):
                raise CliError(
                    f"Capture.Manifest {item.client_id} conflicts with LineRecord {prior.id}"
                )
            needs_support = prior.support != support
            needs_gates = (review and not prior.review) or (
                landing and prior.landing is None
            )
            if needs_support or needs_gates:
                updated_record = prior
                if needs_support:
                    updated_record = updated_record.with_support(support)
                    updated_support += 1
                if review and not updated_record.review:
                    updated_record = updated_record.with_review(*review)
                if landing and updated_record.landing is None:
                    updated_record = updated_record.with_landing(landing)
                if needs_gates:
                    updated_gates += 1
                staged.append(updated_record)
            else:
                existing += 1
            continue
        record = LineRecord.create(
            prepared_item.line.scope,
            item.line_type,
            item.body,
            support=support,
        ).relabel(anchor)
        if review:
            record = record.with_review(*review)
        if landing:
            record = record.with_landing(landing)
        staged.append(record)
        created += 1
    for record in staged:
        store.put(record)
    return {
        "created": created,
        "updated_gates": updated_gates,
        "updated_support": updated_support,
        "existing": existing,
    }


def _record_review(item: CaptureItem) -> tuple[GateRef, ...]:
    return tuple(
        GateRef(
            archive="chat",
            session_id=gate.approval.session,
            token=gate.token or "",
            user_turn_id=gate.approval.message_address,
            agent_turn_id=gate.proposal.message_address,
        )
        for gate in item.gates
        if gate.kind == "tokenized_verbatim_approval"
        and gate.proposal is not None
        and gate.token is not None
    )


def _record_landing(item: CaptureItem) -> GateRef | None:
    review = _record_review(item)
    return review[-1] if review else None


def _record_support(record: object) -> tuple[SupportRef, ...]:
    if not isinstance(record, dict):
        raise CliError("Capture.Manifest Anchory result has no dossier")
    relationships = record.get("relationships")
    support = relationships.get("support") if isinstance(relationships, dict) else None
    members = support.get("members") if isinstance(support, dict) else None
    if not isinstance(members, list) or not members:
        raise CliError("Capture.Manifest Anchory dossier has no support")
    if not all(isinstance(member, dict) for member in members):
        raise CliError("Capture.Manifest Anchory dossier support is malformed")
    return tuple(
        SupportRef(
            archive="chat",
            session_id=str(member["session"]),
            message_id=str(member["message_address"]),
            message_hash=str(member["message_hash"]),
        )
        for member in members
    )


def _chat_index_plan(prepared: PreparedCapture, anchors: dict[str, str]) -> CapturePlan:
    return CapturePlan(
        session={"identity_hash": prepared.manifest.chat_index_session},
        base_surface=prepared.base_surface,
        landed_lines=tuple(
            CapturePlanLine(
                client_id=item.item.client_id,
                concept=item.item.concept,
                line_content=item.item.line_content,
                anchor=anchors[item.item.client_id],
            )
            for item in prepared.items
        ),
        status="ready",
    )


def _audit_capture(
    geo: Geography,
    prepared: PreparedCapture,
    anchors: dict[str, str],
    chat_index: dict[str, object],
) -> dict[str, object]:
    store = IndexStore(geo)
    source_missing: list[str] = []
    record_missing: list[str] = []
    for prepared_item in prepared.items:
        item = prepared_item.item
        label = f"^{anchors[item.client_id]}"
        lines = _read_target_lines(
            geo,
            item,
            host_kind=prepared_item.host_kind,
        )
        if not any(
            line.scope.address == item.target.block
            and line.line_type == item.line_type
            and line.body == item.body
            and line.labels == (label,)
            for line in lines
        ):
            source_missing.append(item.client_id)
        record = store.by_label(label)
        expected_support = tuple(
            SupportRef(
                archive="chat",
                session_id=ref.session,
                message_id=ref.message_address,
                message_hash=ref.message_hash,
            )
            for ref in item.support
        )
        if (
            record is None
            or record.scope.address != item.target.block
            or record.line.type != item.line_type
            or record.line.body != item.body
            or record.support != expected_support
        ):
            record_missing.append(item.client_id)
        elif _record_review(item) and record.review != _record_review(item):
            record_missing.append(item.client_id)
        elif _record_landing(item) and record.landing != _record_landing(item):
            record_missing.append(item.client_id)
    chat_audit = chat_index.get("audit")
    chat_ok = bool(chat_index.get("already_applied")) or (
        isinstance(chat_audit, dict) and bool(chat_audit.get("ok"))
    )
    return {
        "ok": not source_missing and not record_missing and chat_ok,
        "source_missing": source_missing,
        "record_missing": record_missing,
        "chat_index": chat_audit if isinstance(chat_audit, dict) else {"ok": chat_ok},
    }


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _read_target_lines(
    geo: Geography,
    item: CaptureItem,
    *,
    host_kind: str,
) -> list[SurfaceLine]:
    path = resolve_surface_path(item.target.surface, geo.project_root)
    if host_kind == "discovered":
        return read_surface(path, item.target.surface)
    if host_kind == "markdown-heading":
        scope = parse_scope(item.target.block)
        assert scope.region is not None
        return read_markdown_heading_lines(
            path,
            item.target.surface,
            scope.region,
        )
    raise AssertionError(f"unknown capture host kind: {host_kind}")


def _source_lineno(
    geo: Geography,
    item: CaptureItem,
    line: SurfaceLine,
    *,
    host_kind: str,
) -> int:
    if host_kind != "discovered" or not item.target.surface.startswith("skw:"):
        return line.lineno
    path = resolve_surface_path(item.target.surface, geo.project_root)
    needle = f"--note {item.statement}"
    matches = [
        index
        for index, source in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        )
        if needle in source
    ]
    if len(matches) != 1:
        raise CliError(
            f"Capture.Manifest {item.client_id} resolved {len(matches)} physical SKW notes"
        )
    return matches[0]


def render_capture_report(report: ManifestCaptureReport) -> str:
    effects = report.effects
    anchors = effects.get("anchors", {})
    sources = effects.get("sources", {})
    records = effects.get("records", {})
    chat_index = effects.get("chat_index", {})
    lines = [
        f"capture {report.mode}: {report.status} — showing {len(report.items)} of "
        f"{report.item_count} line(s)",
        f"  anchors    {', '.join(f'{key} {value}' for key, value in anchors.items())}",
        f"  sources    {', '.join(f'{key} {value}' for key, value in sources.items())}",
        f"  records    {', '.join(f'{key} {value}' for key, value in records.items())}",
        f"  Chat.Index {', '.join(f'{key} {value}' for key, value in chat_index.items())}",
    ]
    for item in report.items:
        anchor = item.get("anchor") or "<mint>"
        lines.append(
            f"  {item['client_id']}  {anchor}  {item['surface']}  {item['block']}"
        )
    if report.audit is not None:
        lines.append(f"  audit       {'ok' if report.audit.get('ok') else 'FAILED'}")
    return "\n".join(lines)


__all__ = [
    "CAPTURE_MANIFEST_SCHEMA",
    "CaptureManifest",
    "ManifestCaptureReport",
    "capture_manifest",
    "load_capture_manifest",
    "parse_capture_manifest",
    "render_capture_report",
]
