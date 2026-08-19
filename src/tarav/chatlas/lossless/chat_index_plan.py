# $kw: --from Chat.Index --from Chat.Index.Delta --from Chat.Index.HEAD --from Index.Line --note [IMPL] the Chatlas2 real-time plan batches exact already-landed line identities while dossiers retain support and predecessor semantics --supp ^c20260816-60u
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from tarav._core.errors import CliError
from tarav.index_model import index_line_statement_parts


CAPTURE_PLAN_SCHEMA = "tarav.chatlas2.real-time-capture-plan.v1"
PLAN_FILENAME = "plan.json"
#: Anchors carry the `c` prefix of the one index-line namespace.
_ANCHOR = re.compile(r"c[0-9]{8}-[0-9]+[a-z]")
#: Any anchor sigil, whatever its prefix — this guards "the content must not already
#: carry one", which is true of a foreign prefix as much as the current one.
_ANY_ANCHOR_TOKEN = re.compile(r"\^[a-z][0-9]{8}-[0-9]+[a-z]?$")
_IDENTITY = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class CapturePlanLine:
    client_id: str
    concept: str
    line_content: str
    anchor: str


@dataclass(frozen=True, slots=True)
class CapturePlan:
    session: dict[str, str]
    base_surface: dict[str, object] | None
    landed_lines: tuple[CapturePlanLine, ...]
    status: str
    path: Path | None = None


def parse_capture_plan(value: object) -> CapturePlan:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "session",
        "base_surface",
        "landed_lines",
        "status",
    }:
        raise CliError("lossless Capture.Plan has an invalid top-level shape")
    if value.get("schema") != CAPTURE_PLAN_SCHEMA:
        raise CliError(
            f"lossless Capture.Plan requires schema {CAPTURE_PLAN_SCHEMA!r}"
        )
    session = value.get("session")
    if not isinstance(session, dict) or not set(session).issubset(
        {"identity_hash", "session_id", "provider"}
    ):
        raise CliError("lossless Capture.Plan session has an invalid shape")
    identity = session.get("identity_hash")
    if not isinstance(identity, str) or _IDENTITY.fullmatch(identity) is None:
        raise CliError("lossless Capture.Plan requires a full session identity_hash")
    parsed_session = {key: str(item) for key, item in session.items()}
    base_surface = _parse_base_surface(value.get("base_surface"))
    raw_lines = value.get("landed_lines")
    if not isinstance(raw_lines, list):
        raise CliError("lossless Capture.Plan landed_lines must be an array")
    lines: list[CapturePlanLine] = []
    client_ids: set[str] = set()
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict) or set(raw) != {
            "client_id",
            "concept",
            "line_content",
            "anchor",
        }:
            raise CliError(
                f"lossless Capture.Plan landed line {index} has an invalid shape"
            )
        client_id = raw.get("client_id")
        concept = raw.get("concept")
        line_content = raw.get("line_content")
        anchor = raw.get("anchor")
        if (
            not isinstance(client_id, str)
            or not client_id
            or client_id in client_ids
        ):
            raise CliError(
                f"lossless Capture.Plan landed line {index} has an invalid client_id"
            )
        if not isinstance(concept, str) or not concept.strip():
            raise CliError(
                f"lossless Capture.Plan landed line {client_id!r} has no concept"
            )
        if (
            not isinstance(line_content, str)
            or line_content != line_content.strip()
            or not line_content.startswith("- [")
        ):
            raise CliError(
                f"lossless Capture.Plan landed line {client_id!r} has invalid content"
            )
        try:
            index_line_statement_parts(line_content)
        except ValueError as exc:
            raise CliError(
                f"lossless Capture.Plan landed line {client_id!r} is not an Index.Line"
            ) from exc
        if any(_ANY_ANCHOR_TOKEN.match(token) for token in line_content.split()):
            raise CliError(
                f"lossless Capture.Plan landed line {client_id!r} content carries an anchor"
            )
        if not isinstance(anchor, str) or _ANCHOR.fullmatch(anchor) is None:
            raise CliError(
                f"lossless Capture.Plan landed line {client_id!r} has an invalid anchor"
            )
        client_ids.add(client_id)
        lines.append(
            CapturePlanLine(
                client_id=client_id,
                concept=concept.strip(),
                line_content=line_content,
                anchor=anchor,
            )
        )
    status = value.get("status")
    if status not in {"draft", "ready"}:
        raise CliError("lossless Capture.Plan status must be 'draft' or 'ready'")
    if status == "ready" and not lines:
        raise CliError("a ready lossless Capture.Plan requires landed lines")
    return CapturePlan(
        session=parsed_session,
        base_surface=base_surface,
        landed_lines=tuple(lines),
        status=str(status),
    )


def load_capture_plan(path: Path) -> CapturePlan:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"cannot read lossless Capture.Plan {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid lossless Capture.Plan JSON: {path}") from exc
    plan = parse_capture_plan(payload)
    return CapturePlan(
        session=plan.session,
        base_surface=plan.base_surface,
        landed_lines=plan.landed_lines,
        status=plan.status,
        path=path,
    )


def capture_plan_payload(plan: CapturePlan) -> dict[str, object]:
    return {
        "schema": CAPTURE_PLAN_SCHEMA,
        "session": dict(plan.session),
        "base_surface": plan.base_surface,
        "landed_lines": [
            {
                "client_id": line.client_id,
                "concept": line.concept,
                "line_content": line.line_content,
                "anchor": line.anchor,
            }
            for line in plan.landed_lines
        ],
        "status": plan.status,
    }


def _parse_base_surface(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"files", "fingerprint"}:
        raise CliError("lossless Capture.Plan base_surface has an invalid shape")
    files = value.get("files")
    fingerprint = value.get("fingerprint")
    if not isinstance(files, list) or not all(
        isinstance(item, str) and item for item in files
    ):
        raise CliError("lossless Capture.Plan base_surface files are invalid")
    if (
        not isinstance(fingerprint, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint) is None
    ):
        raise CliError("lossless Capture.Plan base_surface fingerprint is invalid")
    return {"files": list(files), "fingerprint": fingerprint}


__all__ = [
    "CAPTURE_PLAN_SCHEMA",
    "PLAN_FILENAME",
    "CapturePlan",
    "CapturePlanLine",
    "capture_plan_payload",
    "load_capture_plan",
    "parse_capture_plan",
]
