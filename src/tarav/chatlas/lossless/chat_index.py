# $kw: --from Chat.Index --from Chat.Index.Delta --from Chat.Index.HEAD --from Line.Home --note [IMPL] real-time capture projects exact landed lines to Chat HEAD first and then appends stable Chat.Turn.Ref receipts when their support has a provable local horizon --supp ^c20260816-60u
# --note [CT] idempotency is decided by whether the requested projection is already satisfied, not by whether a caller retained an older base fingerprint ^c20260821-44u
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import shutil
from typing import Callable
from uuid import uuid4

from filelock import FileLock, Timeout

from tarav._core.errors import CliError
from tarav.index_model.label import parse_citation, split_trailing_address
from tarav._core.persistence import atomic_write_json
from tarav.chatlas.paths import CHAT_INDEX_SURFACES_ROOT, default_chatlas_root
from tarav.index_model import index_line_anchor_triplet_hash

from .anchory import (
    CHATLAS2_NAMESPACE,
    lossless_anchory_depot,
    parse_line_anchor_dossier,
)
from .chat_index_plan import (
    PLAN_FILENAME,
    CapturePlan,
    CapturePlanLine,
    capture_plan_payload,
    load_capture_plan,
)
from .normal_model import provide_normal_model_reader
from .turn_ref import chat_turn_ref


HEAD_FILENAME = "HEAD.md"
DELTA_DIRNAME = "deltas"
LOCK_ROOT = Path("chatlas2") / "locks" / "chat-index"
ReaderLoader = Callable[[str], object]


def chat_index_surface_path(
    identity_hash: str,
    *,
    chatlas_root: Path | None = None,
) -> Path:
    if not identity_hash:
        raise ValueError("identity_hash must be non-empty")
    return _root(chatlas_root) / CHAT_INDEX_SURFACES_ROOT / identity_hash


def surface_state(surface: Path) -> dict[str, object] | None:
    if not surface.exists():
        return None
    if not surface.is_dir():
        raise CliError(f"Chat.Index surface is not a directory: {surface}")
    files = sorted(
        str(path.relative_to(surface)) for path in surface.rglob("*") if path.is_file()
    )
    digest = sha256()
    for relative in files:
        content = (surface / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(content).digest())
        digest.update(b"\n")
    return {"files": files, "fingerprint": f"sha256:{digest.hexdigest()}"}


def scaffold_chat_index_capture_plan(
    *,
    stage: Path,
    session_id: str | None = None,
    identity_hash: str | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    reader = provide_normal_model_reader(
        session_id=session_id,
        identity_hash=identity_hash,
        chatlas_root=chatlas_root,
    )
    session = _reader_session(reader)
    stage = stage.expanduser().resolve()
    if stage.exists() and any(stage.iterdir()):
        raise CliError(f"lossless Capture.Plan stage is not empty: {stage}")
    stage.mkdir(parents=True, exist_ok=True)
    surface = chat_index_surface_path(
        session["identity_hash"], chatlas_root=chatlas_root
    )
    plan = CapturePlan(
        session=session,
        base_surface=surface_state(surface),
        landed_lines=(),
        status="draft",
    )
    path = stage / PLAN_FILENAME
    atomic_write_json(path, capture_plan_payload(plan), ensure_ascii=False)
    return {
        "status": "ok",
        "schema": capture_plan_payload(plan)["schema"],
        "session": session,
        "surface_path": str(surface),
        "plan_path": str(path),
        "base_surface": plan.base_surface,
    }


def validate_chat_index_capture_plan(
    plan: CapturePlan | Path,
    *,
    chatlas_root: Path | None = None,
    reader_loader: ReaderLoader | None = None,
) -> dict[str, object]:
    capture_plan = _coerce_plan(plan)
    if capture_plan.status != "ready":
        raise CliError("lossless Capture.Plan is draft; set status to 'ready'")
    identity = capture_plan.session["identity_hash"]
    load_reader = reader_loader or (
        lambda value: provide_normal_model_reader(
            identity_hash=value,
            chatlas_root=chatlas_root,
        )
    )
    target_reader = load_reader(identity)
    target_session = _reader_session(target_reader)
    if target_session["identity_hash"] != identity:
        raise CliError("lossless Capture.Plan resolved a different target session")
    turns = list(target_reader.iter_chat_turns())
    turn_positions = {
        str(turn.get("turn_address")): index for index, turn in enumerate(turns)
    }
    prepared: list[dict[str, object]] = []
    gaps: list[dict[str, str]] = []
    readers: dict[str, object] = {identity: target_reader}
    depot = lossless_anchory_depot(chatlas_root)
    for line in capture_plan.landed_lines:
        item = _prepare_line(
            line,
            target_identity=identity,
            target_reader=target_reader,
            turn_positions=turn_positions,
            readers=readers,
            reader_loader=load_reader,
            depot=depot,
        )
        prepared.append(item)
        reason = item.get("gap_reason")
        if isinstance(reason, str):
            gaps.append({"client_id": line.client_id, "reason": reason})
    eligible = [item for item in prepared if item.get("origin") is not None]
    horizon = None
    if eligible:
        latest = max(
            eligible,
            key=lambda item: int(item["origin"]["tape_position"]),
        )
        horizon = deepcopy(latest["origin"])
    for item in prepared:
        item["delta"] = horizon is not None and item.get("origin") is not None
    surface = chat_index_surface_path(identity, chatlas_root=chatlas_root)
    current_base = surface_state(surface)
    result: dict[str, object] = {
        "status": "ok",
        "session": target_session,
        "surface_path": str(surface),
        "base_surface": current_base,
        "horizon": horizon,
        "head_only_gaps": gaps,
        "lines": [
            {
                "client_id": item["line"].client_id,
                "concept": item["line"].concept,
                "line_content": item["line"].line_content,
                "anchor": item["line"].anchor,
                "predecessor_anchors": list(item["predecessor_anchors"]),
                "delta": item["delta"],
            }
            for item in prepared
        ],
        "already_applied": False,
    }
    # Idempotency is a property of the requested projection, not of whether the caller
    # happened to retain an older base fingerprint. A freshly composed Capture.Manifest
    # naturally observes the already-landed surface as its base on every retry.
    if _surface_satisfies(surface, result):
        result["already_applied"] = True
    elif current_base != capture_plan.base_surface:
        raise CliError("Chat.Index surface changed since scaffold")
    return result


def apply_chat_index_capture_plan(
    plan: CapturePlan | Path,
    *,
    chatlas_root: Path | None = None,
    reader_loader: ReaderLoader | None = None,
) -> dict[str, object]:
    capture_plan = _coerce_plan(plan)
    root = _root(chatlas_root)
    identity = capture_plan.session["identity_hash"]
    lock_path = root / LOCK_ROOT / f"{identity}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(lock_path, timeout=0):
            validation = validate_chat_index_capture_plan(
                capture_plan,
                chatlas_root=root,
                reader_loader=reader_loader,
            )
            if validation["already_applied"]:
                return {**validation, "changed": False}
            surface = Path(str(validation["surface_path"]))
            temporary = surface.parent / f".{surface.name}.apply-{uuid4().hex}"
            backup = surface.parent / f".{surface.name}.backup-{uuid4().hex}"
            surface.parent.mkdir(parents=True, exist_ok=True)
            try:
                if surface.is_dir():
                    shutil.copytree(surface, temporary)
                else:
                    temporary.mkdir()
                _apply_to_surface(temporary, validation)
                if surface_state(temporary) == surface_state(surface):
                    shutil.rmtree(temporary)
                    return {**validation, "changed": False}
                if surface.exists():
                    surface.rename(backup)
                try:
                    temporary.rename(surface)
                except Exception:
                    if backup.exists() and not surface.exists():
                        backup.rename(surface)
                    raise
                if backup.exists():
                    shutil.rmtree(backup)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
                if backup.exists() and surface.exists():
                    shutil.rmtree(backup)
            audit = _audit_surface(surface, validation)
            return {**validation, "changed": True, "audit": audit}
    except Timeout as exc:
        raise CliError(f"Chat.Index backpropagation is locked: {identity}") from exc


def _prepare_line(
    line: CapturePlanLine,
    *,
    target_identity: str,
    target_reader: object,
    turn_positions: dict[str, int],
    readers: dict[str, object],
    reader_loader: ReaderLoader,
    depot: object,
) -> dict[str, object]:
    resolution = depot.resolve(line.anchor, namespace=CHATLAS2_NAMESPACE)
    if resolution is None:
        raise CliError(f"lossless Capture.Plan anchor is missing: {line.anchor}")
    dossier = parse_line_anchor_dossier(resolution.record)
    expected = index_line_anchor_triplet_hash(line.line_content, line.anchor)
    if dossier["attachment"]["triplet_hash"] != expected:
        raise CliError(
            f"lossless Capture.Plan anchor does not attach its exact line: {line.anchor}"
        )
    members = dossier["relationships"]["support"]["members"]
    local_origins: list[dict[str, object]] = []
    support_drift = False
    for member in members:
        session = str(member["session"])
        reader = readers.get(session)
        if reader is None:
            try:
                reader = reader_loader(session)
            except Exception:
                support_drift = True
                continue
            readers[session] = reader
        records = list(
            reader.iter_chat_message_records(
                message_addresses=[str(member["message_address"])], limit=2
            )
        )
        if len(records) != 1:
            support_drift = True
            continue
        message = records[0].get("message")
        if (
            not isinstance(message, dict)
            or message.get("message_hash") != member["message_hash"]
            or message.get("side") != "user"
        ):
            support_drift = True
            continue
        if session != target_identity:
            continue
        turn = target_reader.find_chat_turn(
            message_address=str(member["message_address"])
        )
        if not isinstance(turn, dict):
            support_drift = True
            continue
        address = str(turn.get("turn_address"))
        if address not in turn_positions:
            support_drift = True
            continue
        local_origins.append(
            {
                "turn_ref": chat_turn_ref(turn),
                "tape_position": turn_positions[address],
                "at": _turn_at(target_reader, turn),
            }
        )
    if support_drift:
        gap_reason = "SUPPORT_DRIFT"
        origin = None
    elif not local_origins:
        gap_reason = "NO_TARGET_SESSION_SUPPORT"
        origin = None
    else:
        gap_reason = None
        origin = max(local_origins, key=lambda item: int(item["tape_position"]))
    return {
        "line": line,
        "predecessor_anchors": tuple(
            dossier["relationships"]["provenance"]["predecessor_anchors"]
        ),
        "origin": origin,
        "gap_reason": gap_reason,
    }


def _turn_at(reader: object, turn: dict[str, object]) -> str | None:
    refs = turn.get("event_refs")
    if not isinstance(refs, list) or not refs or not isinstance(refs[0], dict):
        return None
    address = refs[0].get("event_address")
    if not isinstance(address, str):
        return None
    events = list(reader.iter_events(addresses=[address]))
    if len(events) != 1:
        return None
    at = events[0].get("started_at")
    return at if isinstance(at, str) and at else None


def _apply_to_surface(surface: Path, validation: dict[str, object]) -> None:
    predecessors = {
        anchor for item in validation["lines"] for anchor in item["predecessor_anchors"]
    }
    additions = [
        (str(item["concept"]), _anchored_line(item)) for item in validation["lines"]
    ]
    _patch_document(
        surface / HEAD_FILENAME,
        heading="# Chat.Index.HEAD",
        additions=additions,
        predecessors=predecessors,
        horizon=validation["horizon"],
        is_head=True,
    )
    delta_lines = [item for item in validation["lines"] if item["delta"]]
    horizon = validation["horizon"]
    if not delta_lines or not isinstance(horizon, dict):
        return
    ref = horizon["turn_ref"]
    filename = f"{ref['turn_address']}-{ref['turn_hash']}.md"
    _patch_document(
        surface / DELTA_DIRNAME / filename,
        heading=f"# Chat.Index.Delta/{ref['turn_address']}",
        additions=[
            (str(item["concept"]), _anchored_line(item)) for item in delta_lines
        ],
        predecessors=set(),
        horizon=horizon,
        is_head=False,
    )


def _patch_document(
    path: Path,
    *,
    heading: str,
    additions: list[tuple[str, str]],
    predecessors: set[str],
    horizon: object,
    is_head: bool,
) -> None:
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != heading:
            raise CliError(f"Chat.Index file has an unexpected heading: {path}")
    else:
        lines = [heading]
    lines = [source for source in lines if (_line_anchor(source) not in predecessors)]
    if isinstance(horizon, dict):
        lines = _set_horizon(lines, horizon=horizon, is_head=is_head)
    for concept, anchored in additions:
        anchor = _line_anchor(anchored)
        existing = [source for source in lines if _line_anchor(source) == anchor]
        if existing:
            if existing != [anchored]:
                raise CliError(f"Chat.Index anchor has conflicting content: {anchor}")
            continue
        lines = _insert_in_block(lines, concept=concept, line=anchored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _set_horizon(
    lines: list[str], *, horizon: dict[str, object], is_head: bool
) -> list[str]:
    ref = horizon["turn_ref"]
    at = horizon.get("at")
    if is_head:
        prefix = "Evidence.Horizon:"
        hash_prefix = "Evidence.Horizon.Hash:"
    else:
        prefix = "Turn.Address:"
        hash_prefix = "Turn.Hash:"
    filtered = [
        line
        for line in lines
        if not line.startswith(prefix) and not line.startswith(hash_prefix)
    ]
    address_line = f"{prefix} `{ref['turn_address']}`"
    if isinstance(at, str) and at:
        address_line += f" @ {at}"
    metadata = [address_line, f"{hash_prefix} `{ref['turn_hash']}`"]
    return [filtered[0], "", *metadata, *filtered[1:]]


def _insert_in_block(lines: list[str], *, concept: str, line: str) -> list[str]:
    heading = f"## {concept}"
    try:
        start = lines.index(heading)
    except ValueError:
        result = list(lines)
        if result and result[-1] != "":
            result.append("")
        result.extend([heading, "", line])
        return result
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    insertion = end
    while insertion > start + 1 and lines[insertion - 1] == "":
        insertion -= 1
    result = list(lines)
    result.insert(insertion, line)
    return result


def _surface_satisfies(surface: Path, validation: dict[str, object]) -> bool:
    if not surface.is_dir():
        return False
    return _audit_surface(surface, validation)["ok"]


def _audit_surface(surface: Path, validation: dict[str, object]) -> dict[str, object]:
    head = surface / HEAD_FILENAME
    head_text = head.read_text(encoding="utf-8") if head.is_file() else ""
    missing_head = [
        str(item["client_id"])
        for item in validation["lines"]
        if _anchored_line(item) not in head_text.splitlines()
    ]
    missing_delta: list[str] = []
    horizon = validation["horizon"]
    if isinstance(horizon, dict):
        ref = horizon["turn_ref"]
        delta = surface / DELTA_DIRNAME / f"{ref['turn_address']}-{ref['turn_hash']}.md"
        delta_text = delta.read_text(encoding="utf-8") if delta.is_file() else ""
        missing_delta = [
            str(item["client_id"])
            for item in validation["lines"]
            if item["delta"] and _anchored_line(item) not in delta_text.splitlines()
        ]
    return {
        "ok": not missing_head and not missing_delta,
        "missing_head": missing_head,
        "missing_delta": missing_delta,
    }


def _anchored_line(item: dict[str, object]) -> str:
    return f"{item['line_content']} ^{item['anchor']}"


def _line_anchor(line: str) -> str | None:
    """The citation a chat-index line ends with, caretless, or `None`.

    A locator name at the end is not an anchor here -- a chat index records which index line
    a turn carries, and only a citation names one.
    """

    _text, address = split_trailing_address(line)
    citation = parse_citation(address) if address is not None else None
    return address.removeprefix("^") if citation is not None else None


def _reader_session(reader: object) -> dict[str, str]:
    metadata = getattr(reader, "metadata", None)
    model = metadata.get("model") if isinstance(metadata, dict) else None
    session = model.get("session") if isinstance(model, dict) else None
    if not isinstance(session, dict):
        raise CliError("Chatlas2 reader has no session metadata")
    identity = session.get("identity_hash")
    if not isinstance(identity, str) or not identity:
        raise CliError("Chatlas2 reader has no session identity_hash")
    return {
        key: str(value)
        for key, value in session.items()
        if key in {"identity_hash", "session_id", "provider"} and value is not None
    }


def _coerce_plan(plan: CapturePlan | Path) -> CapturePlan:
    return load_capture_plan(plan) if isinstance(plan, Path) else plan


def _root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


__all__ = [
    "apply_chat_index_capture_plan",
    "chat_index_surface_path",
    "scaffold_chat_index_capture_plan",
    "surface_state",
    "validate_chat_index_capture_plan",
]
