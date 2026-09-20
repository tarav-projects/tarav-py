"""Named surface workflows that submit provisional Breadcrumb annotations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from tarav._core.persistence import atomic_write_text
from tarav.chatlas.normal_model import provide_normal_model_reader
from tarav.chatlas.query import ChatlasQuery, ChatlasQueryEngine
from tarav.chatlas.references import ChatlasTurnReference
from tarav.surfaces.markdown import normalize_markdown
from tarav.surfaces.python import normalize_python

from .model import ChatlasContextAttachment
from .store import BreadcrumbError, BreadcrumbStore, breadcrumb_label


JsonObject = dict[str, Any]
TurnResolver = Callable[[str, str], Mapping[str, object]]
_CONTEXT_CORE = r"tarav\.context\s+([0-9a-f]{8}):([0-9a-f]{1,64})"
_MARKDOWN_CONTEXT = re.compile(rf"^(\s*)<!--\s*{_CONTEXT_CORE}\s*-->\s*$")
_PYTHON_CONTEXT = re.compile(rf"#\s*{_CONTEXT_CORE}\s*$")
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
class ProvisionalMarker:
    line: int
    start_column: int
    end_column: int
    alias: str
    turn_prefix: str


@dataclass(frozen=True, slots=True)
class SubmittedBreadcrumb:
    id: str
    line: int
    provisional: str
    label: str

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id,
            "line": self.line,
            "provisional": self.provisional,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    surface: Path
    language: str
    breadcrumbs: tuple[SubmittedBreadcrumb, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "status": "ok",
            "workflow": "Tarav.Breadcrumbs.ChatlasContext",
            "surface": str(self.surface),
            "language": self.language,
            "breadcrumbs": [item.to_json() for item in self.breadcrumbs],
        }


def submit_chatlas_context(
    surface: str | Path,
    *,
    store: BreadcrumbStore,
    language: str | None = None,
    provider: str | None = None,
    session_id: str | None = None,
    instance: str | None = None,
    chatlas_root: Path | None = None,
    resolver: TurnResolver | None = None,
) -> SubmissionResult:
    """Resolve every active marker, retain records, then atomically rewrite."""

    # tarav.breadcrumb 401522e18f57355da5c10b9d38989d195a40cd608ba515511070efa3562bfe2b
    path = Path(surface).expanduser().resolve()
    if not path.is_file():
        raise BreadcrumbError(f"Surface is not a file: {path}")
    selected_language = language or _infer_language(path)
    text = path.read_text(encoding="utf-8")
    declarations = _markdown_sessions(text) if selected_language == "markdown" else {}
    markers = _markers(text, selected_language)
    if not markers:
        raise BreadcrumbError("Surface contains no active provisional tarav.context markers")
    turn_records = (
        {(item.alias, item.turn_prefix): dict(resolver(item.alias, item.turn_prefix)) for item in markers}
        if resolver is not None
        else _resolve_chatlas_turns(
            markers,
            declarations=declarations,
            provider=provider,
            session_id=session_id,
            instance=instance,
            chatlas_root=chatlas_root,
        )
    )

    lines = text.splitlines(keepends=True)
    submitted: list[SubmittedBreadcrumb] = []
    for marker in markers:
        turn = turn_records[(marker.alias, marker.turn_prefix)]
        reference = ChatlasTurnReference.from_json(turn).to_json()
        breadcrumb = store.create()
        breadcrumb_id = str(breadcrumb.record["id"])
        core_label = breadcrumb_label(breadcrumb_id)
        rendered = (
            f"<!-- {core_label} -->"
            if selected_language == "markdown"
            else f"# {core_label}"
        )
        current = lines[marker.line - 1]
        ending = "\n" if current.endswith("\n") else ""
        body = current[:-1] if ending else current
        body = body[: marker.start_column] + rendered + body[marker.end_column :]
        lines[marker.line - 1] = body + ending
        source_lines = text.splitlines()
        store.observe_position(
            breadcrumb_id,
            file=str(path),
            line=marker.line,
            previous_line=source_lines[marker.line - 2] if marker.line > 1 else None,
            next_line=(
                source_lines[marker.line]
                if marker.line < len(source_lines)
                else None
            ),
        )
        attachment = {
            "type": ChatlasContextAttachment.type_name,
            "breadcrumb_id": breadcrumb_id,
            "workflow": "Tarav.Breadcrumbs.ChatlasContext",
            "context": reference,
        }
        ChatlasContextAttachment.from_json(attachment)
        store.attach(breadcrumb_id, attachment)
        submitted.append(
            SubmittedBreadcrumb(
                breadcrumb_id,
                marker.line,
                f"tarav.context {marker.alias}:{marker.turn_prefix}",
                core_label,
            )
        )
    atomic_write_text(path, "".join(lines))
    return SubmissionResult(path, selected_language, tuple(submitted))


def _infer_language(path: Path) -> str:
    if path.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    if path.suffix.lower() == ".py":
        return "python"
    raise BreadcrumbError(
        f"Cannot infer surface language from {path.suffix or '<no extension>'}; "
        "provide --language"
    )


def _markers(text: str, language: str) -> tuple[ProvisionalMarker, ...]:
    if language == "markdown":
        model = normalize_markdown(text)
        fenced = model.fenced_line_numbers()
        result = []
        for item in model.lines:
            if item.span.start_line in fenced:
                continue
            match = _MARKDOWN_CONTEXT.fullmatch(item.text)
            if match is not None:
                result.append(
                    ProvisionalMarker(
                        item.span.start_line,
                        len(match.group(1)),
                        len(item.text.rstrip()),
                        match.group(2),
                        match.group(3),
                    )
                )
        return tuple(result)
    if language == "python":
        model = normalize_python(text)
        if model.diagnostics:
            raise BreadcrumbError(
                "Python surface has normalization diagnostics: "
                + "; ".join(item.message for item in model.diagnostics)
            )
        result = []
        for comment in model.comments:
            match = _PYTHON_CONTEXT.fullmatch(comment.text)
            if match is not None:
                result.append(
                    ProvisionalMarker(
                        comment.span.start_line,
                        comment.span.start_column,
                        comment.span.end_column,
                        match.group(1),
                        match.group(2),
                    )
                )
        return tuple(result)
    raise BreadcrumbError("Breadcrumb surface language must be markdown or python")


def _markdown_sessions(text: str) -> dict[str, SessionDeclaration]:
    fenced = normalize_markdown(text).fenced_line_numbers()
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
                raise BreadcrumbError(f"Invalid tarav.sessions declaration: {line.strip()}")
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


def _resolve_chatlas_turns(
    markers: tuple[ProvisionalMarker, ...],
    *,
    declarations: Mapping[str, SessionDeclaration],
    provider: str | None,
    session_id: str | None,
    instance: str | None,
    chatlas_root: Path | None,
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
                chatlas_root=chatlas_root,
            )
        else:
            if provider is None or session_id is None:
                raise BreadcrumbError(
                    f"No tarav.sessions declaration for {alias}; provide --provider and --session-id"
                )
            if fallback_used:
                raise BreadcrumbError("One explicit session cannot resolve multiple undeclared aliases")
            fallback_used = True
            reader = provide_normal_model_reader(
                provider=provider,
                session_id=session_id,
                instance=instance,
                chatlas_root=chatlas_root,
            )
        result = ChatlasQueryEngine(reader).run(
            ChatlasQuery(turn_hash_prefixes=tuple(prefixes))
        )
        identity = result.session.get("identity_hash")
        if not isinstance(identity, str) or identity[:8] != alias:
            raise BreadcrumbError(f"Session alias {alias} does not match resolved Chatlas identity")
        for finding in result.findings:
            if finding.turn.get("side") != "user":
                raise BreadcrumbError(
                    f"Breadcrumb context must resolve to a User Turn: {finding.prefix}"
                )
            address = finding.turn.get("turn_address")
            turn_hash = finding.turn.get("turn_hash")
            records[(alias, finding.prefix)] = {
                "type": ChatlasTurnReference.type_name,
                "locator": {
                    "session_identity": identity,
                    "turn_address": address,
                    "turn_hash": turn_hash,
                },
            }
    return records


__all__ = [
    "ProvisionalMarker",
    "SessionDeclaration",
    "SubmissionResult",
    "SubmittedBreadcrumb",
    "submit_chatlas_context",
]
