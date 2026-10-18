"""Inspect Breadcrumbs, optionally recording refreshed file positions."""

from __future__ import annotations

from collections.abc import Mapping
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult
from tarav.l1.poi import NotificationPOI, POI
from tarav.l1.surfaces.markdown import MarkdownNormalModel
from tarav.l1.surfaces.python import PythonNormalModel
from tarav.l1.surfaces.typescript import TypeScriptNormalModel
from tarav.l1.references.git import GitCommitMessagePositionTarget

from .store import (
    LABEL_PREFIX, BreadcrumbAmbiguous, BreadcrumbError, BreadcrumbPositionAmbiguous,
    BreadcrumbPositionMissing, BreadcrumbResolution, BreadcrumbResolutionPOI, BreadcrumbStore,
)
from .identity import BREADCRUMBS_WORKFLOW_SHIP
from .surfaces import UNSUPPORTED_LANGUAGE, BreadcrumbSurface, infer_surface_language
from .workflows import BreadcrumbAnnotationWorkflow


_BREADCRUMB_CORE = rf"tarav\.breadcrumb\s+([0-9a-f]{{{LABEL_PREFIX},64}})"
_MARKDOWN_BREADCRUMB = re.compile(rf"^\s*<!--\s*{_BREADCRUMB_CORE}\s*-->\s*$")
_PYTHON_BREADCRUMB = re.compile(rf"#\s*{_BREADCRUMB_CORE}\s*$")
_TYPESCRIPT_BREADCRUMB = re.compile(rf"//\s*{_BREADCRUMB_CORE}\s*$")


@dataclass(frozen=True, slots=True)
class SurfaceBreadcrumbLabel:
    """A label as a surface carries it: an ID prefix of 12 to 64 characters."""

    prefix: str
    line: int
    label: str


@dataclass(frozen=True, slots=True)
class BreadcrumbAuditConcern:
    """What an audit found, before the bound audit Check raises it: the POI Type
    that states it, and where. Transient input, never a retained POI.
    """

    poi: "type[BreadcrumbAuditPOI]"
    message: str
    breadcrumb_id: str | None = None
    line: int | None = None

@dataclass(frozen=True, slots=True)
class AuditedBreadcrumb:
    breadcrumb_id: str
    line: int
    label: str
    resolution: BreadcrumbResolution | None
    observations: tuple[Mapping[str, object], ...] = ()
    attachments: tuple[Mapping[str, object], ...] = ()

    def to_json(self) -> dict[str, object]:
        position: dict[str, object] | None = None
        status = "missing"
        if self.resolution is not None:
            status = self.resolution.status
            if hasattr(self.resolution.position, "path"):
                position = {
                    "file": str(self.resolution.position.path),
                    "line": self.resolution.position.line,
                    "text": self.resolution.position.text,
                }
            elif isinstance(
                self.resolution.position, GitCommitMessagePositionTarget
            ):
                position = {
                    "repository": str(self.resolution.position.repository),
                    "commit": self.resolution.position.commit,
                    "line": self.resolution.position.line,
                    "text": self.resolution.position.text,
                }
        return {
            "id": self.breadcrumb_id,
            "line": self.line,
            "label": self.label,
            "status": status,
            "position": position,
            "observations": [dict(item) for item in self.observations],
            "attachments": [dict(item) for item in self.attachments],
        }


@dataclass(frozen=True, slots=True)
class BreadcrumbAuditContext:
    surface: BreadcrumbSurface
    breadcrumbs: tuple[AuditedBreadcrumb, ...]


class BreadcrumbAuditPOI(CheckPOI):
    """Family, never raised: an audited surface and its retained Breadcrumbs disagree."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('fd78dc93-f719-4149-8ab8-f67933cd373e'),
                          name='Tarav.Breadcrumbs.Audit.POI', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class BreadcrumbRecordUnavailable(BreadcrumbAuditPOI):
    """A Breadcrumb's retained record cannot be read."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('27680081-5ca5-4f3a-b2f1-ed82f8e71756'),
                          name='Tarav.Breadcrumbs.Audit.POI.RecordUnavailable', workflow=BREADCRUMBS_WORKFLOW_SHIP)


# tarav.breadcrumb 488c9f0b9a18
class LabelAmbiguous(BreadcrumbAuditPOI):
    """A label's prefix matches several Breadcrumbs, so which one it names cannot be told.

    The message lists the colliding full IDs. Lengthening the label until it is
    unique, after choosing the intended Breadcrumb, is Agent or User work.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('b7fa6e78-b3f7-4f29-8caf-9d9e5aade182'),
                          name='Tarav.Breadcrumbs.Audit.POI.LabelAmbiguous', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class LabelWithoutPosition(BreadcrumbAuditPOI):
    """A label on the audited surface belongs to a Breadcrumb that no recorded position contains.

    The audit asks the store where the Breadcrumb is; this is the store's
    `Resolution.PositionMissing`, stated for one label on one line of one file.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('d28f9d43-1f76-46ef-aa36-2bb4a031331c'),
                          name='Tarav.Breadcrumbs.Audit.POI.LabelWithoutPosition', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class LabelWithSeveralPositions(BreadcrumbAuditPOI):
    """A label on the audited surface belongs to a Breadcrumb that several recorded positions
    contain, so which one is the Breadcrumb cannot be told.

    This is the store's `Resolution.PositionAmbiguous`, stated for one label
    on one line of one file.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('9f6b2541-e9af-4502-ac9f-dfced8bbe1c1'),
                          name='Tarav.Breadcrumbs.Audit.POI.LabelWithSeveralPositions', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class BreadcrumbPositionDisagrees(BreadcrumbAuditPOI):
    """A Breadcrumb's resolved position is not where the surface carries its label."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('f4876a51-b684-40e6-b71b-02834812e73b'),
                          name='Tarav.Breadcrumbs.Audit.POI.PositionDisagrees', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class BreadcrumbPositionRefreshFailed(BreadcrumbAuditPOI):
    """A Breadcrumb's new position could not be recorded."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('a58cd095-33fe-4fcd-9e89-d25d5ebfff1d'),
                          name='Tarav.Breadcrumbs.Audit.POI.PositionRefreshFailed', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class BreadcrumbAttachmentMissing(BreadcrumbAuditPOI):
    """A Breadcrumb has no retained workflow attachment."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('9dc4d2f8-6b04-4d62-95e2-ccf110715506'),
                          name='Tarav.Breadcrumbs.Audit.POI.AttachmentMissing', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class BreadcrumbLabelMalformed(BreadcrumbAuditPOI):
    """A surface comment holds a malformed Breadcrumb label."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('84b9c10a-cf29-46fd-902f-91fc0727a159'),
                          name='Tarav.Breadcrumbs.Audit.POI.LabelMalformed', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextAttachmentInvalid(BreadcrumbAuditPOI):
    """A Breadcrumb's Chatlas-context attachment is not valid."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('337c43f6-baba-4d70-98d6-186a7c994d7c'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.AttachmentInvalid', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextAttachmentMissing(BreadcrumbAuditPOI):
    """A Breadcrumb has no Chatlas-context attachment."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('de3581e8-c8ae-4c6a-892a-73cf9cfb1779'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.AttachmentMissing', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextAttachmentMultiple(BreadcrumbAuditPOI):
    """A Breadcrumb has more than one Chatlas-context attachment."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('eae73739-9882-479c-8d4b-b3d54e124b50'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.AttachmentMultiple', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextMarkerMalformed(BreadcrumbAuditPOI):
    """A surface holds a malformed provisional Chatlas-context marker."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('9a71ccec-b088-4d87-82c5-94dde4a42d1b'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.MarkerMalformed', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextMarkerUnsubmitted(BreadcrumbAuditPOI):
    """A surface holds a provisional Chatlas-context marker that was never submitted."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('8da2ecd6-94f0-4ab7-b3b4-e7a79eefa0e2'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.MarkerUnsubmitted', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextTurnNotUser(BreadcrumbAuditPOI):
    """A Breadcrumb's attached Chatlas Turn is not a User Turn."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('fb655512-0d52-4447-984c-66f61b01f788'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.TurnNotUser', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ChatlasContextTurnUnavailable(BreadcrumbAuditPOI):
    """A Breadcrumb's attached Chatlas Turn cannot be found."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('a92048e2-d762-4237-9fa0-ca6732fcc4cf'),
                          name='Tarav.Breadcrumbs.Audit.POI.ChatlasContext.TurnUnavailable', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class CommitEvidenceInvalid(BreadcrumbAuditPOI):
    """A commit message's evidence envelope is not valid."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('0b517ffc-5755-47b2-ba15-ca0fcaeb7d26'),
                          name='Tarav.Breadcrumbs.Audit.POI.CommitEvidence.Invalid', workflow=BREADCRUMBS_WORKFLOW_SHIP)


class CommitEvidenceRegistrationIncomplete(BreadcrumbAuditPOI):
    """A commit's Breadcrumb evidence was not fully registered."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('a8745c40-4bc2-482e-b1d8-faf88d5ea716'),
                          name='Tarav.Breadcrumbs.Audit.POI.CommitEvidence.RegistrationIncomplete', workflow=BREADCRUMBS_WORKFLOW_SHIP)


def audit_type(poi: BreadcrumbResolutionPOI) -> type[BreadcrumbAuditPOI]:
    """The audit's POI Type for what resolving a Breadcrumb found."""
    return {BreadcrumbPositionMissing: LabelWithoutPosition,
            BreadcrumbPositionAmbiguous: LabelWithSeveralPositions}[type(poi)]


class BreadcrumbPositionUpdated(NotificationPOI):
    """An audit recorded a Breadcrumb's refreshed file position."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('01cd56d7-2c07-42cc-8b97-4b6ae86c8e1e'),
                          name='Tarav.Breadcrumbs.Audit.PositionUpdated', workflow=BREADCRUMBS_WORKFLOW_SHIP)


# tarav.breadcrumb 43e2d650575b
class BreadcrumbAuditCheck(Check):
    """Run the owning workflow's audit and report its bounded concerns."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls,
                          id=TypeShip('6962e10b-d96d-4434-b647-9cb41165a7df'),
                          name='Tarav.Breadcrumbs.Audit.Check',
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)

    def __init__(self, context: BreadcrumbAuditContext,
                 concerns: tuple[BreadcrumbAuditConcern, ...],
                 workflow: BreadcrumbAnnotationWorkflow, request: object):
        super().__init__()
        self.audit_context = context
        self.concerns = concerns
        self.annotation_workflow = workflow
        self.request = request

    def _run(self) -> CheckResult:
        concerns = (*self.concerns, *self.annotation_workflow.audit(
            self.audit_context, self.request))

        def poi(item):
            details = {'surface': str(self.audit_context.surface.path),
                       **({'breadcrumb_id': item.breadcrumb_id}
                          if item.breadcrumb_id else {}),
                       **({'line': item.line} if item.line is not None else {})}
            return item.poi(self, item.message, situation=details, details=details)

        return CheckResult(self, status='completed', pois=(
            poi(item) for item in concerns
        ))

@dataclass(frozen=True, slots=True)
# tarav.breadcrumb f30f87cf9b4f
class BreadcrumbAuditResult:
    context: BreadcrumbAuditContext
    workflow: str
    pois: tuple[POI, ...] = ()

    @classmethod
    def from_concerns(cls, context: BreadcrumbAuditContext,
                      workflow: BreadcrumbAnnotationWorkflow, request: object,
                      concerns: tuple[BreadcrumbAuditConcern, ...],
                      updates: tuple[Mapping[str, object], ...] = ()) -> 'BreadcrumbAuditResult':
        checked = BreadcrumbAuditCheck(context, concerns, workflow, request).run().pois()
        notifications = tuple(BreadcrumbPositionUpdated(
            'Breadcrumb position observation appended.',
            details=dict(update)) for update in updates)
        return cls(context, workflow.name, (*checked, *notifications))

    @property
    def check_pois(self) -> tuple[CheckPOI, ...]:
        return tuple(poi for poi in self.pois if isinstance(poi, CheckPOI))

    @property
    def notifications(self) -> tuple[NotificationPOI, ...]:
        return tuple(poi for poi in self.pois if isinstance(poi, NotificationPOI))

    @property
    def ok(self) -> bool:
        return not any(poi.failure for poi in self.check_pois)

    def to_json(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "pois",
            "workflow": self.workflow,
            "surface": str(self.context.surface.path),
            "language": self.context.surface.language,
            "breadcrumbs": [item.to_json() for item in self.context.breadcrumbs],
            "pois": [item.records.to_record() for item in self.pois],
        }


def audit_annotations(
    surface: str | Path,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
    language: str | None = None,
    refresh_positions: bool = False,
) -> BreadcrumbAuditResult:
    """Audit without mutation by default.

    Opt-in refresh appends uniquely observed, stale locations to the store;
    it never edits the surface, identity or attachments. Updates are informational,
    not findings. Ambiguous positions and failed writes remain warnings.
    """
    path = Path(surface).expanduser().resolve()
    if not path.is_file():
        raise BreadcrumbError(f"Surface is not a file: {path}")
    document = BreadcrumbSurface(
        path,
        language or infer_surface_language(path),
        path.read_text(encoding="utf-8"),
    )
    labels, findings = _surface_labels(document)
    found = {label.prefix: find_label(store, label, findings) for label in labels}
    counts = Counter(found.get(label.prefix) for label in labels)
    updates: list[Mapping[str, object]] = []
    audited: list[AuditedBreadcrumb] = []
    for label in labels:
        breadcrumb_id = found[label.prefix]
        if breadcrumb_id is None:
            audited.append(AuditedBreadcrumb(label.prefix, label.line, label.label, None))
            continue
        resolution: BreadcrumbResolution | None = None
        observations: tuple[Mapping[str, object], ...] = ()
        attachments: tuple[Mapping[str, object], ...] = ()
        try:
            resolution = store.resolve(breadcrumb_id)
            if refresh_positions and counts[breadcrumb_id] == 1 and (
                resolution.status == "unresolvable"
            ):
                try:
                    store.observe_position(breadcrumb_id, file=str(path), line=label.line)
                except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
                    findings.append(BreadcrumbAuditConcern(
                        BreadcrumbPositionRefreshFailed, str(exc),
                        breadcrumb_id, label.line))
                else:
                    updates.append({"breadcrumb_id": breadcrumb_id,
                                    "file": str(path), "line": label.line})
                    resolution = store.resolve(breadcrumb_id)
            observations = store.observations(breadcrumb_id)
            attachments = store.attachments(breadcrumb_id)
        except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
            findings.append(
                BreadcrumbAuditConcern(
                    BreadcrumbRecordUnavailable,
                    str(exc),
                    breadcrumb_id,
                    label.line,
                )
            )
        else:
            for poi in resolution.pois:
                findings.append(
                    BreadcrumbAuditConcern(
                        audit_type(poi),
                        poi.message,
                        breadcrumb_id,
                        label.line,
                    )
                )
            if resolution.position is not None and (
                resolution.position.path.resolve() != path
                or resolution.position.line != label.line
            ):
                findings.append(
                    BreadcrumbAuditConcern(
                        BreadcrumbPositionDisagrees,
                        "Resolved Breadcrumb position disagrees with this surface label.",
                        breadcrumb_id,
                        label.line,
                    )
                )
            if not attachments:
                findings.append(
                    BreadcrumbAuditConcern(
                        BreadcrumbAttachmentMissing,
                        "Breadcrumb has no retained workflow attachment.",
                        breadcrumb_id,
                        label.line,
                    )
                )
        audited.append(
            AuditedBreadcrumb(
                breadcrumb_id,
                label.line,
                label.label,
                resolution,
                observations,
                attachments,
            )
        )
    context = BreadcrumbAuditContext(document, tuple(audited))
    return BreadcrumbAuditResult.from_concerns(
        context, workflow, request, tuple(findings), tuple(updates))


def find_label(store: BreadcrumbStore, label: SurfaceBreadcrumbLabel,
               findings: list[BreadcrumbAuditConcern]) -> str | None:
    """The full ID a surface label names, or None after recording why not."""
    try:
        return store.find(label.prefix)
    except BreadcrumbAmbiguous as exc:
        findings.append(BreadcrumbAuditConcern(LabelAmbiguous, str(exc), line=label.line))
    except (BreadcrumbError, OSError) as exc:
        findings.append(BreadcrumbAuditConcern(BreadcrumbRecordUnavailable, str(exc),
                                               label.prefix, label.line))
    return None


def _surface_labels(
    surface: BreadcrumbSurface,
) -> tuple[tuple[SurfaceBreadcrumbLabel, ...], list[BreadcrumbAuditConcern]]:
    candidates: list[tuple[int, str]] = []
    if surface.language == "markdown":
        model = MarkdownNormalModel.from_text(surface.text)
        fenced = model.fenced_line_numbers()
        candidates.extend(
            (item.span.start_line, item.text)
            for item in model.lines
            if item.span.start_line not in fenced
            and "<!--" in item.text
            and "tarav.breadcrumb" in item.text
        )
        pattern = _MARKDOWN_BREADCRUMB
    elif surface.language == "python":
        model = PythonNormalModel.from_text(surface.text)
        if model.diagnostics:
            raise BreadcrumbError(
                "Python surface has normalization diagnostics: "
                + "; ".join(item.message for item in model.diagnostics)
            )
        candidates.extend(
            (item.span.start_line, item.text)
            for item in model.comments
            if "tarav.breadcrumb" in item.text
        )
        pattern = _PYTHON_BREADCRUMB
    elif surface.language == "typescript":
        model = TypeScriptNormalModel.from_text(surface.text)
        if model.diagnostics:
            raise BreadcrumbError(
                "TypeScript surface has normalization diagnostics: "
                + "; ".join(item.message for item in model.diagnostics)
            )
        candidates.extend(
            (item.span.start_line, item.text)
            for item in model.comments
            if item.kind == "line" and "tarav.breadcrumb" in item.text
        )
        pattern = _TYPESCRIPT_BREADCRUMB
    else:
        raise BreadcrumbError(UNSUPPORTED_LANGUAGE)

    labels: list[SurfaceBreadcrumbLabel] = []
    findings: list[BreadcrumbAuditConcern] = []
    for line, text in candidates:
        match = pattern.fullmatch(text)
        if match is None:
            findings.append(
                BreadcrumbAuditConcern(
                    BreadcrumbLabelMalformed,
                    "Surface comment contains a malformed Breadcrumb label.",
                    line=line,
                )
            )
            continue
        prefix = match.group(1)
        labels.append(SurfaceBreadcrumbLabel(prefix, line, f"tarav.breadcrumb {prefix}"))
    return tuple(labels), findings


def surface_labels(
    surface: BreadcrumbSurface,
) -> tuple[tuple[SurfaceBreadcrumbLabel, ...], list[BreadcrumbAuditConcern]]:
    """Parse exact Breadcrumb labels from an already loaded surface."""

    return _surface_labels(surface)


__all__ = [
    "AuditedBreadcrumb",
    "BreadcrumbAuditContext",
    "BreadcrumbAuditConcern",
    "BreadcrumbAuditResult",
    "SurfaceBreadcrumbLabel",
    "audit_annotations",
    "find_label",
    "surface_labels",
]
