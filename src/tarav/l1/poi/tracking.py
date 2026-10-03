"""Explicit tracking of identified POIs within declared evaluation scopes."""

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from tarav.l0.kernel import FileRecord, LiteRecord, Ship, TaravClass, TaravEntity, TypeShip, entity

from .primitives import IdentifiedPOI, POICollector, fingerprint
from .workflow import POI_WORKFLOW_SHIP


def _scope(value):
    return LiteRecord(value).to_json_value()


def _timestamp(value):
    current = datetime.now(timezone.utc) if value is None else value
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("Evaluation time must be a timezone-aware datetime")
    return current.astimezone(timezone.utc).isoformat()


# tarav.breadcrumb cc154b05f97dcc4cdee84f18c2dd5178b471042445ba1e888c393142176c2860
# tarav.breadcrumb 495ae70b5cbc75b59518fe4e9a60c81b134fc0b15a57b4d5804ad327ceb4a67c
class TrackedPOI(TaravEntity, FileRecord):
    """One POI situation tracked by choice, independently of its disposition."""

    class RecordInterface(TaravEntity.RecordInterface):
        schema_version: int
        poi_id: str
        poi_type_id: str
        owner_workflow: str
        scope: dict
        poi: dict
        detected: bool
        history: list[dict]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("28d4c231-8321-4658-8564-71f27f9c2f37"),
            name="Tarav.POI.Tracked",
            workflow=POI_WORKFLOW_SHIP,
        )

    @classmethod
    def identity_for(cls, poi_id):
        return Ship(uuid5(UUID(str(entity(cls).id)), poi_id))

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        if data.schema_version != 1:
            raise ValueError("Unsupported tracked POI schema")
        if data.id != cls.identity_for(data.poi_id):
            raise ValueError("Tracked identity disagrees with POI situation")
        TypeShip(data.poi_type_id)
        UUID(data.owner_workflow)
        _scope(data.scope)
        if (data.poi.get("id") != data.poi_id
                or data.poi.get("class_id") != data.poi_type_id
                or fingerprint([data.poi_type_id, data.poi.get("situation")]) != data.poi_id):
            raise ValueError("Tracked POI snapshot disagrees with identity")
        if not data.history:
            raise ValueError("Tracked POI requires an observation history")
        for observation in data.history:
            if not isinstance(observation, dict) or type(observation.get("detected")) is not bool:
                raise ValueError("Invalid tracked POI observation")
            _timestamp(datetime.fromisoformat(observation["at"]))
            prior = observation.get("poi")
            if prior is not None and (not isinstance(prior, dict)
                                      or prior.get("id") != data.poi_id
                                      or prior.get("class_id") != data.poi_type_id):
                raise ValueError("Observation belongs to another POI situation")
        return data

    @classmethod
    def from_poi(cls, poi: IdentifiedPOI, *, scope: Mapping, at=None):
        if not isinstance(poi, IdentifiedPOI):
            raise TypeError("Only identified POIs can be tracked")
        stamp = _timestamp(at)
        record = {
            "type": entity(cls).name,
            "schema_version": 1,
            "id": str(cls.identity_for(poi.identity)),
            "poi_id": poi.identity,
            "poi_type_id": poi.class_id,
            "owner_workflow": str(entity(type(poi)).workflow_ship),
            "scope": _scope(scope),
            "poi": poi.as_dict(detail=True),
            "detected": True,
            "history": [{"at": stamp, "detected": True,
                         "poi": poi.as_dict(detail=True)}],
        }
        return cls.from_record(record)

    @classmethod
    def record_example(cls):
        poi = {
            "type": "Example.POI", "class_id": "7d28d632-2ec5-4c5a-997f-224ad508ce9d",
            "situation": {"example": 1}, "subject": {}, "evidence": {},
        }
        poi["id"] = fingerprint([poi["class_id"], poi["situation"]])
        return {
            "type": entity(cls).name, "schema_version": 1,
            "id": str(cls.identity_for(poi["id"])), "poi_id": poi["id"],
            "poi_type_id": poi["class_id"],
            "owner_workflow": str(POI_WORKFLOW_SHIP), "scope": {"example": 1},
            "poi": poi, "detected": True,
            "history": [{"at": "2026-10-03T00:00:00+00:00", "detected": True,
                         "poi": poi}],
        }


class TrackedPOIStore:
    """A caller-rooted board store; ownership is a separate Record field."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def snapshot(self):
        records, findings = [], []
        if not self.root.exists():
            return {"records": records, "findings": findings}
        for path in sorted(self.root.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                TrackedPOI.validate_record(record)
                if path.stem != record["id"]:
                    raise ValueError("Tracked POI filename disagrees with identity")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                findings.append({"kind": "invalid-tracked-poi", "path": str(path),
                                 "detail": str(exc)})
                continue
            records.append(record)
        return {"records": records, "findings": findings}

    def load(self, poi_id):
        identity = str(TrackedPOI.identity_for(poi_id))
        path = self.root / f"{identity}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        TrackedPOI.validate_record(record)
        return TrackedPOI.from_record(record)

    def track(self, poi: IdentifiedPOI, *, scope: Mapping, at=None):
        tracked = TrackedPOI.from_poi(poi, scope=scope, at=at)
        path = self.root / f"{tracked.id}.json"
        self.root.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(tracked.to_record(), handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        return tracked

    def reconcile(self, collector: POICollector, *, scope: Mapping,
                  completed: bool, at=None):
        """Absence is evidence only for a successfully completed exact scope."""
        if not isinstance(collector, POICollector):
            raise TypeError("Expected a POICollector")
        if type(completed) is not bool:
            raise TypeError("Completion must be explicit")
        if not completed:
            return self.snapshot()
        selected_scope = _scope(scope)
        stamp = _timestamp(at)
        emitted = {}
        for poi in collector.pois:
            if not isinstance(poi, IdentifiedPOI):
                raise TypeError("Tracked evaluations require identified POIs")
            emitted[poi.identity] = poi
        snapshot = self.snapshot()
        if snapshot["findings"]:
            raise ValueError("Cannot reconcile a store with invalid tracked records")
        existing = {row["poi_id"]: row for row in snapshot["records"]}
        for poi_id, poi in emitted.items():
            previous = existing.get(poi_id)
            if previous is not None and previous["scope"] != selected_scope:
                raise ValueError("POI is already tracked under another evaluation scope")
        for poi_id, poi in emitted.items():
            if poi_id not in existing:
                self.track(poi, scope=selected_scope, at=at)
        for previous in snapshot["records"]:
            if previous["scope"] != selected_scope:
                continue
            detected = previous["poi_id"] in emitted
            updated = dict(previous)
            updated["detected"] = detected
            current_poi = emitted[previous["poi_id"]].as_dict(detail=True) if detected else None
            if detected:
                updated["poi"] = current_poi
            if detected != previous["detected"] or detected and current_poi != previous["poi"]:
                updated["history"] = [*previous["history"],
                                      {"at": stamp, "detected": detected,
                                       **({"poi": current_poi} if detected else {})}]
                self._replace(updated)
        return self.snapshot()

    def _replace(self, record):
        TrackedPOI.validate_record(record)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{record['id']}.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root,
                                         prefix=".tracked-", suffix=".json",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
