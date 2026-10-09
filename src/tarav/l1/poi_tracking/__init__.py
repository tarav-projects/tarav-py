"""POI tracking: a durable record of every tracked POI and of how its status changes.

A check run is evidence. Each check result says which check ran, whether it
completed, and which POIs it raised; the tracker turns that into data points
on one record per POI identity. A record is kept forever. Its status is a set
of independent axes, never one value: this module owns the observation axis,
and any workflow can contribute another. The tracker stores and filters axis
values and does not interpret what they mean.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

from tarav.l0.kernel import (
    FileRecord,
    Ship,
    TaravClass,
    TaravEntity,
    TaravType,
    TaravWorkflow,
    TypeShip,
    WorkflowShip,
    entity,
)
from tarav.l1.poi import IdentifiedPOI, NotificationPOI, POI, emit_notification
from tarav.l1.settings import SettingsProvider

POI_TRACKING_WORKFLOW_SHIP = WorkflowShip("c3104cc5-ec89-46ef-97e7-88deb1a0e913")
TRACKED_POI_VIEW = "tracked-poi"
ACTIVE, PASSED, NOT_EVALUATED = "active", "passed", "not-evaluated"
_UNDERIVED = object()


# tarav.breadcrumb aa938b121f87693fb391bd1ac0eb4879931ad1ed4583f46d3b433af295ae7f71
class POITrackingWorkflow(TaravWorkflow):
    workflow_name = "poi_tracking"
    constitution = ("Keep a record of every tracked POI and of its status over time, "
                    "without deciding what any status means.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d4dbf0a6-206c-4d5d-b9d2-d97723c5470c"),
                          name="Tarav.Workflow.POITracking",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return POI_TRACKING_WORKFLOW_SHIP


class TrackingError(ValueError):
    """An axis was addressed or written in a way the tracker does not accept."""


def _stamp(at: datetime | None) -> str:
    current = datetime.now(timezone.utc) if at is None else at
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("Observation time must be a timezone-aware datetime")
    return current.astimezone(timezone.utc).isoformat()


def _plain(value: object) -> object:
    """Detached JSON data, so that comparing two snapshots is stable."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


# tarav.breadcrumb afc6468e0ac2f13151131dc80051a87e729e13f83c5fea5fbf1251231d95f9cc
class TrackablePOI(POI, SettingsProvider):
    """Capability: a POI of an extending Type is tracked unless it says otherwise.

    The `tracked` setting is this Type's partition. A POI Type that wants its
    instances to be able to switch tracking off lists `TrackablePOI` in
    `settings_include`; an instance then writes the setting. Other trackable
    Types are always tracked.
    """

    class SettingsInterface(BaseModel):
        tracked: bool = Field(
            default=True, description="Whether the tracker keeps a record of this POI.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("01ce7a65-01ed-429c-8a98-36b2f8491a30"),
                          name="Tarav.POI.Tracking.Trackable",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)

    def tracking_enabled(self) -> bool:
        if entity(TrackablePOI).name not in type(self).settings_partitions():
            return True
        return bool(self.settings.get("tracked", partition=TrackablePOI))


# tarav.breadcrumb 5e80fca8c9d4f6155474676f5340cc126b35188bc5253af45ad4d8dc6f63d929
# tarav.breadcrumb 32edfd2fc6e21e489a0506430eff4866675b2f6699922d6c7f3f243d35db7b3a
class TrackAxis(TaravType):
    """One status dimension of a track record, owned by the workflow of its Type.

    `key` names the axis inside a record. `values`, when set, lists the values
    it accepts; a subtype may override `accepts()` instead. An axis that reads
    its value from its own source overrides `derive()`. Axes are independent:
    writing one never changes another, and two may say related things.
    """

    key: ClassVar[str] = ""
    values: ClassVar[tuple[str, ...] | None] = None
    caller_writable: ClassVar[bool] = True

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ff530d61-0872-4271-a5cc-bdb915972d31"),
                          name="Tarav.POI.Tracking.Axis",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)

    def accepts(self, value: object) -> bool:
        if self.values is not None:
            return value in self.values
        return isinstance(value, (str, int, float, bool))

    def derive(self, record: Mapping[str, object]) -> object:
        """The value this axis reads from its own source, when it has one."""
        return _UNDERIVED


class ObservationAxis(TrackAxis):
    """Whether the last evidence saw the POI: written only from check results."""

    key = "observation"
    values = (ACTIVE, PASSED, NOT_EVALUATED)
    caller_writable = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d2f10f63-cb42-4f87-818c-37be41d196ae"),
                          name="Tarav.POI.Tracking.ObservationAxis",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)


# tarav.breadcrumb 27d682d54774d55ce4cac7a9f7fcb1c199457b008e04f7e166731289ccb1c1d4
@dataclass(frozen=True, slots=True)
class CheckObservation:
    """One data point: a check, whether it completed, and the POIs it raised.

    `check_identity` says which check this is across runs. Without it the
    tracker can record what was raised and can never conclude that a POI passed.
    """

    check_type: str
    check_identity: str | None
    status: str
    pois: tuple[POI, ...] = ()

    @property
    def completed(self) -> bool:
        return self.status == "completed"


class TrackRecord(TaravEntity, FileRecord):
    """Everything tracked about one POI identity: snapshot, owning check and axes."""

    class RecordInterface(TaravEntity.RecordInterface):
        schema_version: int
        poi_id: str
        poi_type_id: str
        poi: dict
        check: dict
        first_tracked_at: str
        axes: dict[str, dict]

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("4cc184f0-7c00-4669-8a3c-197134a963cc"),
                          name="Tarav.POI.Tracking.Record",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)

    @classmethod
    def identity_for(cls, poi_id: str) -> Ship:
        return Ship(uuid5(UUID(str(entity(cls).id)), poi_id))

    class Records(TaravEntity.Records):
        def validate_record(self, value):
            cls = self._owner
            data = super().validate_record(value)
            if data.schema_version != 1:
                raise ValueError("Unsupported track record schema")
            if data.id != cls.identity_for(data.poi_id):
                raise ValueError("Track record identity disagrees with its POI identity")
            if data.poi.get("id") != data.poi_id or data.poi.get("class_id") != data.poi_type_id:
                raise ValueError("Track record snapshot disagrees with its POI identity")
            datetime.fromisoformat(data.first_tracked_at)
            for key, axis in data.axes.items():
                history = axis.get("history")
                if not key or "value" not in axis or not isinstance(history, list) or not history:
                    raise ValueError(f"Axis {key!r} needs a value and a history")
                if history[-1].get("value") != axis["value"]:
                    raise ValueError(f"Axis {key!r} value disagrees with its history")
                for change in history:
                    datetime.fromisoformat(change["at"])
            return data

        def record_example(self):
            cls = self._owner
            poi_id = "0" * 64
            at = "2026-10-09T00:00:00+00:00"
            return {
                "type": entity(cls).name, "schema_version": 1,
                "id": str(cls.identity_for(poi_id)), "poi_id": poi_id,
                "poi_type_id": "7d28d632-2ec5-4c5a-997f-224ad508ce9d",
                "poi": {"id": poi_id, "class_id": "7d28d632-2ec5-4c5a-997f-224ad508ce9d",
                        "type": "Example.POI", "message": "Example", "situation": {"example": 1}},
                "check": {"type": "Example.Check", "identity": None},
                "first_tracked_at": at,
                "axes": {ObservationAxis.key: {
                    "type": entity(ObservationAxis).name,
                    "owner_workflow": str(POI_TRACKING_WORKFLOW_SHIP),
                    "value": ACTIVE, "since": at, "data": {"last_active_at": at,
                                                           "last_evaluated_at": at},
                    "history": [{"at": at, "value": ACTIVE, "by": {"kind": "check-run"}}],
                }},
            }

    @property
    def record(self) -> dict[str, object]:
        return self.records.to_record()

    def obj_context(self, builder) -> None:
        from tarav.l1.poi import POIDetails

        record = self.record

        def value(content: object):
            return POIDetails.records.from_record(
                {"type": entity(POIDetails).name, "value": deepcopy(content)})

        builder.add("status", opener=lambda: value(status_vector(record)),
                    description="The current value of every axis.")
        builder.add("poi", opener=lambda: value(record["poi"]),
                    description="The POI as it was last raised.")
        builder.add("check", opener=lambda: value(record["check"]),
                    description="The check that owns this POI, and its identity across runs.")
        builder.add("axes", opener=lambda: value(record["axes"]),
                    description="Every axis with its owner, value and history of changes.")


class TrackRecordUnreadable(NotificationPOI):
    """A file in a tracking store could not be read as a track record; it was skipped."""

    read_first = ("tarav.l1.poi_tracking: TrackRecord.Records.validate_record().",)
    may_do = ("Inspect the named file; the tracker never repairs or deletes it.",
              "Raise it to the User when the file is under Git and was edited by hand.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("78e637bf-c5ba-4f22-b124-f1e741b4346e"),
                          name="Tarav.POI.Tracking.RecordUnreadable",
                          workflow=POI_TRACKING_WORKFLOW_SHIP)


def status_vector(record: Mapping[str, object]) -> dict[str, object]:
    """Axis key to current value: the status of a record, never one value."""
    return {key: axis["value"] for key, axis in record["axes"].items()}


class TrackRecordStore:
    """One JSON file per POI identity under a caller-chosen folder; nothing is deleted."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def load_all(self) -> tuple[dict[str, dict], list[dict[str, str]]]:
        records: dict[str, dict] = {}
        unreadable: list[dict[str, str]] = []
        if not self.root.is_dir():
            return records, unreadable
        for path in sorted(self.root.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                TrackRecord.records.validate_record(record)
                if path.stem != record["poi_id"]:
                    raise ValueError("Track record filename disagrees with its POI identity")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                unreadable.append({"path": str(path), "detail": str(exc)})
                continue
            records[record["poi_id"]] = record
        return records, unreadable

    def find(self, prefix: str) -> list[dict]:
        if not isinstance(prefix, str) or not prefix or not self.root.is_dir():
            return []
        found = []
        for path in sorted(self.root.glob(f"{prefix}*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                TrackRecord.records.validate_record(record)
            except (OSError, ValueError, TypeError, KeyError):
                continue
            found.append(record)
        return found

    def write(self, record: Mapping[str, object]) -> None:
        TrackRecord.records.validate_record(record)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{record['poi_id']}.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                         prefix=".track-", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


class POITracker:
    """Turn check results into data points on track records, and read them back."""

    def __init__(self, store: TrackRecordStore, *, axes: Iterable[TrackAxis] = ()) -> None:
        if not isinstance(store, TrackRecordStore):
            raise TypeError("Expected a TrackRecordStore")
        self.store = store
        self.axes: dict[str, TrackAxis] = {}
        for axis in (ObservationAxis(), *axes):
            if not isinstance(axis, TrackAxis) or not axis.key:
                raise TypeError("A tracker axis is a TrackAxis with a key")
            if axis.key in self.axes:
                raise TrackingError(f"Axis key is already contributed: {axis.key}")
            self.axes[axis.key] = axis

    # -- writing ---------------------------------------------------------

    def _apply(self, record: dict, axis: TrackAxis, value: object, *,
               by: Mapping[str, object], at: str) -> bool:
        if not axis.accepts(value):
            raise TrackingError(
                f"Axis {axis.key!r} ({entity(type(axis)).name}) does not accept {value!r}")
        entry = record["axes"].get(axis.key)
        change = {"at": at, "value": value, "by": _plain(dict(by))}
        if entry is None:
            workflow = entity(type(axis)).workflow_ship
            record["axes"][axis.key] = {
                "type": entity(type(axis)).name,
                "owner_workflow": str(workflow) if workflow is not None else None,
                "value": value, "since": at, "data": {}, "history": [change],
            }
            return True
        if entry["value"] == value:
            return False
        entry.update(value=value, since=at)
        entry["history"].append(change)
        return True

    def _load(self) -> dict[str, dict]:
        records, unreadable = self.store.load_all()
        for problem in unreadable:
            emit_notification(TrackRecordUnreadable(
                f"Track record skipped: {problem['path']}", details=problem))
        return records

    # tarav.breadcrumb 215b93903c2fb28603ac1c58a6f14bbffed42eda0b75c571eb8bcc42d95957c8
    def observe(self, points: Iterable[CheckObservation], *, whole: bool = False,
                at: datetime | None = None) -> dict[str, object]:
        """Record one run's evidence.

        A raised POI is active. A record whose owning check completed without
        raising it has passed. Anything else is no evidence: the owning check
        did not complete, or, when `whole` says these points are the provider's
        entire suite, it did not run or cannot say which check it is.
        """
        if type(whole) is not bool:
            raise TypeError("whole must be explicit")
        stamp = _stamp(at)
        observation = self.axes[ObservationAxis.key]
        records = self._load()
        before = {poi_id: json.dumps(record, sort_keys=True) for poi_id, record in records.items()}
        completed: dict[str, bool] = {}
        touched: set[str] = set()
        counts: Counter[str] = Counter()
        for point in points:
            if not isinstance(point, CheckObservation):
                raise TypeError("observe() takes CheckObservation data points")
            counts["points"] += 1
            if point.check_identity is None:
                counts["points_without_check_identity"] += 1
            else:
                completed[point.check_identity] = (
                    completed.get(point.check_identity, True) and point.completed)
            for poi in point.pois:
                if not (isinstance(poi, TrackablePOI) and isinstance(poi, IdentifiedPOI)
                        and poi.tracking_enabled()):
                    counts["pois_not_tracked"] += 1
                    continue
                snapshot = _plain(poi.as_dict(detail=True))
                snapshot.pop("help", None)  # source paths are machine-local
                record = records.get(poi.identity)
                if record is None:
                    counts["created"] += 1
                    record = records[poi.identity] = {
                        "type": entity(TrackRecord).name, "schema_version": 1,
                        "id": str(TrackRecord.identity_for(poi.identity)),
                        "poi_id": poi.identity, "poi_type_id": poi.class_id,
                        "poi": snapshot, "check": {}, "first_tracked_at": stamp, "axes": {},
                    }
                record["poi"] = snapshot
                record["check"] = {"type": point.check_type, "identity": point.check_identity}
                self._apply(record, observation, ACTIVE, at=stamp, by={
                    "kind": "check-run", "check": point.check_type,
                    "check_identity": point.check_identity, "status": point.status})
                record["axes"][observation.key]["data"].update(
                    last_active_at=stamp, last_evaluated_at=stamp)
                touched.add(poi.identity)
        for poi_id, record in records.items():
            if poi_id in touched:
                continue
            owner = record["check"].get("identity")
            by = {"kind": "check-run", "check": record["check"].get("type"),
                  "check_identity": owner}
            if owner is not None and owner in completed:
                if completed[owner]:
                    self._apply(record, observation, PASSED, at=stamp,
                                by={**by, "status": "completed"})
                    record["axes"][observation.key]["data"]["last_evaluated_at"] = stamp
                else:
                    self._apply(record, observation, NOT_EVALUATED, at=stamp,
                                by={**by, "reason": "the owning check did not complete"})
            elif whole:
                self._apply(record, observation, NOT_EVALUATED, at=stamp, by={
                    **by, "reason": "the owning check did not run or states no identity"})
        for axis in self.axes.values():
            for record in records.values():
                derived = axis.derive(record)
                if derived is not _UNDERIVED:
                    self._apply(record, axis, derived, at=stamp, by={
                        "kind": "axis-derivation", "axis": entity(type(axis)).name})
        for poi_id, record in records.items():
            if before.get(poi_id) != json.dumps(record, sort_keys=True):
                self.store.write(record)
                counts["written"] += 1
        return {
            "at": stamp, "store": str(self.store.root), "records": len(records),
            "points": counts["points"],
            "points_without_check_identity": counts["points_without_check_identity"],
            "created": counts["created"], "written": counts["written"],
            "pois_not_tracked": counts["pois_not_tracked"],
            "by_axis": _by_axis(records.values()),
        }

    def set(self, poi_id: str, *, axis: str, value: object, by: Mapping[str, object],
            at: datetime | None = None) -> dict:
        """Write one caller-owned axis of one record; other axes are untouched."""
        if axis not in self.axes:
            raise TrackingError(f"Unknown axis {axis!r}; contributed: {', '.join(self.axes)}")
        selected = self.axes[axis]
        if not selected.caller_writable:
            raise TrackingError(f"Axis {axis!r} is written only by its owner")
        if not isinstance(by, Mapping) or not by:
            raise TrackingError("An axis change names who or what made it")
        matches = self.store.find(poi_id)
        if len(matches) != 1:
            raise TrackingError(f"{len(matches)} track records match {poi_id!r}")
        record = matches[0]
        if self._apply(record, selected, value, by=by, at=_stamp(at)):
            self.store.write(record)
        return record

    # -- reading ---------------------------------------------------------

    def records(self, *, axes: Mapping[str, object] | None = None,
                poi_type: str | None = None, check: str | None = None) -> list[dict]:
        """Records matching every given axis value; derived axes show their current value.

        Reading never writes: a derived value newer than the stored one is
        shown, and enters the history at the next observation.
        """
        wanted = dict(axes or {})
        unknown = [key for key in wanted if key not in self.axes]
        if unknown:
            raise TrackingError(
                f"Unknown axis {unknown[0]!r}; contributed: {', '.join(self.axes)}")
        selected = []
        for record in self._load().values():
            for axis in self.axes.values():
                derived = axis.derive(record)
                if derived is _UNDERIVED:
                    continue
                entry = record["axes"].setdefault(axis.key, {
                    "type": entity(type(axis)).name, "value": derived, "history": []})
                entry["value"] = derived
            vector = status_vector(record)
            if any(key not in vector or str(vector[key]) != str(value)
                   for key, value in wanted.items()):
                continue
            if poi_type is not None and record["poi"].get("type") != poi_type:
                continue
            if check is not None and record["check"].get("type") != check:
                continue
            selected.append(record)
        return sorted(selected, key=lambda record: (record["poi"].get("type", ""),
                                                    record["poi_id"]))

    def report(self, *, axes: Mapping[str, object] | None = None,
               poi_type: str | None = None, check: str | None = None,
               offset: int = 0, limit: int = 20) -> dict[str, object]:
        if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 1:
            raise ValueError("Expected nonnegative offset and positive limit")
        everything = self.records()
        selected = self.records(axes=axes, poi_type=poi_type, check=check)
        page = selected[offset:offset + limit]
        return {
            "store": str(self.store.root), "total": len(everything),
            "matching": len(selected), "offset": offset, "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "by_axis": _by_axis(everything),
            "items": [{
                "id": record["poi_id"], "type": record["poi"].get("type"),
                "message": record["poi"].get("message"), "check": record["check"],
                "axes": status_vector(record), "record": record,
            } for record in page],
        }


def _by_axis(records: Iterable[Mapping[str, object]]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    for record in records:
        for key, value in status_vector(record).items():
            counts.setdefault(key, Counter())[str(value)] += 1
    return {key: dict(values) for key, values in counts.items()}


POI_TRACKING_RECORD_TYPES = (TrackRecord, TrackRecordUnreadable)

__all__ = [
    "ACTIVE",
    "NOT_EVALUATED",
    "PASSED",
    "POI_TRACKING_RECORD_TYPES",
    "POI_TRACKING_WORKFLOW_SHIP",
    "TRACKED_POI_VIEW",
    "CheckObservation",
    "ObservationAxis",
    "POITracker",
    "POITrackingWorkflow",
    "TrackAxis",
    "TrackRecord",
    "TrackRecordStore",
    "TrackRecordUnreadable",
    "TrackablePOI",
    "TrackingError",
    "status_vector",
]
