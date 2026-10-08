"""Attention changes presentation, never POI detection or retained blessings."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.blessings import BlessablePOI, BlessingRecord, BlessingStore
from tarav.l1.checks import Check, CheckPOI
from tarav.l1.poi import POICollector
from tarav.l2.blessings import BlessingAttentionPolicy, attention_report
from tarav.l2.blessings.assertions import BlessingAcceptanceCase, BlessingAcceptanceTribunal
from tarav.l2.scoring import (
    ScoringRepository, TribunalRegistry, enroll_case, prepare_pair, submit_judgment,
)
from tarav.l3.runtime import create_runtime


class ExampleCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('17894858-c452-4d53-970f-c5ef7064051f'),
                          name='Example.Attention.Check')


class ExamplePOI(CheckPOI, BlessablePOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('b6a71551-c661-407c-b987-d29583a1fd29'),
                          name='Example.Attention.POI')


def _poi(edition=1):
    return ExamplePOI(ExampleCheck(), 'review', 'Review the ambiguity',
                      situation={'edition': edition}, subject={'line': 1})


def _reference(name):
    return {'type': 'Example.Source', 'locator': {'name': name},
            'independence_group': name}


def _add(store, poi, when, *, actor='agent', source=None):
    record = deepcopy(BlessingRecord.records.record_example())
    record.update(id=str(uuid4()), created_at=when.isoformat(),
                  actor={'type': 'Example.Actor', 'locator': {'name': actor}},
                  support=[] if source is None else [_reference(source)],
                  poi=poi.blessing_snapshot())
    return store.add(BlessingRecord.records.from_record(record))


def _setup(tmp_path):
    create_runtime(archive_root=tmp_path / 'archive')
    return BlessingStore(tmp_path / 'blessings'), ScoringRepository.initialize(tmp_path / 'scoring')


def test_first_blessing_defers_briefly_then_returns_without_hiding_detection(tmp_path):
    # tarav.breadcrumb 9ca6e5041dbc2bdf0f5a7b18246b8704f0ea794560a673e5fffaa4dddd986e91
    store, scoring = _setup(tmp_path)
    poi = _poi()
    collector = POICollector()
    collector.emit(poi)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    _add(store, poi, t0)
    later = attention_report(collector, store, scoring, now=t0 + timedelta(hours=12))
    assert later['total'] == 1 and later['deferred'] == 1 and later['items'] == []
    assert collector.report(store=store)['items'][0]['id'] == poi.identity
    full = attention_report(collector, store, scoring, now=t0, show_all=True)
    assert full['items'][0]['attention']['assessment'] == 'unassessed'
    assert full['items'][0]['attention']['review_count'] == 1
    assert full['items'][0]['attention']['next_attention_at'] == (t0 + timedelta(days=1)).isoformat()
    due = attention_report(collector, store, scoring, now=t0 + timedelta(days=1))
    assert due['due'] == 1 and due['items'][0]['id'] == poi.identity
    forced = attention_report(collector, store, scoring, now=t0,
                              force_review=(poi.identity,))
    assert forced['items'][0]['attention']['forced'] is True
    assert forced['items'][0]['attention']['state'] == 'deferred'


def test_unscored_reviews_do_not_extend_even_if_independent(tmp_path):
    # tarav.breadcrumb eb3b923b65c2dfa4c1806e1fc19883cf3899898537bf45160a5500dfb5776022
    store, scoring = _setup(tmp_path)
    poi = _poi()
    collector = POICollector()
    collector.emit(poi)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    for offset, actor, source in ((0, 'a', 'reader-a'), (1, 'b', 'reader-b'),
                                  (2, 'c', 'reader-c'), (3, 'd', 'reader-d')):
        _add(store, poi, t0 + timedelta(hours=offset), actor=actor, source=source)
    policy = BlessingAttentionPolicy(maximum_delay=timedelta(days=2))
    row = attention_report(collector, store, scoring, now=t0 + timedelta(hours=4), policy=policy,
                           show_all=True)['items'][0]['attention']
    assert row['review_count'] == 4 and row['independent_reviews'] == 4
    assert row['next_attention_at'] == (t0 + timedelta(hours=3, days=1)).isoformat()


def test_correlated_reviews_do_not_extend_deferral(tmp_path):
    store, scoring = _setup(tmp_path)
    poi = _poi()
    collector = POICollector()
    collector.emit(poi)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    _add(store, poi, t0, actor='a', source='same-reader')
    _add(store, poi, t0 + timedelta(hours=1), actor='b', source='same-reader')
    _add(store, poi, t0 + timedelta(hours=2), actor='b', source='other-reader')
    row = attention_report(collector, store, scoring, now=t0 + timedelta(hours=3),
                           show_all=True)['items'][0]['attention']
    assert row['review_count'] == 3 and row['independent_reviews'] == 1
    assert row['next_attention_at'] == (t0 + timedelta(hours=2, days=1)).isoformat()


def test_relative_score_extends_only_with_support_and_sampling(tmp_path):
    # tarav.breadcrumb 0b1c9ab6ce611e888d7c24fec762b76b38df7c4224c00b0ff08483b8a909535a
    store, scoring = _setup(tmp_path)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    poi = _poi()
    prior = _add(store, poi, t0 - timedelta(hours=1),
                 actor='prior', source='independent-reader')
    first = _add(store, poi, t0, actor='a', source='publisher')
    others = [_add(store, _poi(edition), t0, actor=str(edition), source=str(edition))
              for edition in (2, 3)]
    registry = TribunalRegistry((BlessingAcceptanceTribunal(),))
    cases = []
    for blessing in (first, prior, *others):
        source = blessing.records.to_record()['support'][0]
        case = blessing.assertions['main'].assessment_case(
            BlessingAcceptanceCase, blessing=blessing,
            source_passages=({'reference': source, 'text': 'Passage from source.'},),
        )
        cases.append(enroll_case(scoring, case, registry=registry))
    collector = POICollector()
    collector.emit(poi)
    before = attention_report(collector, store, scoring, now=t0, show_all=True)['items'][0]
    assert before['attention']['assessment'] == 'unscored'
    for other in cases[1:]:
        pair, _ = prepare_pair(scoring, cases[0], other, registry=registry)
        submit_judgment(scoring, pair, outcome='A', judge={'type': 'Example.Judge'},
                        rationale='The first case is better supported.')
    for other in cases[2:]:
        pair, _ = prepare_pair(scoring, cases[1], other, registry=registry)
        submit_judgment(scoring, pair, outcome='A', judge={'type': 'Example.Judge'},
                        rationale='The prior case is better supported.')
    after = attention_report(collector, store, scoring, now=t0, show_all=True,
                             policy=BlessingAttentionPolicy(maximum_delay=timedelta(days=4)))['items'][0]
    assert after['attention']['assessment'] == 'scored'
    assert after['attention']['relative_support'] is True
    assert after['attention']['score_vector']['main']['assessments'][0]['comparisons'] == 3
    assert after['attention']['independent_reviews'] == 2
    assert after['attention']['supported_independent_reviews'] == 2
    assert after['attention']['next_attention_at'] == (t0 + timedelta(days=4)).isoformat()
    weaker = POICollector()
    weaker.emit(_poi(2))
    weak_row = attention_report(weaker, store, scoring, now=t0,
                                show_all=True)['items'][0]['attention']
    assert weak_row['assessment'] == 'scored' and weak_row['relative_support'] is False
    assert weak_row['next_attention_at'] == (t0 + timedelta(days=1)).isoformat()


def test_changed_situation_and_absent_poi_have_no_inherited_schedule(tmp_path):
    store, scoring = _setup(tmp_path)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    _add(store, _poi(1), t0)
    collector = POICollector()
    collector.emit(_poi(2))
    report = attention_report(collector, store, scoring, now=t0)
    assert report['items'][0]['attention']['review_count'] == 0
    assert report['items'][0]['attention']['state'] == 'due'
    assert report['items'][0]['blessing']['status'] == 'unblessed'
    assert attention_report(POICollector(), store, scoring, now=t0)['total'] == 0


def test_show_all_remains_bounded_and_pageable(tmp_path):
    store, scoring = _setup(tmp_path)
    collector = POICollector()
    for edition in range(25):
        collector.emit(_poi(edition))
    first = attention_report(collector, store, scoring, show_all=True)
    second = attention_report(collector, store, scoring, show_all=True, offset=20)
    assert first['total'] == first['matching'] == 25
    assert first['shown'] == 20 and first['next_offset'] == 20
    assert second['shown'] == 5 and second['next_offset'] is None
    assert {row['id'] for row in first['items']}.isdisjoint(
        row['id'] for row in second['items'])


def test_rejects_invalid_clocks_and_policy(tmp_path):
    store, scoring = _setup(tmp_path)
    with pytest.raises(ValueError, match='timezone'):
        attention_report(POICollector(), store, scoring, now=datetime(2026, 10, 3))
    with pytest.raises(ValueError, match='positive'):
        BlessingAttentionPolicy(first_delay=timedelta(0))
