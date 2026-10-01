"""Neutral POI values, identified occurrences, collection, and notification delivery."""

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
import warnings

from tarav.l0.kernel import FileRecord, TaravClass, TaravObject, TypeShip, entity

from .workflow import POI_WORKFLOW_SHIP


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class POI(TaravObject):
    """A point of interest. Specialized workflows define its meaning."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("67634f40-7209-43ee-9bbb-7590b2fe5e59"),
            name="Tarav.POI",
            workflow=POI_WORKFLOW_SHIP,
        )

    def as_dict(self) -> dict[str, object]:
        return {"type": entity(type(self)).name}


class IdentifiedPOI(POI):
    """A workflow-owned POI occurrence with stable concern and evidence identities."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d341dcd8-6155-4588-b881-bdfb4ba0bc4e"),
            name="Tarav.POI.Identified",
            workflow=POI_WORKFLOW_SHIP,
        )

    def __init__(
        self,
        code: str,
        message: str,
        *,
        subject: dict | None = None,
        evidence: dict | None = None,
    ) -> None:
        super().__init__()
        if not isinstance(code, str) or not code:
            raise ValueError("IdentifiedPOI requires a nonempty code")
        if not isinstance(message, str):
            raise TypeError("IdentifiedPOI message must be text")
        self.code = code
        self.message = message
        self._subject = canonical(subject or {})
        self._evidence = canonical(evidence or {})
        self.class_id = str(entity(type(self)).id)
        self.identity = fingerprint([self.class_id, self.subject])
        self.state = fingerprint([self.identity, self.evidence])

    @property
    def subject(self) -> dict:
        return json.loads(self._subject)

    @property
    def evidence(self) -> dict:
        return json.loads(self._evidence)

    @property
    def coordinate(self) -> dict:
        return self.subject

    def as_dict(self, *, detail: bool = False) -> dict[str, object]:
        result = {
            "type": entity(type(self)).name,
            "class_id": self.class_id,
            "id": self.identity,
            "state": self.state,
            "code": self.code,
            "message": self.message,
            "subject": self.subject,
            "help": deepcopy(type(self).help()),
        }
        if detail:
            result["evidence"] = self.evidence
        return result

    def obj_context(self, builder) -> None:
        builder.add("coordinate", opener=lambda: _details(self.coordinate))
        builder.add("evidence", opener=lambda: _details(self.evidence))


class NotificationPOI(POI):
    """An operation or event worth showing without implying failure."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d4ac1ae7-63c3-42c9-8b78-6026cd072a69"),
            name="Tarav.POI.Notification",
            workflow=POI_WORKFLOW_SHIP,
        )

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__()
        self.code = code
        self.message = message
        self.details = deepcopy(details or {})

    def as_dict(self) -> dict[str, object]:
        return {
            "type": entity(type(self)).name,
            "code": self.code,
            "message": self.message,
            "details": deepcopy(self.details),
        }

    def obj_context(self, builder):
        builder.add("details", opener=lambda: _details(self.details))


class POIDetails(FileRecord):
    """JSON coordinates or evidence exposed as an ordinary Context value."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("1a61795f-5db6-4b52-982e-b2a0881d625e"),
            name="Tarav.POI.Details",
            workflow=POI_WORKFLOW_SHIP,
        )


def _details(value) -> POIDetails:
    return POIDetails.from_record(
        {"type": entity(POIDetails).name, "value": deepcopy(value)}
    )


class POIError(Exception):
    def __init__(self, poi: POI):
        self.poi = poi
        name = entity(type(poi)).name
        if getattr(poi, "check", None) is not None:
            name = entity(type(poi.check)).name
        super().__init__(f"{name}: {getattr(poi, 'identity', getattr(poi, 'code', 'POI'))}")


class POICollector:
    """Retain every emission. Paging and filtering affect only presentation."""

    def __init__(self):
        self.pois: list[POI] = []

    def emit(self, poi: POI):
        if not isinstance(poi, POI):
            raise TypeError("Expected POI")
        self.pois.append(poi)
        return poi

    def get(self, identity: str) -> IdentifiedPOI:
        if not isinstance(identity, str) or not identity:
            raise ValueError("Expected a nonempty POI ID or prefix")
        matches = [
            poi
            for poi in self.pois
            if isinstance(poi, IdentifiedPOI) and poi.identity.startswith(identity)
        ]
        if not matches:
            raise ValueError("POI does not exist in this evaluation")
        if len({poi.identity for poi in matches}) != 1:
            raise ValueError("Ambiguous POI ID prefix; use a longer prefix")
        if len({poi.state for poi in matches}) != 1:
            raise ValueError("POI identity has conflicting current states")
        return matches[0]

    def report(
        self,
        *,
        store=None,
        offset=0,
        limit=20,
        class_name=None,
        blessing=None,
        detail=False,
    ):
        if offset < 0 or limit < 1:
            raise ValueError("Expected nonnegative offset and positive limit")
        if blessing not in (None, "unblessed", "blessed", "stale"):
            raise ValueError("Unknown blessing filter")
        snapshot = store.snapshot() if store else None
        rows = []
        for poi in sorted(
            self.pois,
            key=lambda value: (
                getattr(value, "identity", ""),
                getattr(value, "state", ""),
                entity(type(value)).name,
            ),
        ):
            standing = (
                store.standing(poi, snapshot=snapshot)
                if store is not None and store.accepts(poi)
                else None
            )
            rows.append((poi, standing))
        selected = [
            (poi, standing)
            for poi, standing in rows
            if (class_name is None or entity(type(poi)).name == class_name)
            and (blessing is None or standing is not None and standing["status"] == blessing)
        ]
        page = []
        for poi, standing in selected[offset : offset + limit]:
            row = (
                poi.as_dict(detail=detail)
                if isinstance(poi, IdentifiedPOI)
                else poi.as_dict()
            )
            if standing is not None:
                row["blessing"] = standing
            page.append(row)
        return {
            "total": len(rows),
            "matching": len(selected),
            "offset": offset,
            "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "by_class": dict(Counter(entity(type(poi)).name for poi, _ in rows)),
            "by_blessing": dict(
                Counter(standing["status"] for _, standing in rows if standing is not None)
            ),
            "by_assessment_finding": dict(
                Counter(
                    finding["kind"]
                    for _, standing in rows
                    for finding in (standing or {}).get("assessment_findings", [])
                )
            ),
            "store_findings": snapshot["findings"] if snapshot else [],
            "items": page,
        }


class POINotificationWarning(UserWarning):
    """Default visible delivery for an emitted NotificationPOI."""

    def __init__(self, poi: NotificationPOI):
        self.poi = poi
        super().__init__(poi.message)


_notification_collector: ContextVar[POICollector | None] = ContextVar(
    "tarav_poi_notification_collector", default=None
)


def emit_notification(poi: NotificationPOI) -> NotificationPOI:
    """Emit once: collect explicitly when bound, otherwise use visible warnings."""

    if not isinstance(poi, NotificationPOI):
        raise TypeError("Expected NotificationPOI")
    collector = _notification_collector.get()
    if collector is None:
        warnings.warn(POINotificationWarning(poi), stacklevel=2)
    else:
        collector.emit(poi)
    return poi


@contextmanager
def collect_notifications(collector: POICollector | None = None):
    """Collect notifications emitted in this context instead of warning."""

    selected = collector or POICollector()
    token = _notification_collector.set(selected)
    try:
        yield selected
    finally:
        _notification_collector.reset(token)
