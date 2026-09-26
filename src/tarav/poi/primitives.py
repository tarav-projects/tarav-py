"""Application-owned POI classes, non-throwing collection, and bounded views."""
import hashlib
import json
from collections import Counter

from tarav.kernel import TaravClass, entity
from tarav.kernel import FileRecord, TypeShip


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class POI(FileRecord):
    """Subclass beside an application's checks. Emission does not raise.

    Declare a unique ``TaravClass`` through ``class_entity()``, as for any
    Tarav Type.
    blessable is explicit policy; a workflow still owns its response.
    Increment check_version when the evaluation contract changes.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('c8b62a96-070b-488a-b560-c0231f249b16'),
            name='Tarav.POI',
        )
    blessable = False
    check_version = 1

    @classmethod
    def finding(cls, subject, *, evidence=None):
        return POIFinding(cls, subject, evidence if evidence is not None else {})


class POIFinding:
    """A frozen JSON snapshot; navigation uses the trusted emitting class."""

    def __init__(self, poi_class, subject, evidence):
        if not isinstance(poi_class, type) or not issubclass(poi_class, POI):
            raise TypeError('Expected a POI subclass')
        if not isinstance(subject, dict) or not isinstance(evidence, dict):
            raise ValueError('Subject and evidence must be objects')
        self.poi_class = poi_class
        self._subject = canonical(subject)
        self._evidence = canonical(evidence)
        self.class_id = str(entity(poi_class).id)
        self.check_version = poi_class.check_version
        self.identity = fingerprint([self.class_id, subject])
        self.state = fingerprint([self.identity, self.check_version, evidence])

    @property
    def subject(self):
        return json.loads(self._subject)

    @property
    def evidence(self):
        return json.loads(self._evidence)

    def as_dict(self, *, detail=False):
        context = self.poi_class.help()
        if not context.get('hints'):
            context.pop('hints', None)
        result = {'id': self.identity, 'state': self.state,
                  'type': entity(self.poi_class).name, 'class_id': self.class_id,
                  'check_version': self.check_version, 'subject': self.subject,
                  'blessable': self.poi_class.blessable,
                  'help': context}
        if detail:
            result['evidence'] = self.evidence
        return result


class POICollector:
    """Retain every emission. Paging/filtering affects only presentation."""

    def __init__(self):
        self.findings = []

    def emit(self, finding):
        if not isinstance(finding, POIFinding):
            raise TypeError('Expected POIFinding')
        self.findings.append(finding)
        return finding

    def get(self, identity):
        """Select a full identity or a unique nonempty identity prefix."""
        if not isinstance(identity, str) or not identity:
            raise ValueError('Expected a nonempty finding ID or prefix')
        matches = [f for f in self.findings if f.identity.startswith(identity)]
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
        for finding in sorted(self.findings, key=lambda f: (f.identity, f.state)):
            standing = (store.standing(finding, snapshot=snapshot) if store
                        else {'status': 'unblessed', 'records': []})
            rows.append((finding, standing))
        selected = [(f, s) for f, s in rows
                    if (class_name is None or entity(f.poi_class).name == class_name)
                    and (blessing is None or s['status'] == blessing)]
        page = []
        for finding, standing in selected[offset:offset + limit]:
            row = finding.as_dict(detail=detail)
            row['blessing'] = standing
            page.append(row)
        return {'total': len(rows), 'matching': len(selected), 'offset': offset,
                'shown': len(page), 'next_offset': offset + limit
                if offset + limit < len(selected) else None,
                'by_class': dict(Counter(entity(f.poi_class).name for f, _ in rows)),
                'by_blessing': dict(Counter(s['status'] for _, s in rows)),
                'by_assessment_finding': dict(Counter(
                    f['kind'] for _, standing in rows
                    for f in standing.get('assessment_findings', []))),
                'store_findings': snapshot['findings'] if snapshot else [],
                'items': page}
