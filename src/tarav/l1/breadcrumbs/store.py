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
from tarav.l1.poi import SituationPOI
from tarav.l1.references import FilePositionReference, FilePositionTarget
from tarav.l1.references.git import (
    GitCommitMessagePositionReference,
    GitCommitMessagePositionTarget,
)

from .model import Breadcrumb, LocatorObservation
from .identity import BREADCRUMBS_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord


# tarav.breadcrumb b8fcfd6a5d2b
# A surface carries the first LABEL_PREFIX characters of a Breadcrumb ID, or
# more when that is not unique; the registry keeps the full 64.
LABEL_PREFIX = 12
_BREADCRUMB_ID = re.compile(r"[0-9a-f]{64}")
_PREFIX = re.compile(rf"[0-9a-f]{{{LABEL_PREFIX},64}}")
_CORE_LABEL = re.compile(rf"tarav\.breadcrumb\s+([0-9a-f]{{{LABEL_PREFIX},64}})")


class BreadcrumbError(ValueError):
    pass


class BreadcrumbNotFound(BreadcrumbError):
    """No retained Breadcrumb ID starts with the prefix."""


# tarav.breadcrumb 792e5d16a3d5
class BreadcrumbAmbiguous(BreadcrumbError):
    """Several retained Breadcrumb IDs start with the prefix; none is chosen."""

    def __init__(self, prefix: str, candidates: tuple[str, ...]) -> None:
        self.prefix, self.candidates = prefix, candidates
        super().__init__(f"Breadcrumb prefix {prefix} matches {len(candidates)} Breadcrumbs: "
                         + ", ".join(candidates))


# tarav.breadcrumb 85e87dcfa170
class BreadcrumbResolutionPOI(SituationPOI):
    """Family of failures to locate a Breadcrumb's label."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('23e961ba-5383-4fc0-a386-b646b8b10240'),
            name='Tarav.Breadcrumbs.Resolution.POI',
            workflow=BREADCRUMBS_WORKFLOW_SHIP,
        )


class BreadcrumbPositionMissing(BreadcrumbResolutionPOI):
    """No recorded position contains the Breadcrumb's label."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('a98d3411-c552-481f-974b-e54b83517a24'),
                          name='Tarav.Breadcrumbs.Resolution.PositionMissing',
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)


class BreadcrumbPositionAmbiguous(BreadcrumbResolutionPOI):
    """Several recorded positions contain the same Breadcrumb label.

    `positions` is how many of them do.
    """

    def __init__(self, message: str, *, situation, positions: int) -> None:
        super().__init__(message, situation=situation)
        self.positions = positions

    class RecordInterface(BreadcrumbResolutionPOI.RecordInterface):
        positions: int

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "positions": self.positions}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        result = super()._from_record(loaded)
        result.positions = loaded.data.positions
        return result

    class Records(BreadcrumbResolutionPOI.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "positions": 2}

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('ac977f0a-6f4e-4d32-a50d-6cd56271d38b'),
                          name='Tarav.Breadcrumbs.Resolution.PositionAmbiguous',
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ExternalAnchorMissing(BreadcrumbResolutionPOI):
    """An external selection is unavailable; its Breadcrumb remains registered."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('ff221f17-7bee-460d-897d-4c2cb9976293'),
                          name='Tarav.Breadcrumbs.Resolution.ExternalAnchorMissing',
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)


class ExternalAnchorAmbiguous(BreadcrumbResolutionPOI):
    """Several lines contain the external fragment after its observed line changed."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('a0692022-cbc0-4a60-83d8-f8fba2841e43'),
                          name='Tarav.Breadcrumbs.Resolution.ExternalAnchorAmbiguous',
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)


@dataclass(frozen=True, slots=True)
class BreadcrumbResolution:
    breadcrumb: Breadcrumb
    status: str
    position: FilePositionTarget | GitCommitMessagePositionTarget | None = None
    pois: tuple[BreadcrumbResolutionPOI, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "resolved"

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "breadcrumb": self.breadcrumb.records.to_record(),
            "position": _position_json(self.position),
            "pois": [
                item.records.to_record()
                for item in self.pois
            ],
        }


def default_breadcrumbs_root() -> Path:
    return Path.home() / "Documents" / "tarav" / "breadcrumbs"


def breadcrumb_label(prefix: str) -> str:
    """The label text for an ID prefix; `BreadcrumbStore.label` picks the prefix."""
    return f"tarav.breadcrumb {_validated_prefix(prefix)}"


def parse_breadcrumb_label(value: str) -> str:
    """The ID prefix a label or bare prefix carries, 12 to 64 characters."""
    candidate = value.strip()
    if _PREFIX.fullmatch(candidate):
        return candidate
    match = _CORE_LABEL.fullmatch(candidate)
    if match is None:
        raise BreadcrumbError("Breadcrumb label must be an ID prefix of 12 to 64 lowercase "
                              "hexadecimal characters, bare or as 'tarav.breadcrumb <prefix>'")
    return match.group(1)


class BreadcrumbStore:
    # tarav.breadcrumb 7c694b608689
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_breadcrumbs_root()).expanduser().resolve()
        self.records_root = self.root / "records"

    def create(self, breadcrumb_id: str | None = None, *, placement="embedded") -> Breadcrumb:
        if placement not in ("embedded", "external"):
            raise BreadcrumbError("Breadcrumb placement must be embedded or external")
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
                if placement != "embedded":
                    record["placement"] = placement
                Breadcrumb.records.from_record(record)
                atomic_write_json(directory / "main.json", record)
                (directory / "attachments").mkdir()
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            return self.load(selected)

    # tarav.breadcrumb 976a54ce1b75
    def create_external(self, *, file: str | Path, line: int, fragment: str) -> Breadcrumb:
        path = validate_external_selection(file, line, fragment)
        breadcrumb = self.create(placement="external")
        self.observe_external_position(str(breadcrumb.typed.id), file=path, line=line, fragment=fragment)
        return breadcrumb

    def observe_external_position(self, label: str, *, file: str | Path,
                                  line: int, fragment: str) -> dict[str, object]:
        """A maintainer's explicit replacement location; never edit the source."""
        path = validate_external_selection(file, line, fragment)
        breadcrumb = self.load(label)
        if breadcrumb.typed.placement != "external":
            raise BreadcrumbError("External observations require external placement")
        record = {"type": entity(LocatorObservation).name,
                  "breadcrumb_id": breadcrumb.typed.id, "observed_at": _now(),
                  "fragment": fragment,
                  "locator": {"type": entity(FilePositionReference).name,
                              "locator": {"file": str(path), "line": line}}}
        self.append_observation(label, record)
        return record

    def external_for_file(self, file: str | Path) -> tuple[str, ...]:
        """Discover external anchors from their latest registry observation."""
        path = Path(file).expanduser().resolve()
        found = []
        for source in sorted(self.records_root.glob("*/main.json")):
            payload = json.loads(source.read_text(encoding="utf-8"))
            if payload.get("placement") != "external":
                continue
            identity = self.find(source.parent.name)
            observations = self.observations(identity)
            if observations and Path(observations[-1]["locator"]["locator"]["file"]).resolve() == path:
                found.append(identity)
        return tuple(found)

    def ensure(self, breadcrumb_id: str) -> Breadcrumb:
        """Return one retained identity, creating it only when absent."""

        selected = _validated_id(breadcrumb_id)
        if (self.records_root / selected / "main.json").is_file():
            return self.load(selected)
        return self.create(selected)

    def find(self, label: str) -> str:
        """The one full ID a label's prefix names; several or none is an error."""
        prefix = parse_breadcrumb_label(label)
        if len(prefix) == 64:
            if (self.records_root / prefix).is_dir():
                return prefix
            raise BreadcrumbNotFound(f"No Breadcrumb matches {prefix}")
        candidates = tuple(sorted(
            path.name for path in self.records_root.glob(f"{prefix}*")
            if _BREADCRUMB_ID.fullmatch(path.name)))
        if not candidates:
            raise BreadcrumbNotFound(f"No Breadcrumb matches {prefix}")
        if len(candidates) > 1:
            raise BreadcrumbAmbiguous(prefix, candidates)
        return candidates[0]

    def label(self, breadcrumb_id: str) -> str:
        """The label a surface carries: the 12-character prefix, which must be unique."""
        selected = _validated_id(breadcrumb_id)
        prefix = selected[:LABEL_PREFIX]
        if self.find(prefix) != selected:
            raise BreadcrumbNotFound(f"No Breadcrumb matches {selected}")
        return breadcrumb_label(prefix)

    def load(self, label: str) -> Breadcrumb:
        breadcrumb_id = self.find(label)
        source = self.records_root / breadcrumb_id / "main.json"
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BreadcrumbError(f"Cannot load Breadcrumb {breadcrumb_id}: {exc}") from exc
        record = Breadcrumb.records.from_record(payload)
        if record.records.to_record()["id"] != breadcrumb_id:
            raise BreadcrumbError("Breadcrumb directory and retained ID disagree")
        record.source = source
        return record

    def append_observation(self, label: str, record: Mapping[str, object]) -> None:
        breadcrumb = self.load(label)
        observation = LocatorObservation.records.from_record(record)
        external = breadcrumb.typed.placement == "external"
        if external != (observation.typed.fragment is not None):
            raise BreadcrumbError("External observations require a fragment; embedded observations do not")
        if external and (not isinstance(observation.typed.locator, FilePositionReference.RecordInterface)
                         or not isinstance(observation.typed.locator.locator.file, str)):
            raise BreadcrumbError("External observations require a file path and line")
        if observation.records.to_record()["breadcrumb_id"] != breadcrumb.records.to_record()["id"]:
            raise BreadcrumbError("Locator observation belongs to another Breadcrumb")
        path = breadcrumb.directory / "locator-observations.jsonl"
        prior = path.read_text(encoding="utf-8") if path.exists() else ""
        identity = _observation_identity(observation.records.to_record())
        for retained in self.observations(label):
            if _observation_identity(retained) == identity:
                return
        serialized = json.dumps(observation.records.to_record(), sort_keys=True, ensure_ascii=False)
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
            "breadcrumb_id": breadcrumb.records.to_record()["id"],
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
        self.append_observation(str(breadcrumb.records.to_record()["id"]), record)
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
        breadcrumb_id = str(breadcrumb.records.to_record()["id"])
        reference = GitCommitMessagePositionReference(
            repository=repository,
            commit=commit,
            line=line,
        ).records.to_record()
        reference["check"] = {"contains": breadcrumb_label(breadcrumb_id[:LABEL_PREFIX])}
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
                observation = LocatorObservation.records.from_record(value)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise BreadcrumbError(f"Invalid locator observation at line {number}: {exc}") from exc
            records.append(observation.records.to_record())
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
            "breadcrumb": breadcrumb.records.to_record(),
            "observations": list(self.observations(label)),
            "attachments": list(self.attachments(label)),
        }

    def resolve(self, label: str) -> BreadcrumbResolution:
        breadcrumb = self.load(label)
        if breadcrumb.typed.placement == "external":
            return self._resolve_external(breadcrumb)
        # Every valid label of this Breadcrumb contains its 12-character one.
        core_label = breadcrumb_label(str(breadcrumb.records.to_record()["id"])[:LABEL_PREFIX])
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
                reference = FilePositionReference.records.from_record(checked)
            elif GitCommitMessagePositionReference.matches(reference_type):
                reference = GitCommitMessagePositionReference.records.from_record(checked)
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
            poi = BreadcrumbPositionMissing(
                "No recorded position contains the Breadcrumb's label.",
                situation={"breadcrumb_id": breadcrumb.records.to_record()["id"]},
            )
            return BreadcrumbResolution(breadcrumb, "unresolvable", pois=(poi,))
        poi = BreadcrumbPositionAmbiguous(
            f"{len(positions)} recorded positions contain the Breadcrumb's label.",
            situation={"breadcrumb_id": breadcrumb.records.to_record()["id"]},
            positions=len(positions),
        )
        return BreadcrumbResolution(breadcrumb, "ambiguous", pois=(poi,))

    def _resolve_external(self, breadcrumb: Breadcrumb) -> BreadcrumbResolution:
        identity = str(breadcrumb.typed.id)
        observations = self.observations(identity)
        reason = "External Breadcrumb has no observed location."
        if observations:
            observation = observations[-1]
            locator, fragment = observation["locator"]["locator"], observation.get("fragment")
            if not isinstance(fragment, str) or not fragment.strip():
                raise BreadcrumbError("External observation has no exact fragment")
            path = Path(locator["file"]).expanduser().resolve()
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError) as exc:
                reason = f"External Breadcrumb file is unavailable: {exc}"
            else:
                line = locator["line"]
                if line <= len(lines) and fragment in lines[line - 1]:
                    return BreadcrumbResolution(breadcrumb, "resolved", FilePositionTarget(path, line, lines[line - 1]))
                matches = [i for i, text in enumerate(lines, 1) if fragment in text]
                if len(matches) == 1:
                    line = matches[0]
                    return BreadcrumbResolution(breadcrumb, "resolved", FilePositionTarget(path, line, lines[line - 1]))
                if matches:
                    poi = ExternalAnchorAmbiguous(
                        f"External Breadcrumb fragment matches several lines: {matches}.",
                        situation={"breadcrumb_id": identity})
                    return BreadcrumbResolution(breadcrumb, "ambiguous", pois=(poi,))
                reason = "External Breadcrumb line is missing; the maintainer must provide a new location."
        poi = ExternalAnchorMissing(reason, situation={"breadcrumb_id": identity})
        return BreadcrumbResolution(breadcrumb, "unresolvable", pois=(poi,))


def validate_external_selection(file: str | Path, line: int, fragment: str) -> Path:
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise BreadcrumbError("External line must be a positive integer")
    if not isinstance(fragment, str) or not fragment.strip() or "\n" in fragment or "\r" in fragment:
        raise BreadcrumbError("External fragment must be a nonempty single-line string")
    path = Path(file).expanduser().resolve()
    lines = path.read_text(encoding="utf-8").splitlines()
    if line > len(lines) or fragment not in lines[line - 1]:
        raise BreadcrumbError("External fragment does not occur on the selected line")
    return path


def _validated_prefix(value: str) -> str:
    if not isinstance(value, str) or _PREFIX.fullmatch(value) is None:
        raise BreadcrumbError("Breadcrumb ID prefix must be 12 to 64 lowercase hexadecimal characters")
    return value


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
    "LABEL_PREFIX",
    "BreadcrumbAmbiguous",
    "BreadcrumbError",
    "BreadcrumbNotFound",
    "BreadcrumbResolutionPOI",
    "BreadcrumbPositionMissing",
    "BreadcrumbPositionAmbiguous",
    "ExternalAnchorMissing",
    "ExternalAnchorAmbiguous",
    "validate_external_selection",
    "BreadcrumbResolution",
    "BreadcrumbStore",
    "breadcrumb_label",
    "default_breadcrumbs_root",
    "parse_breadcrumb_label",
]
