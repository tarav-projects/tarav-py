from copy import deepcopy

import pytest

from tarav.l0.kernel import TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.poi import (
    BlessingRecord, BlessingStore, POICheck, POIError, POIFinding, POIInstance,
    POIWorkflow,
)
from tarav.l3.runtime import create_runtime


class ExampleCheck(POICheck):
    blessable = True

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('082c8223-a19a-4817-8235-7f405002f446'),
                          name='Example.POICheck')


class ReviewedBlessing(BlessingRecord):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('28b0ec48-2fe9-49f4-bb0e-d944aece9bdd'),
                          name='Example.ReviewedBlessing')

    def assessment_findings(self, assessments):
        return [] if any(a['assertion'] == 'reviewed' for a in assessments) else [
            {'kind': 'review-required', 'blessing': str(self.id)}]


def test_finding_identity_context_and_roundtrip(tmp_path):
    runtime = create_runtime(archive_root=tmp_path, record_types=(ExampleCheck,))
    finding = ExampleCheck.finding({'path': 'sample.md', 'line': 12}, evidence={'text': 'x'})
    assert isinstance(finding, (POIInstance, TaravEntity))
    assert entity(type(finding)).workflow is POIWorkflow()
    assert runtime.context(finding).open('check').target is ExampleCheck
    encoded = finding.to_record()
    loaded = runtime.records.from_record(encoded)
    assert type(loaded) is POIFinding
    assert loaded.to_record() == encoded
    assert loaded.id == finding.id
    assert entity(ExampleCheck).id in loaded.ships()
    assert loaded.resolve_check(runtime.records).target is ExampleCheck
    for subject in (finding, loaded):
        context = runtime.context(subject)
        assert context.open('check').id == entity(ExampleCheck).id
        assert context.open('coordinate').to_record()['value'] == finding.coordinate
        assert context.open('evidence').to_record()['value'] == {'text': 'x'}
    changed = ExampleCheck.finding(finding.coordinate, evidence={'text': 'y'})
    assert changed.id == finding.id and changed.state != finding.state
    moved = ExampleCheck.finding({'path': 'other.md'})
    assert moved.id != finding.id


@pytest.mark.parametrize('field,value', [('identity', 'bad'), ('state', 'bad'),
                                         ('id', 'fda72f60-18ec-48b0-a56b-60baaceee904')])
def test_invalid_retained_identity_is_rejected(field, value):
    record = deepcopy(ExampleCheck.finding({}).to_record())
    record[field] = value
    with pytest.raises(ValueError):
        POIFinding.from_record(record)


def test_runtime_collector_and_explicit_exception(tmp_path):
    first, second = (create_runtime(archive_root=tmp_path) for _ in range(2))
    finding = first.pois.emit(ExampleCheck.finding({'path': 'a'}))
    assert second.pois.findings == []
    assert first.pois.get(str(finding.id)) is finding
    assert first.pois.report()['total'] == 1
    with pytest.raises(POIError) as raised:
        finding.error()
    assert raised.value.poi is finding
    assert not tmp_path.joinpath(str(POIWorkflow().id)).exists()
    assert first.blessings.root == tmp_path / str(POIWorkflow().id) / 'blessings'


def test_typed_blessing_policy_and_context(tmp_path):
    runtime = create_runtime(archive_root=tmp_path, record_types=(ReviewedBlessing,))
    store = BlessingStore(tmp_path, record_types=(ReviewedBlessing,))
    actor = {'type': 'Example.Actor', 'locator': {'session': 'fixture'}}
    finding = ExampleCheck.finding({'path': 'a'})
    record = store.bless(finding, actor=actor, rationale='Fixture review',
                         record_type=ReviewedBlessing)
    loaded = store.load(record['id'])
    assert isinstance(loaded, TaravEntity)
    assert loaded.to_record() == record
    assert finding.id in loaded.ships()
    assert runtime.records.from_record(record).id == loaded.id
    assert runtime.context(loaded).open('acceptance').to_record()['value'] == record
    assert store.standing(finding)['assessment_findings'][0]['kind'] == 'review-required'
    assessment = store.assess(record['id'], actor=actor, assertion='reviewed',
                              score=1, rationale='Fixture assessment')
    assert store.load(assessment['id']).to_record() == assessment
    assert loaded.id in store.load(assessment['id']).ships()
    assert store.standing(finding)['assessment_findings'] == []
    assert BlessingStore(tmp_path).snapshot()['findings']  # No imports from stored Types.
    assert finding.to_record()['state'] == finding.state  # Blessing never changes detection.
    assert runtime.blessings.record_types['Example.ReviewedBlessing'] is ReviewedBlessing


def test_typed_append_preserves_extra_fields_and_refuses_overwrite(tmp_path):
    store = BlessingStore(tmp_path, record_types=(ReviewedBlessing,))
    record = ReviewedBlessing.record_example()
    record['review_ticket'] = 'example-ticket'
    blessing = ReviewedBlessing.from_record(record)
    assert store.add(blessing) is blessing
    assert store.load(blessing.id).to_record()['review_ticket'] == 'example-ticket'
    with pytest.raises(FileExistsError):
        store.add(blessing)
