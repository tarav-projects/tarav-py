"""Neutral POI values, identified occurrences, collection, and notification delivery."""

from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json
import warnings

from tarav.l0.kernel import (
    FileRecord,
    LiteRecord,
    TaravClass,
    TaravObject,
    TypeShip,
    entity,
)

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


# tarav.breadcrumb 0e47f7f09769ba32c37969a636c8480ceef794d03f21b3306cfed321b6c1bdf7
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

    def summary(self) -> str:
        """One POI's meaning; layout belongs to a renderer."""
        message = getattr(self, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()
        return (type(self).__doc__ or "").strip() or entity(type(self)).name


class IdentifiedPOI(POI):
    """A workflow-owned POI with identity defined by its Type and situation."""

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
        message: str,
        *,
        situation: Mapping[str, object] | LiteRecord,
        subject: dict | None = None,
        evidence: dict | None = None,
    ) -> None:
        super().__init__()
        # The Type states which situation was found; there is no case label.
        if not isinstance(message, str):
            raise TypeError("IdentifiedPOI message must be text")
        self.message = message
        self._subject = canonical(subject or {})
        self._evidence = canonical(evidence or {})
        self._situation = LiteRecord(situation)
        self.class_id = str(entity(type(self)).id)
        self.identity = fingerprint([self.class_id, self.situation])

    @property
    def situation(self) -> dict[str, object]:
        return self._situation.to_json_value()

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
            "message": self.message,
            "situation": self.situation,
            "subject": self.subject,
            "help": deepcopy(type(self).help()),
        }
        if detail:
            result["evidence"] = self.evidence
        return result

    def obj_context(self, builder) -> None:
        builder.add("situation", opener=lambda: _details(self.situation))
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

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__()
        self.message = message
        self.details = deepcopy(details or {})

    def as_dict(self) -> dict[str, object]:
        return {
            "type": entity(type(self)).name,
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
    return POIDetails.records.from_record(
        {"type": entity(POIDetails).name, "value": deepcopy(value)}
    )


class POIError(Exception):
    def __init__(self, poi: POI):
        self.poi = poi
        name = entity(type(poi)).name
        if getattr(poi, "check", None) is not None:
            name = entity(type(poi.check)).name
        super().__init__(f"{name}: {getattr(poi, 'identity', 'POI')}")


class POICollector:
    """Retain every emission. Paging and filtering affect only presentation."""

    def __init__(self):
        self.pois: list[POI] = []

    def emit(self, poi: POI):
        if not isinstance(poi, POI):
            raise TypeError("Expected POI")
        self.pois.append(poi)
        return poi

    # tarav.breadcrumb 5eb40a749da9400fa0e6bc5526e6fb65f0e3004d7cf6193ba742b4ff9a4bac8f
    def get(self, identity: str, *, index: int | None = None) -> IdentifiedPOI:
        if not isinstance(identity, str) or not identity:
            raise ValueError("Expected a nonempty POI ID or prefix")
        if index is not None and (type(index) is not int or index < 0):
            raise ValueError("POI emission index must be a nonnegative integer")
        matches = [
            poi
            for poi in self.pois
            if isinstance(poi, IdentifiedPOI) and poi.identity.startswith(identity)
        ]
        if not matches:
            raise ValueError("POI does not exist in this evaluation")
        if len({poi.identity for poi in matches}) != 1:
            raise ValueError("Ambiguous POI ID prefix; use a longer prefix")
        if index is None:
            if len(matches) != 1:
                raise ValueError("POI identity has multiple emissions; provide index")
            return matches[0]
        if index >= len(matches):
            raise ValueError("POI emission index does not exist")
        return matches[index]

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
        if blessing not in (None, "unblessed", "blessed"):
            raise ValueError("Unknown blessing filter")
        snapshot = store.snapshot() if store else None
        identity_counts = Counter(
            poi.identity for poi in self.pois if isinstance(poi, IdentifiedPOI)
        )
        next_index: Counter[str] = Counter()
        rows = []
        for poi in self.pois:
            emission_index = None
            if isinstance(poi, IdentifiedPOI):
                emission_index = next_index[poi.identity]
                next_index[poi.identity] += 1
            standing = (
                store.standing(poi, snapshot=snapshot)
                if store is not None and store.accepts(poi)
                else None
            )
            rows.append((poi, standing, emission_index))
        rows.sort(
            key=lambda row: (
                getattr(row[0], "identity", ""),
                entity(type(row[0])).name,
                row[2] if row[2] is not None else -1,
            )
        )
        selected = [
            (poi, standing, emission_index)
            for poi, standing, emission_index in rows
            if (class_name is None or entity(type(poi)).name == class_name)
            and (blessing is None or standing is not None and standing["status"] == blessing)
        ]
        page = []
        for poi, standing, emission_index in selected[offset : offset + limit]:
            row = (
                poi.as_dict(detail=detail)
                if isinstance(poi, IdentifiedPOI)
                else poi.as_dict()
            )
            if (
                isinstance(poi, IdentifiedPOI)
                and identity_counts[poi.identity] > 1
            ):
                row["index"] = emission_index
            if standing is not None:
                row["blessing"] = standing
            page.append(row)
        return {
            "total": len(rows),
            "matching": len(selected),
            "offset": offset,
            "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "by_class": dict(Counter(entity(type(poi)).name for poi, _, _ in rows)),
            "by_blessing": dict(
                Counter(
                    standing["status"]
                    for _, standing, _ in rows
                    if standing is not None
                )
            ),
            "by_assessment_finding": dict(
                Counter(
                    finding["kind"]
                    for _, standing, _ in rows
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
