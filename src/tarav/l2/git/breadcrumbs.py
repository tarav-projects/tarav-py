"""Git commits whose messages retain recoverable Breadcrumb evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l0.kernel.records import _json_object
from tarav.l1.breadcrumbs import (
    LABEL_PREFIX,
    AuditedBreadcrumb,
    BreadcrumbAuditContext,
    BreadcrumbAuditConcern,
    BreadcrumbAuditResult,
    BreadcrumbError,
    BreadcrumbPositionMissing,
    BreadcrumbResolution,
    BreadcrumbStore,
    BreadcrumbSurface,
    breadcrumb_label,
)
from tarav.l1.breadcrumbs import auditing as audit
from tarav.l1.breadcrumbs.auditing import find_label, surface_labels
from tarav.l1.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow
from tarav.l1.git import GIT_WORKFLOW_SHIP, GitObject, GitRepository
from tarav.l1.references.git import GitCommitMessagePositionTarget
from tarav.l1.references.git import GitCommitMessagePositionReference


_CONTEXT = re.compile(
    r"^\s*<!--\s*tarav\.context\s+[0-9a-f]{8}:[0-9a-f]{1,64}\s*-->\s*$"
)
_BREADCRUMB = re.compile(
    rf"^\s*<!--\s*tarav\.breadcrumb\s+([0-9a-f]{{{LABEL_PREFIX},64}})\s*-->\s*$"
)
_EVIDENCE = re.compile(
    r"^\s*<!--\s*tarav\.evidence\s+(agent-initiated|unknown-session)\s*-->\s*$"
)
_ENVELOPE = re.compile(
    r"<!--\s*tarav\.commit-evidence\s*\n([^\n]+)\n\s*-->", re.MULTILINE
)


class CommitEvidenceError(BreadcrumbError):
    """A commit-evidence manifest or message is invalid."""


class CommitObservationError(CommitEvidenceError):
    """A commit exists but its Breadcrumb observations were not completed."""

    def __init__(self, commit: str, cause: Exception) -> None:
        self.commit = commit
        super().__init__(f"Commit {commit} exists; observation failed: {cause}")


class CommitManifest(GitObject):
    """Temporary declaration of one bounded evidence commit."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("12125c40-2508-46df-b342-805901f563af"),
            name="Tarav.Git.CommitEvidence.Manifest",
            workflow=GIT_WORKFLOW_SHIP,
        )

    class RecordInterface(GitObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Git.CommitEvidence.Manifest"]
        repository: str = Field(min_length=1)
        files: list[str]
        message: str = Field(min_length=1)
        allow_empty: bool = False

    @classmethod
    def load(cls, path: str | Path) -> "CommitManifest":
        source = Path(path).expanduser().resolve()
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommitEvidenceError(f"Cannot load commit manifest {source}: {exc}") from exc
        result = cls.records.from_record(payload)
        result.source = source
        return result

    class Records(GitObject.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "repository": ".",
                "files": [],
                "message": (
                    "Example evidence commit\n\n"
                    "- scope: example\n"
                    "<!-- tarav.evidence agent-initiated -->"
                ),
                "allow_empty": True,
            }


    @property
    def repository(self) -> str:
        return str(self._value("repository"))

    @property
    def repository_path(self) -> Path:
        selected = Path(self.repository).expanduser()
        if not selected.is_absolute() and self.source is not None:
            selected = self.source.parent / selected
        return selected.resolve()

    @property
    def files(self) -> tuple[str, ...]:
        value = self._value("files")
        assert isinstance(value, list)
        return tuple(str(item) for item in value)

    @property
    def message(self) -> str:
        return str(self._value("message"))

    @property
    def allow_empty(self) -> bool:
        return bool(self._value("allow_empty", False))

    def _value(self, key: str, default: object = None) -> object:
        if self._record is None:
            raise RuntimeError("Commit manifest has no Record")
        return self._record.get(key, default)


@dataclass(frozen=True, slots=True)
class PreparedCommitMessage:
    message: str
    breadcrumb_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegisteredCommit:
    repository: Path
    commit: str
    breadcrumb_ids: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "status": "ok",
            "repository": str(self.repository),
            "commit": self.commit,
            "breadcrumbs": list(self.breadcrumb_ids),
        }


def prepare_message(
    manifest: CommitManifest,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
) -> PreparedCommitMessage:
    """Register evidence and render its stable IDs into one commit message."""

    if not isinstance(manifest, CommitManifest):
        raise TypeError("prepare_message requires a CommitManifest")
    message = manifest.message.rstrip("\n")
    _validate_message(message, provisional=True)
    surface = BreadcrumbSurface(Path("commit-message.md"), "markdown", message)
    annotations = workflow.prepare(surface, request)
    _validate_annotations(surface, annotations)

    rewritten = message.splitlines(keepends=True)
    retained: list[dict[str, object]] = []
    breadcrumb_ids: list[str] = []
    for annotation in annotations:
        breadcrumb = store.create()
        breadcrumb_id = str(breadcrumb.records.to_record()["id"])
        label = store.label(breadcrumb_id)
        attachments = tuple(
            _json_object(item)
            for item in workflow.attachments(annotation, breadcrumb_id)
        )
        for attachment in attachments:
            store.attach(breadcrumb_id, attachment)
        marker = annotation.marker
        current = rewritten[marker.line - 1]
        ending = "\n" if current.endswith("\n") else ""
        body = current[:-1] if ending else current
        rendered = f"<!-- {label} -->"
        rewritten[marker.line - 1] = (
            body[: marker.start_column]
            + rendered
            + body[marker.end_column :]
            + ending
        )
        breadcrumb_ids.append(breadcrumb_id)
        retained.append(
            {"id": breadcrumb_id, "attachments": list(attachments)}
        )

    rendered_message = "".join(rewritten).rstrip("\n")
    envelope = json.dumps(
        {"version": 1, "breadcrumbs": retained},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    rendered_message += f"\n\n<!-- tarav.commit-evidence\n{envelope}\n-->"
    _validate_message(rendered_message, provisional=False)
    _label_lines(rendered_message, _parse_envelope(rendered_message))
    return PreparedCommitMessage(rendered_message, tuple(breadcrumb_ids))


def commit_from_manifest(
    manifest: CommitManifest,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
) -> RegisteredCommit:
    prepared = prepare_message(
        manifest,
        store=store,
        workflow=workflow,
        request=request,
    )
    repository = GitRepository(manifest.repository_path)
    commit = repository.commit(
        manifest.files,
        prepared.message,
        allow_empty=manifest.allow_empty,
    )
    try:
        return register_commit(repository.root, commit, store=store)
    except Exception as exc:
        raise CommitObservationError(commit, exc) from exc


def register_commit(
    repository: str | Path,
    commit: str,
    *,
    store: BreadcrumbStore,
) -> RegisteredCommit:
    selected = GitRepository(repository)
    exact, message = selected.commit_message(commit)
    entries = _parse_envelope(message)
    label_lines = _label_lines(message, entries)
    expected_ids = tuple(str(entry["id"]) for entry in entries)

    for entry in entries:
        breadcrumb_id = str(entry["id"])
        store.ensure(breadcrumb_id)
        attachments = entry["attachments"]
        assert isinstance(attachments, list)
        _check_attachment_conflicts(store, breadcrumb_id, attachments)
        for attachment in attachments:
            assert isinstance(attachment, Mapping)
            store.attach(breadcrumb_id, attachment)
        store.observe_commit_position(
            breadcrumb_id,
            repository=selected.root,
            commit=exact,
            line=label_lines[breadcrumb_id],
        )
    return RegisteredCommit(selected.root, exact, expected_ids)


# tarav.breadcrumb 99b7ba51eb7aee2aaa5c4e5603c2995fd5e479c5dbe1ef090d8f42a842193ee1
def audit_commit(
    repository: str | Path,
    commit: str,
    *,
    store: BreadcrumbStore,
    workflow: BreadcrumbAnnotationWorkflow,
    request: object,
) -> BreadcrumbAuditResult:
    selected = GitRepository(repository)
    exact, message = selected.commit_message(commit)
    document = BreadcrumbSurface(
        selected.root / ".git" / f"commit-message-{exact}",
        "markdown",
        message,
    )
    labels, findings = surface_labels(document)
    evidence_by_id: dict[str, list[object]] = {}
    try:
        _validate_message(message, provisional=False)
        entries = _parse_envelope(message)
        _label_lines(message, entries)
        evidence_by_id = {
            str(entry["id"]): entry["attachments"] for entry in entries
        }
    except CommitEvidenceError as exc:
        findings.append(BreadcrumbAuditConcern(audit.CommitEvidenceInvalid, str(exc)))

    audited: list[AuditedBreadcrumb] = []
    for label in labels:
        # The message's own envelope names its full IDs; the registry is the fallback.
        enveloped = [item for item in evidence_by_id if item.startswith(label.prefix)]
        breadcrumb_id = enveloped[0] if len(enveloped) == 1 else find_label(
            store, label, findings)
        if breadcrumb_id is None:
            audited.append(AuditedBreadcrumb(label.prefix, label.line, label.label, None))
            continue
        resolution = None
        observations: tuple[Mapping[str, object], ...] = ()
        attachments: tuple[Mapping[str, object], ...] = ()
        try:
            observations = store.observations(breadcrumb_id)
            attachments = store.attachments(breadcrumb_id)
            expected = evidence_by_id.get(breadcrumb_id)
            if expected is not None:
                _check_attachment_conflicts(store, breadcrumb_id, expected)
                if any(item not in attachments for item in expected):
                    findings.append(
                        BreadcrumbAuditConcern(
                            audit.CommitEvidenceRegistrationIncomplete,
                            "Commit evidence contains attachments not retained in the store.",
                            breadcrumb_id,
                            label.line,
                        )
                    )
            resolution = _resolve_commit_label(
                store,
                breadcrumb_id,
                selected,
                exact,
                label.line,
            )
        except (BreadcrumbError, OSError, TypeError, ValueError) as exc:
            findings.append(
                BreadcrumbAuditConcern(
                    audit.BreadcrumbRecordUnavailable,
                    str(exc),
                    breadcrumb_id,
                    label.line,
                )
            )
        else:
            for poi in resolution.pois:
                findings.append(
                    BreadcrumbAuditConcern(
                        audit.audit_type(poi),
                        poi.message,
                        breadcrumb_id,
                        label.line,
                    )
                )
            position = resolution.position
            if isinstance(position, GitCommitMessagePositionTarget) and (
                position.repository.resolve() != selected.root
                or position.commit != exact
                or position.line != label.line
            ):
                findings.append(
                    BreadcrumbAuditConcern(
                        audit.BreadcrumbPositionDisagrees,
                        "Resolved Breadcrumb position disagrees with this commit message.",
                        breadcrumb_id,
                        label.line,
                    )
                )
            if not attachments:
                findings.append(
                    BreadcrumbAuditConcern(
                        audit.BreadcrumbAttachmentMissing,
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
    return BreadcrumbAuditResult.from_concerns(context, workflow, request, tuple(findings))


def _validate_annotations(surface, annotations) -> None:
    lines = surface.text.splitlines()
    occupied: set[int] = set()
    for annotation in annotations:
        marker = annotation.marker
        if marker.line < 1 or marker.line > len(lines) or marker.line in occupied:
            raise CommitEvidenceError("Breadcrumb workflow returned an invalid marker")
        occupied.add(marker.line)
        line = lines[marker.line - 1]
        if not 0 <= marker.start_column < marker.end_column <= len(line):
            raise CommitEvidenceError("Breadcrumb workflow returned an invalid marker span")


def _validate_message(message: str, *, provisional: bool) -> None:
    if not message.strip() or not message.splitlines()[0].strip():
        raise CommitEvidenceError("Commit message requires a nonempty subject")
    if _ENVELOPE.search(message) and provisional:
        raise CommitEvidenceError("Manifest message already contains an evidence envelope")
    marker_lines: list[int] = []
    for number, line in enumerate(message.splitlines(), 1):
        matches = (
            (_CONTEXT.fullmatch(line) is not None if provisional else False)
            or _BREADCRUMB.fullmatch(line) is not None
            or _EVIDENCE.fullmatch(line) is not None
        )
        if matches:
            marker_lines.append(number)
        if provisional and _BREADCRUMB.fullmatch(line) is not None:
            raise CommitEvidenceError(
                "Manifest message must use provisional context or evidence markers"
            )
        for token, pattern in (
            ("tarav.context", _CONTEXT),
            ("tarav.breadcrumb", _BREADCRUMB),
            ("tarav.evidence", _EVIDENCE),
        ):
            if token in line and pattern.fullmatch(line) is None:
                raise CommitEvidenceError(f"Malformed {token} marker at line {number}")
    if not marker_lines:
        raise CommitEvidenceError("Commit message requires an evidence group")
    lines = message.splitlines()
    marker_set = set(marker_lines)
    for number in marker_lines:
        cursor = number - 1
        while cursor > 0:
            candidate = lines[cursor - 1]
            if not candidate.strip() or cursor in marker_set:
                cursor -= 1
                continue
            if not candidate.lstrip().startswith("- "):
                raise CommitEvidenceError(
                    f"Evidence marker at line {number} requires a preceding '- ' group"
                )
            break
        else:
            raise CommitEvidenceError(
                f"Evidence marker at line {number} requires a preceding '- ' group"
            )


def _parse_envelope(message: str) -> list[dict[str, object]]:
    matches = _ENVELOPE.findall(message)
    if len(matches) != 1:
        raise CommitEvidenceError("Commit message requires one evidence envelope")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise CommitEvidenceError(f"Invalid commit evidence envelope: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "breadcrumbs"}:
        raise CommitEvidenceError("Invalid commit evidence envelope shape")
    if payload["version"] != 1 or not isinstance(payload["breadcrumbs"], list):
        raise CommitEvidenceError("Unsupported commit evidence envelope")
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in payload["breadcrumbs"]:
        if not isinstance(entry, dict) or set(entry) != {"id", "attachments"}:
            raise CommitEvidenceError("Invalid Breadcrumb evidence entry")
        breadcrumb_id = entry["id"]
        attachments = entry["attachments"]
        if (
            not isinstance(breadcrumb_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", breadcrumb_id) is None
            or breadcrumb_id in seen
            or not isinstance(attachments, list)
            or not attachments
            or not all(isinstance(item, dict) for item in attachments)
        ):
            raise CommitEvidenceError("Invalid Breadcrumb evidence entry")
        seen.add(breadcrumb_id)
        entries.append(entry)
    return entries


def _label_lines(message: str, entries: list[dict[str, object]]) -> dict[str, int]:
    """Each envelope ID's message line: every label is a prefix of exactly one."""
    ids = [str(entry["id"]) for entry in entries]
    result: dict[str, int] = {}
    for number, line in enumerate(message.splitlines(), 1):
        match = _BREADCRUMB.fullmatch(line)
        if match is None:
            continue
        named = [item for item in ids if item.startswith(match.group(1))]
        if len(named) != 1:
            raise CommitEvidenceError(
                "Commit message labels and recoverable evidence mapping disagree")
        if named[0] in result:
            raise CommitEvidenceError(f"Duplicate Breadcrumb label: {named[0]}")
        result[named[0]] = number
    if len(result) != len(ids):
        raise CommitEvidenceError(
            "Commit message labels and recoverable evidence mapping disagree")
    return result


def _check_attachment_conflicts(
    store: BreadcrumbStore,
    breadcrumb_id: str,
    expected: list[object],
) -> None:
    retained = store.attachments(breadcrumb_id)
    expected_records = [_json_object(item) for item in expected]
    expected_types = {json.dumps(item.get("type"), sort_keys=True) for item in expected_records}
    for item in retained:
        item_type = json.dumps(item.get("type"), sort_keys=True)
        if item_type in expected_types and item not in expected_records:
            raise CommitEvidenceError(
                f"Breadcrumb {breadcrumb_id} has conflicting retained evidence"
            )


def _resolve_commit_label(
    store: BreadcrumbStore,
    breadcrumb_id: str,
    repository: GitRepository,
    commit: str,
    line: int,
) -> BreadcrumbResolution:
    breadcrumb = store.load(breadcrumb_id)
    canonical = breadcrumb_label(breadcrumb_id[:LABEL_PREFIX])
    for observation in reversed(store.observations(breadcrumb_id)):
        record = observation.get("locator")
        if not isinstance(record, dict):
            continue
        locator = record.get("locator")
        if not isinstance(locator, dict):
            continue
        if (
            record.get("type") != entity(GitCommitMessagePositionReference).name
            or Path(str(locator.get("repository"))).resolve() != repository.root
            or locator.get("commit") != commit
            or locator.get("line") != line
        ):
            continue
        checked = dict(record)
        checked["check"] = {"contains": canonical}
        reference = GitCommitMessagePositionReference.records.from_record(checked)
        reference.source = breadcrumb.source
        result = reference.resolve()
        if result.ok and isinstance(result.target, GitCommitMessagePositionTarget):
            return BreadcrumbResolution(breadcrumb, "resolved", result.target)
    return BreadcrumbResolution(
        breadcrumb,
        "unresolvable",
        pois=(
            BreadcrumbPositionMissing(
                "No observation resolves this Breadcrumb at the audited commit line.",
                situation={"breadcrumb_id": breadcrumb.records.to_record()["id"]},
            ),
        ),
    )


GIT_BREADCRUMB_RECORD_TYPES = (CommitManifest,)


__all__ = [
    "CommitEvidenceError",
    "CommitManifest",
    "CommitObservationError",
    "GIT_BREADCRUMB_RECORD_TYPES",
    "PreparedCommitMessage",
    "RegisteredCommit",
    "audit_commit",
    "commit_from_manifest",
    "prepare_message",
    "register_commit",
]
