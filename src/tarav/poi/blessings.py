"""Append-only attributed acceptances and assessments at a caller-owned path."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from tarav.kernel import TaravClass, entity
from tarav.kernel import Ship, TaravEntity, FileRecord, TypeShip
from .primitives import POIInstance, canonical, fingerprint
from .workflow import POI_WORKFLOW_SHIP


class BlessingRecord(TaravEntity, FileRecord):
    class RecordInterface(TaravEntity.RecordInterface):
        schema_version: int
        created_at: str
        actor: dict
        rationale: str
        support: list[dict]
        finding: dict

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('1c218c7c-4a6b-43dc-9e22-817330824b85'),
            name='Tarav.POI.Blessing',
            workflow=POI_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        _validate(value, blessing=True)
        return data

    @classmethod
    def _from_record(cls, data):
        result = cls.__new__(cls)
        TaravEntity.__init__(result, data.id)
        return result

    def assessment_findings(self, assessments):
        """Override in a blessing subtype to define its assessment obligations."""
        selected = [a for a in assessments if a['assertion'] == 'acceptance-justified']
        if not selected:
            return [{'kind': 'blessing-unassessed', 'blessing': str(self.id)}]
        return [{'kind': 'blessing-low-score', 'assessment': a['id'],
                 'blessing': str(self.id)} for a in selected if a['score'] < 0.5]

    def ships(self):
        finding = self.to_record()['finding']
        return (*super().ships(), POIInstance.ship_for(finding['id']),
                TypeShip(finding['class_id']))

    def obj_context(self, builder):
        from .primitives import POIDetails
        builder.add('acceptance', opener=lambda: POIDetails.from_record(
            {'type': entity(POIDetails).name, 'value': self.to_record()}))

    @classmethod
    def record_example(cls):
        from .primitives import POICheck
        finding = POICheck.finding({'example': 'coordinate'}).as_dict(detail=True)
        finding['blessable'] = True
        return {'type': entity(cls).name, 'schema_version': 1,
                'id': 'b3c3a696-e88c-497f-b87d-cdc9a557d882',
                'created_at': '2026-09-26T00:00:00+00:00',
                'actor': {'type': 'Example.Actor', 'locator': {'name': 'example'}},
                'rationale': 'Synthetic Record example', 'support': [], 'finding': finding}


class BlessingAssessmentRecord(TaravEntity, FileRecord):
    class RecordInterface(TaravEntity.RecordInterface):
        schema_version: int
        created_at: str
        actor: dict
        rationale: str
        support: list[dict]
        blessing: str
        assertion: str
        score: float | int

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('341a797a-82c7-4fb3-b97b-c60c6f19139b'),
            name='Tarav.POI.BlessingAssessment',
            workflow=POI_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        _validate(value, blessing=False)
        return data

    @classmethod
    def _from_record(cls, data):
        result = cls.__new__(cls)
        TaravEntity.__init__(result, data.id)
        return result

    def obj_context(self, builder):
        from .primitives import POIDetails
        builder.add('assessment', opener=lambda: POIDetails.from_record(
            {'type': entity(POIDetails).name, 'value': self.to_record()}))

    def ships(self):
        return (*super().ships(), Ship(self.to_record()['blessing']))

    @classmethod
    def record_example(cls):
        record = BlessingRecord.record_example()
        record.pop('finding')
        record.update(type=entity(cls).name,
                      blessing='b3c3a696-e88c-497f-b87d-cdc9a557d882',
                      assertion='acceptance-justified', score=1.0)
        return record


def reference(value):
    if (not isinstance(value, dict) or not value.get('type')
            or not isinstance(value.get('locator'), dict) or not value['locator']):
        raise ValueError('Expected an explicit typed actor/evidence reference')
    canonical(value)


def _validate(record, *, blessing):
    if not isinstance(record, dict):
        raise ValueError('Expected a blessing Record object')
    if record.get('schema_version') != 1:
        raise ValueError('Unsupported blessing record schema')
    UUID(record['id'])
    datetime.fromisoformat(record['created_at'])
    reference(record['actor'])
    if not isinstance(record['rationale'], str) or not record['rationale'].strip():
        raise ValueError('An attributed rationale is required')
    if not isinstance(record['support'], list):
        raise ValueError('support must be a list of typed references')
    for item in record['support']:
        reference(item)
    if blessing:
        finding = record['finding']
        if not isinstance(finding, dict) or not finding.get('blessable'):
            raise ValueError('Blessing must retain a blessable finding')
        if finding['id'] != fingerprint([finding['class_id'], finding['subject']]):
            raise ValueError('Finding identity disagrees with retained subject')
        if finding['state'] != fingerprint([finding['id'], finding['check_version'], finding['evidence']]):
            raise ValueError('Finding state disagrees with retained evidence')
        TypeShip(finding['class_id'])
        if ('entity_id' in finding
                and finding['entity_id'] != str(POIInstance.ship_for(finding['id']))):
            raise ValueError('Finding Ship disagrees with retained identity')
    else:
        UUID(record['blessing'])
        if (type(record['score']) not in (int, float) or not math.isfinite(record['score'])
                or not 0 <= record['score'] <= 1):
            raise ValueError('score must be a finite value between zero and one')
        if not isinstance(record['assertion'], str) or not record['assertion'].strip():
            raise ValueError('Assessment must name its assertion')


class BlessingStore:
    def __init__(self, root, *, record_types=()):
        self.root = Path(root).resolve()
        self.record_types = {}
        for cls in (BlessingRecord, BlessingAssessmentRecord, *record_types):
            if not issubclass(cls, (BlessingRecord, BlessingAssessmentRecord)):
                raise TypeError('Expected a blessing or assessment type')
            name = entity(cls).name
            if name in self.record_types and self.record_types[name] is not cls:
                raise ValueError(f'Duplicate blessing type: {name}')
            self.record_types[name] = cls

    @classmethod
    def from_archive(cls, archive, **kwargs):
        """Address the shared POI partition; no directories are created on read."""
        from .workflow import POIWorkflow
        return cls(archive.for_workflow(POIWorkflow).directory / 'blessings', **kwargs)

    def _type(self, record):
        if not isinstance(record, dict) or record.get('type') not in self.record_types:
            raise ValueError('Unknown blessing record type')
        return self.record_types[record['type']]

    def _is(self, record, base):
        return issubclass(self._type(record), base)

    def load(self, identity):
        for record in self.snapshot()['records']:
            if record['id'] == str(identity):
                return self._type(record).from_record(record)
        raise KeyError(identity)

    def add(self, blessing):
        """Append a typed object, including subtype-specific retained fields."""
        if not isinstance(blessing, (BlessingRecord, BlessingAssessmentRecord)):
            raise TypeError('Expected a blessing or assessment object')
        record = blessing.to_record()
        if self._type(record) is not type(blessing):
            raise TypeError('Object does not match registered blessing type')
        self._append(record)
        return blessing

    def snapshot(self):
        records, findings = [], []
        for path in sorted(self.root.glob('*.json')):
            try:
                record = json.loads(path.read_text())
                self._type(record).validate_record(record)
                if path.stem != record['id']:
                    raise ValueError('Record ID and filename disagree')
                records.append(record)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                findings.append({'kind': 'invalid-blessing-record', 'path': str(path),
                                 'detail': str(exc)})
        ids = {r['id'] for r in records if self._is(r, BlessingRecord)}
        for record in records:
            if self._is(record, BlessingAssessmentRecord) and record['blessing'] not in ids:
                findings.append({'kind': 'orphan-blessing-assessment', 'id': record['id']})
        return {'records': records, 'findings': findings}

    def _append(self, record):
        self._type(record).validate_record(record)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (record['id'] + '.json')
        with path.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        return record

    def bless(self, finding, *, actor, rationale, support=(), record_type=BlessingRecord):
        if not issubclass(record_type, BlessingRecord):
            raise TypeError('Expected BlessingRecord subtype')
        if not finding.blessable:
            raise ValueError('This POI class does not permit blessing')
        record = {'type': entity(record_type).name, 'schema_version': 1,
                  'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                  'actor': actor, 'rationale': rationale, 'support': list(support),
                  'finding': finding.as_dict(detail=True)}
        return self._append(record)

    def assess(self, blessing, *, actor, assertion, score, rationale, support=(),
               record_type=BlessingAssessmentRecord):
        if not issubclass(record_type, BlessingAssessmentRecord):
            raise TypeError('Expected BlessingAssessmentRecord subtype')
        records = self.snapshot()['records']
        if not any(self._is(r, BlessingRecord) and r['id'] == blessing for r in records):
            raise ValueError('Unknown blessing')
        return self._append({'type': entity(record_type).name, 'schema_version': 1,
                             'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                             'blessing': blessing, 'actor': actor, 'assertion': assertion,
                             'score': score, 'rationale': rationale, 'support': list(support)})

    def standing(self, finding, *, snapshot=None):
        records = (snapshot if snapshot is not None else self.snapshot())['records']
        accepted = [r for r in records if self._is(r, BlessingRecord)
                    and r['finding']['id'] == finding.identity]
        current = [r for r in accepted if r['finding']['state'] == finding.state]
        status = ('disallowed' if accepted and not finding.blessable else
                  'blessed' if current else 'stale' if accepted else 'unblessed')
        scores = [r for r in records if self._is(r, BlessingAssessmentRecord)
                  and r['blessing'] in {b['id'] for b in current}]
        assessment_findings = []
        for record in current:
            assessments = [r for r in scores if r['blessing'] == record['id']]
            obj = self._type(record).from_record(record)
            assessment_findings.extend(obj.assessment_findings(assessments))
        return {'status': status, 'records': [r['id'] for r in accepted],
                'current': [r['id'] for r in current],
                'assessment_findings': assessment_findings,
                'assessment': 'unassessed' if any(f['kind'] == 'blessing-unassessed'
                                                 for f in assessment_findings) else
                'scored' if scores else 'not-applicable',
                'scores': [{'id': r['id'], 'blessing': r['blessing'], 'assertion': r['assertion'],
                            'score': r['score']} for r in scores]}
