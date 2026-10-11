"""Attention changes presentation, never POI detection or the Blessing of an action."""

from datetime import datetime, timedelta, timezone

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI
from tarav.l1.poi import POICollector
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l2.blessings import BlessingAttentionPolicy, attention_report
from tarav.l2.blessings.assertions import BlessingAcceptanceCase, BlessingAcceptanceTribunal
from tarav.l2.scoring import (
    ScoringRepository, TribunalRegistry, enroll_case, prepare_pair, submit_judgment,
)
from tarav.l3.runtime import create_runtime

from blessing_bench import Bench


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
    return ExamplePOI(ExampleCheck(), 'Review the ambiguity',
                      situation={'edition': edition}, subject={'line': 1})


def _reference(name):
    return {'type': 'Example.Source', 'locator': {'name': name}}


def _setup(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / 'archive')
    return (Bench(tmp_path / 'records', runtime.records),
            ScoringRepository.initialize(tmp_path / 'scoring'))


def test_a_blessing_defers_briefly_then_returns_without_hiding_detection(tmp_path):
    # tarav.breadcrumb 9ca6e5041dbc2bdf0f5a7b18246b8704f0ea794560a673e5fffaa4dddd986e91
    bench, scoring = _setup(tmp_path)
    poi = _poi()
    collector = POICollector()
    collector.emit(poi)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    blessing = bench.bless(poi, at=t0)
    later = attention_report(collector, bench.pois, scoring, now=t0 + timedelta(hours=12))
    assert later['total'] == 1 and later['deferred'] == 1 and later['items'] == []
    assert collector.report(actions=bench.pois)['items'][0]['id'] == poi.identity
    full = attention_report(collector, bench.pois, scoring, now=t0, show_all=True)
    assert full['items'][0]['attention']['assessment'] == 'unassessed'
    assert full['items'][0]['attention']['blessed_at'] == t0.isoformat()
    assert full['items'][0]['attention']['next_attention_at'] == (t0 + timedelta(days=1)).isoformat()
    assert full['items'][0]['blessing'] == {'status': 'blessed', 'blessing': str(blessing.id)}
    due = attention_report(collector, bench.pois, scoring, now=t0 + timedelta(days=1))
    assert due['due'] == 1 and due['items'][0]['id'] == poi.identity
    forced = attention_report(collector, bench.pois, scoring, now=t0,
                              force_review=(poi.identity,))
    assert forced['items'][0]['attention']['forced'] is True
    assert forced['items'][0]['attention']['state'] == 'deferred'


def test_support_alone_does_not_extend_the_deferral(tmp_path):
    # tarav.breadcrumb eb3b923b65c2dfa4c1806e1fc19883cf3899898537bf45160a5500dfb5776022
    bench, scoring = _setup(tmp_path)
    poi = _poi()
    collector = POICollector()
    collector.emit(poi)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    bench.bless(poi, at=t0, support=[_reference('reader')])
    row = attention_report(collector, bench.pois, scoring, now=t0,
                           show_all=True)['items'][0]['attention']
    assert row['assessment'] == 'unassessed' and row['relative_support'] is False
    assert row['next_attention_at'] == (t0 + timedelta(days=1)).isoformat()


def test_relative_score_extends_only_with_support_and_sampling(tmp_path):
    # tarav.breadcrumb 0b1c9ab6ce611e888d7c24fec762b76b38df7c4224c00b0ff08483b8a909535a
    bench, scoring = _setup(tmp_path)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    poi = _poi()
    first = bench.bless(poi, at=t0, support=[_reference('publisher')])
    others = [bench.bless(_poi(edition), at=t0, support=[_reference(str(edition))])
              for edition in (2, 3, 4)]
    registry = TribunalRegistry((BlessingAcceptanceTribunal(),))
    cases = []
    for blessing in (first, *others):
        source = blessing.records.to_record()['support'][0]
        case = blessing.assertions['main'].assessment_case(
            BlessingAcceptanceCase, blessing=blessing,
            source_passages=({'reference': source, 'text': 'Passage from source.'},),
        )
        cases.append(enroll_case(scoring, case, registry=registry))
    collector = POICollector()
    collector.emit(poi)
    before = attention_report(collector, bench.pois, scoring, now=t0, show_all=True)['items'][0]
    assert before['attention']['assessment'] == 'unscored'
    for other in cases[1:]:
        pair, _ = prepare_pair(scoring, cases[0], other, registry=registry)
        submit_judgment(scoring, pair, outcome='A', judge={'type': 'Example.Judge'},
                        rationale='The first case is better supported.')
    after = attention_report(collector, bench.pois, scoring, now=t0, show_all=True)['items'][0]
    assert after['attention']['assessment'] == 'scored'
    assert after['attention']['relative_support'] is True
    assert after['attention']['score_vector']['main']['assessments'][0]['comparisons'] == 3
    assert after['attention']['next_attention_at'] == (t0 + timedelta(days=3)).isoformat()
    capped = attention_report(collector, bench.pois, scoring, now=t0, show_all=True,
                              policy=BlessingAttentionPolicy(maximum_delay=timedelta(days=2)))
    assert capped['items'][0]['attention']['next_attention_at'] == (t0 + timedelta(days=2)).isoformat()
    weaker = POICollector()
    weaker.emit(_poi(2))
    weak_row = attention_report(weaker, bench.pois, scoring, now=t0,
                                show_all=True)['items'][0]['attention']
    assert weak_row['assessment'] == 'scored' and weak_row['relative_support'] is False
    assert weak_row['next_attention_at'] == (t0 + timedelta(days=1)).isoformat()


def test_changed_situation_and_absent_poi_have_no_inherited_schedule(tmp_path):
    bench, scoring = _setup(tmp_path)
    t0 = datetime(2026, 10, 3, tzinfo=timezone.utc)
    bench.bless(_poi(1), at=t0)
    collector = POICollector()
    collector.emit(_poi(2))
    report = attention_report(collector, bench.pois, scoring, now=t0)
    assert report['items'][0]['attention']['blessed_at'] is None
    assert report['items'][0]['attention']['state'] == 'due'
    assert report['items'][0]['blessing']['status'] == 'unblessed'
    assert attention_report(POICollector(), bench.pois, scoring, now=t0)['total'] == 0


def test_show_all_remains_bounded_and_pageable(tmp_path):
    bench, scoring = _setup(tmp_path)
    collector = POICollector()
    for edition in range(25):
        collector.emit(_poi(edition))
    first = attention_report(collector, bench.pois, scoring, show_all=True)
    second = attention_report(collector, bench.pois, scoring, show_all=True, offset=20)
    assert first['total'] == first['matching'] == 25
    assert first['shown'] == 20 and first['next_offset'] == 20
    assert second['shown'] == 5 and second['next_offset'] is None
    assert {row['id'] for row in first['items']}.isdisjoint(
        row['id'] for row in second['items'])


def test_rejects_invalid_clocks_and_policy(tmp_path):
    bench, scoring = _setup(tmp_path)
    with pytest.raises(ValueError, match='timezone'):
        attention_report(POICollector(), bench.pois, scoring, now=datetime(2026, 10, 3))
    with pytest.raises(ValueError, match='positive'):
        BlessingAttentionPolicy(first_delay=timedelta(0))
