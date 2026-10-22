"""Generic Product.Surface transaction for registered Breadcrumb workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from tarav.l0._core.persistence import atomic_write_text

from .store import BreadcrumbError, BreadcrumbStore
from .workflows import BreadcrumbAnnotationWorkflow, PreparedAnnotation


# tarav.breadcrumb 8e22d670e075
# tarav.breadcrumb 81884a16846c
SURFACE_LANGUAGES = ("markdown", "python", "typescript", "json", "toml")
TYPESCRIPT_SUFFIXES = frozenset({".ts", ".tsx", ".mts", ".cts"})
UNSUPPORTED_LANGUAGE = "Breadcrumb surface language must be markdown, python, typescript, json or toml"


@dataclass(frozen=True, slots=True)
class BreadcrumbSurface:
    path: Path
    language: str
    text: str


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
    workflow: str
    breadcrumbs: tuple[SubmittedBreadcrumb, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "status": "ok",
            "workflow": self.workflow,
            "surface": str(self.surface),
            "language": self.language,
            "breadcrumbs": [item.to_json() for item in self.breadcrumbs],
        }


def submit_annotations(
    surface: str | Path,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
    language: str | None = None,
) -> SubmissionResult:
    """Retain workflow attachments and replace their provisional markers."""

    path = Path(surface).expanduser().resolve()
    if not path.is_file():
        raise BreadcrumbError(f"Surface is not a file: {path}")
    selected_language = language or infer_surface_language(path)
    document = BreadcrumbSurface(
        path=path,
        language=selected_language,
        text=path.read_text(encoding="utf-8"),
    )
    annotations = workflow.prepare(document, request)
    if not annotations:
        raise BreadcrumbError(
            f"Surface contains no active provisional markers for {workflow.name}"
        )
    _validate_annotations(document, annotations)

    # tarav.breadcrumb cc0bdfe5ce1f
    # Every label is settled before anything is observed or written, so a
    # collision leaves the surface and the new Breadcrumbs' positions untouched.
    labelled = []
    for annotation in annotations:
        breadcrumb_id = str(store.create().records.to_record()["id"])
        labelled.append((annotation, breadcrumb_id, store.label(breadcrumb_id)))

    original_lines = document.text.splitlines()
    rewritten = document.text.splitlines(keepends=True)
    submitted: list[SubmittedBreadcrumb] = []
    label_order = {item[1]: index for index, item in enumerate(labelled)}
    # Columns refer to the original text; replace right to left on each line.
    for annotation, breadcrumb_id, core_label in sorted(
        labelled, key=lambda item: (item[0].marker.line, -item[0].marker.start_column)
    ):
        rendered = render_surface_label(selected_language, core_label)
        marker = annotation.marker
        current = rewritten[marker.line - 1]
        ending = "\n" if current.endswith("\n") else ""
        body = current[:-1] if ending else current
        rewritten[marker.line - 1] = (
            body[: marker.start_column] + rendered + body[marker.end_column :] + ending
        )
        store.observe_position(
            breadcrumb_id,
            file=str(path),
            line=marker.line,
            previous_line=original_lines[marker.line - 2] if marker.line > 1 else None,
            next_line=(
                original_lines[marker.line]
                if marker.line < len(original_lines)
                else None
            ),
        )
        for attachment in workflow.attachments(annotation, breadcrumb_id):
            store.attach(breadcrumb_id, attachment)
        submitted.append(
            SubmittedBreadcrumb(
                breadcrumb_id,
                marker.line,
                annotation.provisional,
                core_label,
            )
        )
    atomic_write_text(path, "".join(rewritten))
    return SubmissionResult(
        path,
        selected_language,
        workflow.name,
        tuple(sorted(submitted, key=lambda item: label_order[item.id])),
    )


def infer_surface_language(path: Path) -> str:
    if path.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    if path.suffix.lower() == ".py":
        return "python"
    if path.suffix.lower() in TYPESCRIPT_SUFFIXES:
        return "typescript"
    if path.suffix.lower() in {".json", ".toml"}:
        return path.suffix.lower()[1:]
    raise BreadcrumbError(
        f"Cannot infer surface language from {path.suffix or '<no extension>'}; "
        "provide --language"
    )


def render_surface_label(language: str, label: str) -> str:
    if language == "markdown":
        return f"<!-- {label} -->"
    if language in ("python", "toml"):
        return f"# {label}"
    if language == "json":
        return json.dumps(label)
    if language == "typescript":
        return f"// {label}"
    raise BreadcrumbError(UNSUPPORTED_LANGUAGE)


def _validate_annotations(
    surface: BreadcrumbSurface,
    annotations: tuple[PreparedAnnotation, ...],
) -> None:
    lines = surface.text.splitlines()
    occupied: dict[int, list[tuple[int, int]]] = {}
    for annotation in annotations:
        marker = annotation.marker
        if marker.line < 1 or marker.line > len(lines):
            raise BreadcrumbError("Breadcrumb workflow returned an invalid marker line")
        spans = occupied.setdefault(marker.line, [])
        if any(marker.start_column < end and start < marker.end_column
               for start, end in spans):
            raise BreadcrumbError(
                "Breadcrumb marker spans must not overlap"
            )
        spans.append((marker.start_column, marker.end_column))
        line = lines[marker.line - 1]
        if not 0 <= marker.start_column < marker.end_column <= len(line):
            raise BreadcrumbError("Breadcrumb workflow returned an invalid marker span")


__all__ = [
    "SURFACE_LANGUAGES",
    "TYPESCRIPT_SUFFIXES",
    "UNSUPPORTED_LANGUAGE",
    "BreadcrumbSurface",
    "SubmissionResult",
    "SubmittedBreadcrumb",
    "infer_surface_language",
    "render_surface_label",
    "submit_annotations",
]
