"""Chatlas User-Turn integration for the Breadcrumb annotation framework."""

from __future__ import annotations

from tarav.l0.kernel import entity

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.l1.breadcrumbs import BreadcrumbError
from tarav.l1.breadcrumbs.auditing import (
    BreadcrumbAuditContext,
    BreadcrumbAuditConcern,
    ChatlasContextAttachmentInvalid,
    ChatlasContextAttachmentMissing,
    ChatlasContextAttachmentMultiple,
    ChatlasContextMarkerMalformed,
    ChatlasContextMarkerUnsubmitted,
    ChatlasContextTurnNotUser,
    ChatlasContextTurnUnavailable,
)
from tarav.l1.breadcrumbs.surfaces import UNSUPPORTED_LANGUAGE, BreadcrumbSurface
from tarav.l1.breadcrumbs.workflows import (
    BreadcrumbAnnotationWorkflow,
    PreparedAnnotation,
    SurfaceMarker,
)
from tarav.l1.chatlas.normal_model import compute_normal_model, provide_normal_model_reader
from tarav.l1.chatlas.normal_model import resolve_chat_turn_ref
from tarav.l1.chatlas.query import ChatlasQuery, ChatlasQueryEngine, ChatlasQueryError
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.surfaces.markdown import MarkdownNormalModel
from tarav.l1.surfaces.python import PythonNormalModel
from tarav.l1.surfaces.typescript import TypeScriptNormalModel

from .model import ChatlasContextAttachment


JsonObject = dict[str, Any]
TurnResolver = Callable[[str, str], Mapping[str, object]]
_CONTEXT_CORE = r"tarav\.context\s+([0-9a-f]{8}):([0-9a-f]{1,64})"
_MARKDOWN_CONTEXT = re.compile(rf"^(\s*)<!--\s*{_CONTEXT_CORE}\s*-->\s*$")
_PYTHON_CONTEXT = re.compile(rf"#\s*{_CONTEXT_CORE}\s*$")
_TYPESCRIPT_CONTEXT = re.compile(rf"//\s*{_CONTEXT_CORE}\s*$")
_SESSION_BLOCK = re.compile(r"<!--\s*tarav\.sessions\s*\n(.*?)\n\s*-->", re.DOTALL)
_SESSION_LINE = re.compile(
    r"^\s*([0-9a-f]{8})\s*=\s*([a-z0-9-]+):([^\s]+)\s+@([0-9a-f]{64})\s*$"
)


@dataclass(frozen=True, slots=True)
class SessionDeclaration:
    alias: str
    provider: str
    session_id: str
    identity_hash: str


@dataclass(frozen=True, slots=True)
class ChatlasContextMarker:
    position: SurfaceMarker
    alias: str
    turn_prefix: str


@dataclass(frozen=True, slots=True)
class ChatlasContextRequest:
    provider: str | None = None
    session_id: str | None = None
    instance: str | None = None
    chatlas_root: Path | None = None
    resolver: TurnResolver | None = None


class ChatlasContextBreadcrumbWorkflow(BreadcrumbAnnotationWorkflow):
    name = "chatlas-context"
    record_types = (ChatlasContextAttachment,)

    def prepare(
        self,
        surface: BreadcrumbSurface,
        request: object,
    ) -> tuple[PreparedAnnotation, ...]:
        if not isinstance(request, ChatlasContextRequest):
            raise TypeError("chatlas-context requires a ChatlasContextRequest")
        declarations = (
            _markdown_sessions(surface.text) if surface.language == "markdown" else {}
        )
        markers = provisional_markers(surface.text, surface.language)
        if request.resolver is not None:
            turn_records = {
                (item.alias, item.turn_prefix): dict(
                    request.resolver(item.alias, item.turn_prefix)
                )
                for item in markers
            }
        else:
            try:
                turn_records = _resolve_chatlas_turns(
                    markers,
                    declarations=declarations,
                    request=request,
                )
            except ChatlasQueryError as exc:
                raise BreadcrumbError(str(exc)) from exc
        return tuple(
            PreparedAnnotation(
                item.position,
                f"tarav.context {item.alias}:{item.turn_prefix}",
                ChatlasTurnReference.records.from_record(
                    turn_records[(item.alias, item.turn_prefix)]
                ).records.to_record(),
            )
            for item in markers
        )

    def attachments(
        self,
        annotation: PreparedAnnotation,
        breadcrumb_id: str,
    ) -> tuple[Mapping[str, object], ...]:
        attachment = {
            "type": entity(ChatlasContextAttachment).name,
            "breadcrumb_id": breadcrumb_id,
            "workflow": "Tarav.Breadcrumbs.ChatlasContext",
            "context": annotation.state,
        }
        return (ChatlasContextAttachment.records.from_record(attachment).records.to_record(),)

    def audit(
        self,
        context: BreadcrumbAuditContext,
        request: object,
    ) -> tuple[BreadcrumbAuditConcern, ...]:
        if not isinstance(request, ChatlasContextRequest):
            raise TypeError("chatlas-context requires a ChatlasContextRequest")
        concerns = [
            BreadcrumbAuditConcern(
                ChatlasContextMarkerUnsubmitted,
                "Active tarav.context marker was not submitted as a Breadcrumb.",
                line=marker.position.line,
            )
            for marker in provisional_markers(context.surface.text, context.surface.language)
        ]
        concerns.extend(
            BreadcrumbAuditConcern(
                ChatlasContextMarkerMalformed,
                "Surface comment contains a malformed tarav.context marker.",
                line=line,
            )
            for line in _malformed_marker_lines(
                context.surface.text,
                context.surface.language,
            )
        )

        models: dict[str, JsonObject] = {}
        for breadcrumb in context.breadcrumbs:
            attachments = [
                value
                for value in breadcrumb.attachments
                if value.get("type") == entity(ChatlasContextAttachment).name
            ]
            if not attachments:
                if breadcrumb.attachments:
                    concerns.append(
                        BreadcrumbAuditConcern(
                            ChatlasContextAttachmentMissing,
                            "Breadcrumb has no Chatlas-context attachment.",
                            breadcrumb.breadcrumb_id,
                            breadcrumb.line,
                        )
                    )
                continue
            if len(attachments) > 1:
                concerns.append(
                    BreadcrumbAuditConcern(
                        ChatlasContextAttachmentMultiple,
                        "Breadcrumb has multiple Chatlas-context attachments.",
                        breadcrumb.breadcrumb_id,
                        breadcrumb.line,
                    )
                )
                continue
            try:
                attachment = ChatlasContextAttachment.records.from_record(attachments[0])
                payload = attachment.records.to_record()
                if payload["breadcrumb_id"] != breadcrumb.breadcrumb_id:
                    raise ValueError(
                        "Chatlas-context attachment belongs to another Breadcrumb"
                    )
                reference = payload["context"]
                if not isinstance(reference, dict):
                    raise TypeError("Chatlas-context attachment has no Turn reference")
                locator = reference.get("locator")
                if not isinstance(locator, dict):
                    raise TypeError("Chatlas-context attachment has no Turn locator")
                identity = locator.get("session_identity")
                if not isinstance(identity, str):
                    raise TypeError("Chatlas Turn locator has no session identity")
                model = models.get(identity)
                if model is None:
                    model = compute_normal_model(
                        identity_hash=identity,
                        chatlas_root=request.chatlas_root,
                    )
                    models[identity] = model
                turns = model.get("turns")
                if not isinstance(turns, list):
                    raise TypeError("Chatlas Normal Model has no Turns collection")
                resolution = resolve_chat_turn_ref(turns, locator)
                standing = resolution.get("standing")
                if standing != "MATCHED":
                    concerns.append(
                        BreadcrumbAuditConcern(
                            ChatlasContextTurnUnavailable,
                            f"Retained Chatlas Turn is {standing}.",
                            breadcrumb.breadcrumb_id,
                            breadcrumb.line,
                        )
                    )
                    continue
                turn = resolution.get("turn")
                if not isinstance(turn, dict) or turn.get("side") != "user":
                    concerns.append(
                        BreadcrumbAuditConcern(
                            ChatlasContextTurnNotUser,
                            "Chatlas-context attachment does not resolve to a User Turn.",
                            breadcrumb.breadcrumb_id,
                            breadcrumb.line,
                        )
                    )
            except (CliError, OSError, TypeError, ValueError) as exc:
                concerns.append(
                    BreadcrumbAuditConcern(
                        ChatlasContextAttachmentInvalid,
                        str(exc),
                        breadcrumb.breadcrumb_id,
                        breadcrumb.line,
                    )
                )
        return tuple(concerns)


def provisional_markers(text: str, language: str) -> tuple[ChatlasContextMarker, ...]:
    """The active `tarav.context` markers of a text, by this workflow's convention for its language."""
    if language == "markdown":
        model = MarkdownNormalModel.from_text(text)
        fenced = model.fenced_line_numbers()
        result = []
        for item in model.lines:
            if item.span.start_line in fenced:
                continue
            match = _MARKDOWN_CONTEXT.fullmatch(item.text)
            if match is not None:
                result.append(
                    ChatlasContextMarker(
                        SurfaceMarker(
                            item.span.start_line,
                            len(match.group(1)),
                            len(item.text.rstrip()),
                        ),
                        match.group(2),
                        match.group(3),
                    )
                )
        return tuple(result)
    if language in ("python", "typescript"):
        _, pattern, comments = _code_comments(text, language)
        result = []
        for comment in comments:
            match = pattern.fullmatch(comment.text)
            if match is not None:
                result.append(
                    ChatlasContextMarker(
                        SurfaceMarker(
                            comment.span.start_line,
                            comment.span.start_column,
                            comment.span.end_column,
                        ),
                        match.group(1),
                        match.group(2),
                    )
                )
        return tuple(result)
    raise BreadcrumbError(UNSUPPORTED_LANGUAGE)


# tarav.breadcrumb 1677d0a1c26b
def _code_comments(text: str, language: str):
    """A code surface's comments that can hold a marker, and the marker pattern."""
    if language == "python":
        model, pattern, name = PythonNormalModel.from_text(text), _PYTHON_CONTEXT, "Python"
        comments = model.comments
    else:
        model, pattern, name = (TypeScriptNormalModel.from_text(text), _TYPESCRIPT_CONTEXT,
                                "TypeScript")
        comments = tuple(item for item in model.comments if item.kind == "line")
    if model.diagnostics:
        raise BreadcrumbError(
            f"{name} surface has normalization diagnostics: "
            + "; ".join(item.message for item in model.diagnostics)
        )
    return model, pattern, comments


def _malformed_marker_lines(text: str, language: str) -> tuple[int, ...]:
    candidates: list[tuple[int, str]] = []
    if language == "markdown":
        model = MarkdownNormalModel.from_text(text)
        fenced = model.fenced_line_numbers()
        candidates.extend(
            (item.span.start_line, item.text)
            for item in model.lines
            if item.span.start_line not in fenced
            and "<!--" in item.text
            and "tarav.context" in item.text
        )
        pattern = _MARKDOWN_CONTEXT
    elif language in ("python", "typescript"):
        _, pattern, comments = _code_comments(text, language)
        candidates.extend(
            (item.span.start_line, item.text)
            for item in comments
            if "tarav.context" in item.text
        )
    else:
        raise BreadcrumbError(UNSUPPORTED_LANGUAGE)
    return tuple(line for line, value in candidates if pattern.fullmatch(value) is None)


def _markdown_sessions(text: str) -> dict[str, SessionDeclaration]:
    fenced = MarkdownNormalModel.from_text(text).fenced_line_numbers()
    declarations: dict[str, SessionDeclaration] = {}
    for block in _SESSION_BLOCK.finditer(text):
        start_line = text.count("\n", 0, block.start()) + 1
        if start_line in fenced:
            continue
        for line in block.group(1).splitlines():
            if not line.strip():
                continue
            match = _SESSION_LINE.fullmatch(line)
            if match is None:
                raise BreadcrumbError(
                    f"Invalid tarav.sessions declaration: {line.strip()}"
                )
            declaration = SessionDeclaration(*match.groups())
            if declaration.alias != declaration.identity_hash[:8]:
                raise BreadcrumbError(
                    f"Session alias {declaration.alias} disagrees with its identity hash"
                )
            existing = declarations.get(declaration.alias)
            if existing is not None and existing != declaration:
                raise BreadcrumbError(f"Session alias is rebound: {declaration.alias}")
            declarations[declaration.alias] = declaration
    return declarations


# tarav.breadcrumb bd346b29e65f
def _resolve_chatlas_turns(
    markers: tuple[ChatlasContextMarker, ...],
    *,
    declarations: Mapping[str, SessionDeclaration],
    request: ChatlasContextRequest,
) -> dict[tuple[str, str], JsonObject]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for marker in markers:
        if marker.turn_prefix not in grouped[marker.alias]:
            grouped[marker.alias].append(marker.turn_prefix)
    records: dict[tuple[str, str], JsonObject] = {}
    fallback_used = False
    for alias, prefixes in grouped.items():
        declaration = declarations.get(alias)
        if declaration is not None:
            reader = provide_normal_model_reader(
                identity_hash=declaration.identity_hash,
                chatlas_root=request.chatlas_root,
            )
        else:
            if request.provider is None or request.session_id is None:
                raise BreadcrumbError(
                    f"No tarav.sessions declaration for {alias}; "
                    "provide --provider and --session-id"
                )
            if fallback_used:
                raise BreadcrumbError(
                    "One explicit session cannot resolve multiple undeclared aliases"
                )
            fallback_used = True
            reader = provide_normal_model_reader(
                provider=request.provider,
                session_id=request.session_id,
                instance=request.instance,
                chatlas_root=request.chatlas_root,
            )
        result = ChatlasQueryEngine(reader).run(
            ChatlasQuery(turn_hash_prefixes=tuple(prefixes))
        )
        identity = result.session.get("identity_hash")
        if not isinstance(identity, str) or identity[:8] != alias:
            raise BreadcrumbError(
                f"Session alias {alias} does not match resolved Chatlas identity"
            )
        for match in result.matches:
            if match.turn.get("side") != "user":
                raise BreadcrumbError(
                    f"Breadcrumb context must resolve to a User Turn: {match.prefix}"
                )
            records[(alias, match.prefix)] = {
                "type": entity(ChatlasTurnReference).name,
                "locator": {
                    "session_identity": identity,
                    "turn_address": match.turn.get("turn_address"),
                    "turn_hash": match.turn.get("turn_hash"),
                },
            }
    return records


__all__ = [
    "ChatlasContextBreadcrumbWorkflow",
    "ChatlasContextMarker",
    "ChatlasContextRequest",
    "SessionDeclaration",
    "TurnResolver",
]
