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


def type_named(base: type, name: str) -> type | None:
    """The Type of this name among `base` and its subclasses defined in the running code."""
    pending = [base]
    while pending:
        candidate = pending.pop()
        if entity(candidate).name == name:
            return candidate
        pending.extend(candidate.__subclasses__())
    return None


def plain(value):
    """Free data of a POI as JSON data, for its record: a tuple becomes a list."""
    return json.loads(json.dumps(value, allow_nan=False))


# tarav.breadcrumb 0e47f7f09769ba32c37969a636c8480ceef794d03f21b3306cfed321b6c1bdf7
class POI(TaravObject):
    """A point of interest: the statement that an event happened.

    Like an error, a POI is an object with a Type and an elementary message,
    and that is all the base holds. Creating one does nothing; what is done
    with it is the caller's act. A specialization adds what it needs as
    fields of its own Type.
    """

    # tarav.breadcrumb fbce893f8a509ccd3120c6f50be4e69a32ff924ed42d9cef1af7857d8dc86efb
    #: Descriptive sentences this Type adds to its POIs' context: what the POI
    #: means, where its producer's documentation is, what is known to make it
    #: stop being raised. They are not part of the POI's record.

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("67634f40-7209-43ee-9bbb-7590b2fe5e59"),
            name="Tarav.POI",
            workflow=POI_WORKFLOW_SHIP,
        )

    # tarav.breadcrumb 17627641c140831a58058d274ae60618c5ddcfb654b3f2d8b748518b3d76c0bd
    def __init__(self, message: str) -> None:
        super().__init__()
        if not isinstance(message, str):
            raise TypeError("A POI's message must be text")
        self.message = message

    class RecordInterface(TaravObject.RecordInterface):
        type: str
        message: str

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "message": self.message}

    @classmethod
    def _from_record(cls, record_data):
        result = super()._from_record(record_data)
        result.message = record_data.message
        return result

    class Records(TaravObject.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "message": "Synthetic POI"}

    def summary(self) -> str:
        """One POI's meaning; layout belongs to a renderer."""
        if self.message.strip():
            return self.message.strip()
        return (type(self).__doc__ or "").strip() or entity(type(self)).name

    # tarav.breadcrumb 0216682f0099c00e834aa725e6214609154e74337b7c0ea50bf53d32d5b6948e
    # tarav.breadcrumb 2f1b1fe8f260aab8fdc6686a018c0a67690193baef77db8ad977f39e23e73a84
    def throw(self) -> None:
        """Raise this POI as a `POIError` that carries it, for a caller that wants to stop."""
        raise POIError(self)


# tarav.breadcrumb f79017e17d4716cf2da6b9734b2c2a6737ed9facccf0ad524505fda4a9d8cc10
class SituationPOI(POI):
    """A POI about a situation: an object that describes what was found, and where.

    The situation is a `LiteRecord`; what goes into it is for each line of
    POIs to decide. The same Type with the same situation is the same POI:
    that is its identity. Nothing else is required or offered here.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d341dcd8-6155-4588-b881-bdfb4ba0bc4e"),
            name="Tarav.POI.Situation",
            workflow=POI_WORKFLOW_SHIP,
        )

    def __init__(self, message: str, *, situation: Mapping[str, object] | LiteRecord) -> None:
        super().__init__(message)
        # The Type states which situation was found; there is no case label.
        self._situation = LiteRecord(situation)
        self.class_id = str(entity(type(self)).id)
        self.identity = fingerprint([self.class_id, self.situation])

    @property
    def situation(self) -> dict[str, object]:
        return self._situation.to_json_value()

    class RecordInterface(POI.RecordInterface):
        class_id: str
        id: str
        situation: dict

    def _to_record(self) -> dict[str, object]:
        """The Type, the message, the situation, and the identity those give."""
        return {**super()._to_record(), "class_id": self.class_id, "id": self.identity,
                "situation": self.situation}

    @classmethod
    def _from_record(cls, record_data):
        result = super()._from_record(record_data)
        result._situation = LiteRecord(record_data.situation)
        result.class_id = str(entity(cls).id)
        result.identity = fingerprint([result.class_id, result.situation])
        if (record_data.class_id, record_data.id) != (result.class_id, result.identity):
            raise ValueError("A POI record's identity does not match its Type and situation")
        return result

    class Records(POI.Records):
        def record_example(self) -> dict[str, object]:
            class_id, situation = str(entity(self._owner).id), {"example": "situation"}
            return {**super().record_example(), "class_id": class_id,
                    "id": fingerprint([class_id, situation]), "situation": situation}

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
        super().__init__(message)
        self.details = deepcopy(details or {})

    class RecordInterface(POI.RecordInterface):
        details: dict

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "details": plain(self.details)}

    @classmethod
    def _from_record(cls, record_data):
        result = super()._from_record(record_data)
        result.details = deepcopy(record_data.details)
        return result

    class Records(POI.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "details": {}}

class POIDetails(FileRecord):
    """Plain JSON data of a POI exposed as an ordinary Context value."""

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
    def get(self, identity: str, *, index: int | None = None) -> SituationPOI:
        if not isinstance(identity, str) or not identity:
            raise ValueError("Expected a nonempty POI ID or prefix")
        if index is not None and (type(index) is not int or index < 0):
            raise ValueError("POI emission index must be a nonnegative integer")
        matches = [
            poi
            for poi in self.pois
            if isinstance(poi, SituationPOI) and poi.identity.startswith(identity)
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
        offset=0,
        limit=20,
        class_name=None,
    ):
        if offset < 0 or limit < 1:
            raise ValueError("Expected nonnegative offset and positive limit")
        identity_counts = Counter(
            poi.identity for poi in self.pois if isinstance(poi, SituationPOI)
        )
        next_index: Counter[str] = Counter()
        rows = []
        for poi in self.pois:
            emission_index = None
            if isinstance(poi, SituationPOI):
                emission_index = next_index[poi.identity]
                next_index[poi.identity] += 1
            rows.append((poi, emission_index))
        rows.sort(
            key=lambda row: (
                getattr(row[0], "identity", ""),
                entity(type(row[0])).name,
                row[1] if row[1] is not None else -1,
            )
        )
        selected = [
            (poi, emission_index)
            for poi, emission_index in rows
            if class_name is None or entity(type(poi)).name == class_name
        ]
        page = []
        for poi, emission_index in selected[offset : offset + limit]:
            row = (
                poi.records.to_record()
            )
            if (
                isinstance(poi, SituationPOI)
                and identity_counts[poi.identity] > 1
            ):
                row["index"] = emission_index
            page.append(row)
        return {
            "total": len(rows),
            "matching": len(selected),
            "offset": offset,
            "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "by_class": dict(Counter(entity(type(poi)).name for poi, _ in rows)),
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
