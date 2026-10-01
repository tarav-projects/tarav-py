"""Directory-backed Breadcrumb identity, observations, and attachments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import shutil

from tarav.l0._core.persistence import atomic_write_json, atomic_write_text
from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import (
    RecordTypeReference,
    TypeShip,
    locate_record_type,
)
from tarav.l1.poi import POI
from tarav.l1.references import FilePositionReference, FilePositionTarget
from tarav.l1.references.git import (
    GitCommitMessagePositionReference,
    GitCommitMessagePositionTarget,
)

from .model import Breadcrumb, LocatorObservation
from .identity import BREADCRUMBS_WORKFLOW_SHIP


_BREADCRUMB_ID = re.compile(r"[0-9a-f]{64}")
_CORE_LABEL = re.compile(r"tarav\.breadcrumb\s+([0-9a-f]{64})")


class BreadcrumbError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BreadcrumbFinding(POI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('23e961ba-5383-4fc0-a386-b646b8b10240'),
            name='Tarav.Breadcrumbs.Finding',
            workflow=BREADCRUMBS_WORKFLOW_SHIP,
        )

    code: str
    message: str

    def as_dict(self):
        return {"type": entity(type(self)).name, "code": self.code,
                "message": self.message}


@dataclass(frozen=True, slots=True)
class BreadcrumbResolution:
    breadcrumb: Breadcrumb
    status: str
    position: FilePositionTarget | GitCommitMessagePositionTarget | None = None
    findings: tuple[BreadcrumbFinding, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "resolved"

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "breadcrumb": self.breadcrumb.to_record(),
            "position": _position_json(self.position),
            "findings": [
                item.as_dict()
                for item in self.findings
            ],
        }


def default_breadcrumbs_root() -> Path:
    return Path.home() / "Documents" / "tarav" / "breadcrumbs"


def breadcrumb_label(breadcrumb_id: str) -> str:
    return f"tarav.breadcrumb {_validated_id(breadcrumb_id)}"


def parse_breadcrumb_label(value: str) -> str:
    candidate = value.strip()
    if _BREADCRUMB_ID.fullmatch(candidate):
        return candidate
    match = _CORE_LABEL.fullmatch(candidate)
    if match is None:
        raise BreadcrumbError("Breadcrumb label must be an ID or 'tarav.breadcrumb <id>'")
    return match.group(1)


class BreadcrumbStore:
    # tarav.breadcrumb 7c694b6086890f17f29ecb680fa492cef54312d463ec11243594fb7bc5c15598
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_breadcrumbs_root()).expanduser().resolve()
        self.records_root = self.root / "records"

    def create(self, breadcrumb_id: str | None = None) -> Breadcrumb:
        while True:
            selected = _validated_id(breadcrumb_id or secrets.token_hex(32))
            directory = self.records_root / selected
            try:
                directory.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                if breadcrumb_id is not None:
                    raise BreadcrumbError(f"Breadcrumb already exists: {selected}") from None
                continue
            try:
                record = {"type": entity(Breadcrumb).name, "id": selected}
                Breadcrumb.from_record(record)
                atomic_write_json(directory / "main.json", record)
                (directory / "attachments").mkdir()
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            return self.load(selected)

    def ensure(self, breadcrumb_id: str) -> Breadcrumb:
        """Return one retained identity, creating it only when absent."""

        selected = _validated_id(breadcrumb_id)
        if (self.records_root / selected / "main.json").is_file():
            return self.load(selected)
        return self.create(selected)

    def load(self, label: str) -> Breadcrumb:
        breadcrumb_id = parse_breadcrumb_label(label)
        source = self.records_root / breadcrumb_id / "main.json"
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BreadcrumbError(f"Cannot load Breadcrumb {breadcrumb_id}: {exc}") from exc
        record = Breadcrumb.from_record(payload)
        if record.to_record()["id"] != breadcrumb_id:
            raise BreadcrumbError("Breadcrumb directory and retained ID disagree")
        record.source = source
        return record

    def append_observation(self, label: str, record: Mapping[str, object]) -> None:
        breadcrumb = self.load(label)
        observation = LocatorObservation.from_record(record)
        if observation.to_record()["breadcrumb_id"] != breadcrumb.to_record()["id"]:
            raise BreadcrumbError("Locator observation belongs to another Breadcrumb")
        path = breadcrumb.directory / "locator-observations.jsonl"
        prior = path.read_text(encoding="utf-8") if path.exists() else ""
        identity = _observation_identity(observation.to_record())
        for retained in self.observations(label):
            if _observation_identity(retained) == identity:
                return
        serialized = json.dumps(observation.to_record(), sort_keys=True, ensure_ascii=False)
        atomic_write_text(path, prior + serialized + "\n")

    def observe_position(
        self,
        label: str,
        *,
        file: str | Mapping[str, object],
        line: int,
        previous_line: str | None = None,
        next_line: str | None = None,
    ) -> dict[str, object]:
        breadcrumb = self.load(label)
        record: dict[str, object] = {
            "type": entity(LocatorObservation).name,
            "breadcrumb_id": breadcrumb.to_record()["id"],
            "observed_at": _now(),
            "locator": {
                "type": entity(FilePositionReference).name,
                "locator": {"file": file, "line": line},
            },
        }
        if previous_line is not None or next_line is not None:
            record["hints"] = {
                "previous_line": previous_line,
                "next_line": next_line,
            }
        self.append_observation(str(breadcrumb.to_record()["id"]), record)
        return record

    def observe_commit_position(
        self,
        label: str,
        *,
        repository: str | Path,
        commit: str,
        line: int,
    ) -> dict[str, object]:
        breadcrumb = self.load(label)
        breadcrumb_id = str(breadcrumb.to_record()["id"])
        reference = GitCommitMessagePositionReference(
            repository=repository,
            commit=commit,
            line=line,
        ).to_record()
        reference["check"] = {"contains": breadcrumb_label(breadcrumb_id)}
        record = {
            "type": entity(LocatorObservation).name,
            "breadcrumb_id": breadcrumb_id,
            "observed_at": _now(),
            "locator": reference,
        }
        self.append_observation(breadcrumb_id, record)
        return record

    def observations(self, label: str) -> tuple[dict[str, object], ...]:
        breadcrumb = self.load(label)
        path = breadcrumb.directory / "locator-observations.jsonl"
        if not path.exists():
            return ()
        records: list[dict[str, object]] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                observation = LocatorObservation.from_record(value)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise BreadcrumbError(f"Invalid locator observation at line {number}: {exc}") from exc
            records.append(observation.to_record())
        return tuple(records)

    def attach(self, label: str, record: Mapping[str, object]) -> Path:
        breadcrumb = self.load(label)
        payload = _typed_record(record)
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        for existing in sorted((breadcrumb.directory / "attachments").glob("*.json")):
            try:
                retained = _typed_record(
                    json.loads(existing.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                continue
            if json.dumps(retained, sort_keys=True, ensure_ascii=False) == serialized:
                return existing
        attachment = breadcrumb.directory / "attachments" / f"{secrets.token_hex(16)}.json"
        atomic_write_json(attachment, payload, ensure_ascii=False)
        return attachment

    def attachments(self, label: str) -> tuple[dict[str, object], ...]:
        directory = self.load(label).directory / "attachments"
        records = []
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BreadcrumbError(f"Cannot load attachment {path}: {exc}") from exc
            records.append(_typed_record(value))
        return tuple(records)

    def show(self, label: str) -> dict[str, object]:
        breadcrumb = self.load(label)
        return {
            "breadcrumb": breadcrumb.to_record(),
            "observations": list(self.observations(label)),
            "attachments": list(self.attachments(label)),
        }

    def resolve(self, label: str) -> BreadcrumbResolution:
        breadcrumb = self.load(label)
        core_label = breadcrumb_label(str(breadcrumb.to_record()["id"]))
        positions: dict[
            tuple[object, ...], FilePositionTarget | GitCommitMessagePositionTarget
        ] = {}
        for observation in reversed(self.observations(label)):
            locator = observation["locator"]
            assert isinstance(locator, dict)
            checked = dict(locator)
            checked["check"] = {"contains": core_label}
            location = locate_record_type(checked)
            if location is None:
                continue
            reference_type = RecordTypeReference.parse(location.value)
            if FilePositionReference.matches(reference_type):
                reference = FilePositionReference.from_record(checked)
            elif GitCommitMessagePositionReference.matches(reference_type):
                reference = GitCommitMessagePositionReference.from_record(checked)
            else:
                continue
            reference.source = breadcrumb.source
            result = reference.resolve()
            if result.ok and isinstance(result.target, FilePositionTarget):
                positions[(result.target.path.resolve(), result.target.line)] = result.target
            elif result.ok and isinstance(
                result.target, GitCommitMessagePositionTarget
            ):
                positions[
                    (
                        result.target.repository.resolve(),
                        result.target.commit,
                        result.target.line,
                    )
                ] = result.target
        if len(positions) == 1:
            return BreadcrumbResolution(breadcrumb, "resolved", next(iter(positions.values())))
        if not positions:
            finding = BreadcrumbFinding(
                "breadcrumb-position-missing",
                "No recorded file position contains the Breadcrumb's exact canonical label.",
            )
            return BreadcrumbResolution(breadcrumb, "unresolvable", findings=(finding,))
        finding = BreadcrumbFinding(
            "breadcrumb-position-ambiguous",
            f"{len(positions)} recorded file positions contain the Breadcrumb's canonical label.",
        )
        return BreadcrumbResolution(breadcrumb, "ambiguous", findings=(finding,))


def _validated_id(value: str) -> str:
    if not isinstance(value, str) or _BREADCRUMB_ID.fullmatch(value) is None:
        raise BreadcrumbError("Breadcrumb ID must be 64 lowercase hexadecimal characters")
    return value


def _typed_record(value: Mapping[str, object]) -> dict[str, object]:
    try:
        payload = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise BreadcrumbError(f"Attachment must be JSON-compatible: {exc}") from exc
    location = locate_record_type(payload)
    if location is None:
        raise BreadcrumbError("Attachment must carry a top-level Tarav Type reference")
    reference = RecordTypeReference.parse(location.value)
    if reference.ship is None and reference.label is None:
        raise BreadcrumbError("Attachment has an invalid top-level Tarav Type reference")
    return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _observation_identity(record: Mapping[str, object]) -> str:
    payload = dict(record)
    payload.pop("observed_at", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _position_json(
    position: FilePositionTarget | GitCommitMessagePositionTarget | None,
) -> dict[str, object] | None:
    if isinstance(position, FilePositionTarget):
        return {
            "file": str(position.path),
            "line": position.line,
            "text": position.text,
        }
    if isinstance(position, GitCommitMessagePositionTarget):
        return {
            "repository": str(position.repository),
            "commit": position.commit,
            "line": position.line,
            "text": position.text,
        }
    return None


__all__ = [
    "BreadcrumbError",
    "BreadcrumbFinding",
    "BreadcrumbResolution",
    "BreadcrumbStore",
    "breadcrumb_label",
    "default_breadcrumbs_root",
    "parse_breadcrumb_label",
]
