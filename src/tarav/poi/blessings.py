"""Append-only attributed acceptances and assessments at a caller-owned path."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from tarav.harness import FileRecord, TypeShip
from .primitives import canonical, fingerprint


class BlessingRecord(FileRecord):
    type_name = 'Tarav.POI.Blessing'
    type_ship = TypeShip('1c218c7c-4a6b-43dc-9e22-817330824b85')


class BlessingAssessmentRecord(FileRecord):
    type_name = 'Tarav.POI.BlessingAssessment'
    type_ship = TypeShip('341a797a-82c7-4fb3-b97b-c60c6f19139b')


def reference(value):
    if (not isinstance(value, dict) or not value.get('type')
            or not isinstance(value.get('locator'), dict) or not value['locator']):
        raise ValueError('Expected an explicit typed actor/evidence reference')
    canonical(value)


def validate(record):
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
    if record['type'] == BlessingRecord.type_name:
        finding = record['finding']
        if not isinstance(finding, dict) or not finding.get('blessable'):
            raise ValueError('Blessing must retain a blessable finding')
        if finding['id'] != fingerprint([finding['class_id'], finding['subject']]):
            raise ValueError('Finding identity disagrees with retained subject')
        if finding['state'] != fingerprint([finding['id'], finding['check_version'], finding['evidence']]):
            raise ValueError('Finding state disagrees with retained evidence')
    elif record['type'] == BlessingAssessmentRecord.type_name:
        UUID(record['blessing'])
        if (type(record['score']) not in (int, float) or not math.isfinite(record['score'])
                or not 0 <= record['score'] <= 1):
            raise ValueError('score must be a finite value between zero and one')
        if not isinstance(record['assertion'], str) or not record['assertion'].strip():
            raise ValueError('Assessment must name its assertion')
    else:
        raise ValueError('Unknown blessing record type')


class BlessingStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def snapshot(self):
        records, findings = [], []
        for path in sorted(self.root.glob('*.json')):
            try:
                record = json.loads(path.read_text())
                validate(record)
                if path.stem != record['id']:
                    raise ValueError('Record ID and filename disagree')
                records.append(record)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                findings.append({'kind': 'invalid-blessing-record', 'path': str(path),
                                 'detail': str(exc)})
        ids = {r['id'] for r in records if r['type'] == BlessingRecord.type_name}
        for record in records:
            if record['type'] == BlessingAssessmentRecord.type_name and record['blessing'] not in ids:
                findings.append({'kind': 'orphan-blessing-assessment', 'id': record['id']})
        return {'records': records, 'findings': findings}

    def _append(self, record):
        validate(record)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (record['id'] + '.json')
        with path.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        return record

    def bless(self, finding, *, actor, rationale, support=()):
        if not finding.poi_class.blessable:
            raise ValueError('This POI class does not permit blessing')
        record = {'type': BlessingRecord.type_name, 'schema_version': 1,
                  'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                  'actor': actor, 'rationale': rationale, 'support': list(support),
                  'finding': finding.as_dict(detail=True)}
        return self._append(record)

    def assess(self, blessing, *, actor, assertion, score, rationale, support=()):
        records = self.snapshot()['records']
        if not any(r['type'] == BlessingRecord.type_name and r['id'] == blessing for r in records):
            raise ValueError('Unknown blessing')
        return self._append({'type': BlessingAssessmentRecord.type_name, 'schema_version': 1,
                             'id': str(uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(),
                             'blessing': blessing, 'actor': actor, 'assertion': assertion,
                             'score': score, 'rationale': rationale, 'support': list(support)})

    def standing(self, finding, *, snapshot=None):
        records = (snapshot if snapshot is not None else self.snapshot())['records']
        accepted = [r for r in records if r['type'] == BlessingRecord.type_name
                    and r['finding']['id'] == finding.identity]
        current = [r for r in accepted if r['finding']['state'] == finding.state]
        status = ('disallowed' if accepted and not finding.poi_class.blessable else
                  'blessed' if current else 'stale' if accepted else 'unblessed')
        scores = [r for r in records if r['type'] == BlessingAssessmentRecord.type_name
                  and r['blessing'] in {b['id'] for b in current}]
        assessment_findings = []
        for record in current:
            assessments = [r for r in scores if r['blessing'] == record['id']
                           and r['assertion'] == 'acceptance-justified']
            if not assessments:
                assessment_findings.append({'kind': 'blessing-unassessed', 'blessing': record['id']})
            for assessment in assessments:
                if assessment['score'] < 0.5:
                    assessment_findings.append({'kind': 'blessing-low-score',
                                                'assessment': assessment['id'],
                                                'blessing': record['id']})
        return {'status': status, 'records': [r['id'] for r in accepted],
                'current': [r['id'] for r in current],
                'assessment_findings': assessment_findings,
                'assessment': 'unassessed' if any(f['kind'] == 'blessing-unassessed'
                                                 for f in assessment_findings) else
                'scored' if scores else 'not-applicable',
                'scores': [{'id': r['id'], 'blessing': r['blessing'], 'assertion': r['assertion'],
                            'score': r['score']} for r in scores]}
