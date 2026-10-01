"""Application-owned POI classes, non-throwing collection, and bounded views."""
import hashlib
import json
from collections import Counter
from uuid import UUID, uuid5

from pydantic import model_validator

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TaravObject, entity
from tarav.l0.kernel import FileRecord, TypeShip
from .workflow import POI_WORKFLOW_SHIP


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class POICheck(FileRecord):
    """Extensible check declaration. Consumers own how and when it runs."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('b50c547e-323d-4438-b466-8654800f226c'),
                          name='Tarav.POI.Check', workflow=POI_WORKFLOW_SHIP)

    blessable = False
    check_version = 1

    @classmethod
    def finding(cls, subject, *, evidence=None):
        return POIFinding(cls, subject, evidence if evidence is not None else {})


# tarav.breadcrumb 68dda606d6ef2ed5711488bb952bbcacf278c1c2b6c1252738e0665c6885b48e
class POI(TaravObject):
    """A point of interest. Specialized workflows define its meaning."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('67634f40-7209-43ee-9bbb-7590b2fe5e59'),
            name='Tarav.POI',
            workflow=POI_WORKFLOW_SHIP,
        )

    def as_dict(self) -> dict[str, object]:
        return {'type': entity(type(self)).name}


class NotificationPOI(POI):
    """An operation or event worth showing without implying failure."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('d4ac1ae7-63c3-42c9-8b78-6026cd072a69'),
            name='Tarav.POI.Notification',
            workflow=POI_WORKFLOW_SHIP,
        )

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__()
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, object]:
        return {'type': entity(type(self)).name, 'code': self.code,
                'message': self.message, 'details': dict(self.details)}

    # tarav.breadcrumb 462d77217023b71b5716e1fe68c4e3111cebca14f5df880365651773e88b2e59
    def obj_context(self, builder):
        builder.add('details', opener=lambda: POIDetails.from_record(
            {'type': entity(POIDetails).name, 'value': self.details}))


class POIDetails(FileRecord):
    """JSON coordinates or evidence exposed as an ordinary Context value."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('1a61795f-5db6-4b52-982e-b2a0881d625e'),
                          name='Tarav.POI.Details', workflow=POI_WORKFLOW_SHIP)


class POIError(Exception):
    def __init__(self, poi):
        self.poi = poi
        check = poi.check
        name = check.name if isinstance(check, TaravClass) else entity(type(check)).name
        super().__init__(f'{name}: {getattr(poi, "identity", getattr(poi, "code", "POI"))}')


class POIInstance(TaravEntity, POI, FileRecord):
    """An identified concern at a coordinate, with a retained check/evidence state.

    Repeated observations of the same concern share a Ship. State fingerprints
    distinguish evidence editions; the collector still retains every emission.
    """

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('d341dcd8-6155-4588-b881-bdfb4ba0bc4e'),
                          name='Tarav.POIInstance', workflow=POI_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        check: dict
        check_help: dict
        check_version: int
        blessable: bool
        subject: dict
        evidence: dict
        identity: str
        state: str

        @model_validator(mode='after')
        def consistent(self):
            check = TaravClass.from_record(self.check)
            identity = fingerprint([str(check.id), self.subject])
            if self.identity != identity or self.state != fingerprint(
                [identity, self.check_version, self.evidence]
            ):
                raise ValueError('POI identity/state disagrees with retained evidence')
            if self.id != POIInstance.ship_for(identity):
                raise ValueError('POI Ship disagrees with concern identity')
            return self

    @staticmethod
    def ship_for(identity):
        return Ship(uuid5(UUID('d341dcd8-6155-4588-b881-bdfb4ba0bc4e'), identity))

    def __init__(self, poi_class, subject, evidence):
        if not isinstance(poi_class, type) or not issubclass(poi_class, POICheck):
            raise TypeError('Expected a POICheck subclass')
        if not isinstance(subject, dict) or not isinstance(evidence, dict):
            raise ValueError('Subject and evidence must be objects')
        self.poi_class = poi_class
        self.check = entity(poi_class)
        self._check_help = canonical(poi_class.help())
        self._blessable = poi_class.blessable
        self._subject = canonical(subject)
        self._evidence = canonical(evidence)
        self.class_id = str(entity(poi_class).id)
        self.check_version = poi_class.check_version
        self.identity = fingerprint([self.class_id, subject])
        self.state = fingerprint([self.identity, self.check_version, evidence])
        super().__init__(self.ship_for(self.identity))

    @property
    def blessable(self):
        return self.poi_class.blessable if self.poi_class is not None else self._blessable

    @property
    def coordinate(self):
        return self.subject

    def error(self):
        """Explicit interruption; constructing or collecting a POI never raises it."""
        raise POIError(self)

    def resolve_check(self, records):
        """Resolve through an explicitly supplied trusted registry, never a path."""
        check_type = records.resolve_ship(self.check.id)
        if not issubclass(check_type, POICheck) or entity(check_type).id != self.check.id:
            raise TypeError('Registered check does not match retained check identity')
        return entity(check_type)

    def ships(self):
        return (*super().ships(), self.check.id)

    def obj_context(self, builder):
        builder.add('check', opener=lambda: self.check)
        builder.add('check-help', opener=lambda: POIDetails.from_record(
            {'type': entity(POIDetails).name, 'value': json.loads(self._check_help)}))
        builder.add('coordinate', opener=lambda: POIDetails.from_record(
            {'type': entity(POIDetails).name, 'value': self.coordinate}))
        builder.add('evidence', opener=lambda: POIDetails.from_record(
            {'type': entity(POIDetails).name, 'value': self.evidence}))

    def _to_record(self):
        return {**super()._to_record(), 'check': self.check.to_record(),
                'check_help': json.loads(self._check_help),
                'check_version': self.check_version, 'blessable': self._blessable,
                'subject': self.subject, 'evidence': self.evidence,
                'identity': self.identity, 'state': self.state}

    @classmethod
    def _from_record(cls, data):
        result = cls.__new__(cls)
        TaravEntity.__init__(result, data.id)
        result.poi_class = None  # Retained Python paths never authorize imports.
        result.check = TaravClass.from_record(data.check)
        result.class_id = str(result.check.id)
        result._check_help = canonical(data.check_help)
        result._blessable = data.blessable
        result.check_version = data.check_version
        result._subject = canonical(data.subject)
        result._evidence = canonical(data.evidence)
        result.identity, result.state = data.identity, data.state
        return result

    @classmethod
    def record_example(cls):
        return cls(POICheck, {'example': 'coordinate'}, {}).to_record()

    @property
    def subject(self):
        return json.loads(self._subject)

    @property
    def evidence(self):
        return json.loads(self._evidence)

    def as_dict(self, *, detail=False):
        context = json.loads(self._check_help)
        if not context.get('hints'):
            context.pop('hints', None)
        result = {'id': self.identity, 'entity_id': str(self.id), 'state': self.state,
                  'type': self.check.name, 'class_id': self.class_id,
                  'check_version': self.check_version, 'subject': self.subject,
                  'blessable': self.blessable,
                  'help': context}
        if detail:
            result['evidence'] = self.evidence
        return result


class POIFinding(POIInstance):
    """The observation emitted by a POICheck."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('98db26a0-1bbc-45e8-89a8-98e2bce59f68'),
                          name='Tarav.POI.Finding', workflow=POI_WORKFLOW_SHIP)


class POICollector:
    """Retain every emission. Paging/filtering affects only presentation."""

    def __init__(self):
        self.findings = []

    def emit(self, finding):
        if not isinstance(finding, POI):
            raise TypeError('Expected POI')
        self.findings.append(finding)
        return finding

    def get(self, identity):
        """Select a full identity or a unique nonempty identity prefix."""
        if not isinstance(identity, str) or not identity:
            raise ValueError('Expected a nonempty finding ID or prefix')
        matches = [f for f in self.findings if isinstance(f, POIInstance)
                   if f.identity.startswith(identity) or str(f.id).startswith(identity)]
        if not matches:
            raise ValueError('Finding does not exist in this evaluation')
        if len({f.identity for f in matches}) != 1:
            raise ValueError('Ambiguous finding ID prefix; use a longer prefix')
        if len({f.state for f in matches}) != 1:
            raise ValueError('Finding identity has conflicting current states')
        return matches[0]

    def report(self, *, store=None, offset=0, limit=20, class_name=None,
               blessing=None, detail=False):
        if offset < 0 or limit < 1:
            raise ValueError('Expected nonnegative offset and positive limit')
        if blessing not in (None, 'unblessed', 'blessed', 'stale', 'disallowed'):
            raise ValueError('Unknown blessing filter')
        snapshot = store.snapshot() if store else None
        rows = []
        for finding in sorted(self.findings, key=lambda f: (
            getattr(f, 'identity', ''), getattr(f, 'state', ''), entity(type(f)).name)):
            standing = ((store.standing(finding, snapshot=snapshot) if store
                         else {'status': 'unblessed', 'records': []})
                        if isinstance(finding, POIInstance) else None)
            rows.append((finding, standing))
        selected = [(f, s) for f, s in rows
                    if (class_name is None or (
                        f.check.name if isinstance(f, POIInstance)
                        else entity(type(f)).name) == class_name)
                    and (blessing is None or (s is not None and s['status'] == blessing))]
        page = []
        for finding, standing in selected[offset:offset + limit]:
            row = (finding.as_dict(detail=detail) if isinstance(finding, POIInstance)
                   else finding.as_dict())
            if standing is not None:
                row['blessing'] = standing
            page.append(row)
        return {'total': len(rows), 'matching': len(selected), 'offset': offset,
                'shown': len(page), 'next_offset': offset + limit
                if offset + limit < len(selected) else None,
                'by_class': dict(Counter(f.check.name if isinstance(f, POIInstance)
                                         else entity(type(f)).name for f, _ in rows)),
                'by_blessing': dict(Counter(s['status'] for _, s in rows if s is not None)),
                'by_assessment_finding': dict(Counter(
                    f['kind'] for _, standing in rows
                    for f in (standing or {}).get('assessment_findings', []))),
                'store_findings': snapshot['findings'] if snapshot else [],
                'items': page}
