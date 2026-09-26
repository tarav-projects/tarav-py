"""Generic Product.Surface transaction for registered Breadcrumb workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarav._core.persistence import atomic_write_text

from .store import BreadcrumbError, BreadcrumbStore, breadcrumb_label
from .workflows import BreadcrumbAnnotationWorkflow, PreparedAnnotation


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

    original_lines = document.text.splitlines()
    rewritten = document.text.splitlines(keepends=True)
    submitted: list[SubmittedBreadcrumb] = []
    for annotation in annotations:
        breadcrumb = store.create()
        breadcrumb_id = str(breadcrumb.to_record()["id"])
        core_label = breadcrumb_label(breadcrumb_id)
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
        tuple(submitted),
    )


def infer_surface_language(path: Path) -> str:
    if path.suffix.lower() in {".md", ".markdown"}:
        return "markdown"
    if path.suffix.lower() == ".py":
        return "python"
    raise BreadcrumbError(
        f"Cannot infer surface language from {path.suffix or '<no extension>'}; "
        "provide --language"
    )


def render_surface_label(language: str, label: str) -> str:
    if language == "markdown":
        return f"<!-- {label} -->"
    if language == "python":
        return f"# {label}"
    raise BreadcrumbError("Breadcrumb surface language must be markdown or python")


def _validate_annotations(
    surface: BreadcrumbSurface,
    annotations: tuple[PreparedAnnotation, ...],
) -> None:
    lines = surface.text.splitlines()
    occupied: set[int] = set()
    for annotation in annotations:
        marker = annotation.marker
        if marker.line < 1 or marker.line > len(lines):
            raise BreadcrumbError("Breadcrumb workflow returned an invalid marker line")
        if marker.line in occupied:
            raise BreadcrumbError(
                "A surface line cannot contain multiple Breadcrumb markers"
            )
        occupied.add(marker.line)
        line = lines[marker.line - 1]
        if not 0 <= marker.start_column < marker.end_column <= len(line):
            raise BreadcrumbError("Breadcrumb workflow returned an invalid marker span")


__all__ = [
    "BreadcrumbSurface",
    "SubmissionResult",
    "SubmittedBreadcrumb",
    "infer_surface_language",
    "render_surface_label",
    "submit_annotations",
]
