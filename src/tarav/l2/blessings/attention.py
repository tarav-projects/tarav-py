"""Revisable attention over currently detected POIs and attributed blessings."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from tarav.l1.blessings import BlessingRecord, BlessingStore
from tarav.l1.poi import POI, POICollector
from tarav.l1.poi.primitives import canonical
from tarav.l2.scoring import ScoringRepository


@dataclass(frozen=True)
class BlessingAttentionPolicy:
    """Conservative deferral parameters, never a truth score or detection rule."""

    first_delay: timedelta = timedelta(days=1)
    maximum_delay: timedelta = timedelta(days=30)
    supported_multiplier: int = 3
    maximum_independent_reviews: int = 3
    minimum_comparisons: int = 2
    minimum_coverage: float = 0.5
    minimum_relative_support: float = 0.5

    def __post_init__(self):
        if self.first_delay <= timedelta(0) or self.maximum_delay < self.first_delay:
            raise ValueError('Attention delays must be positive and ordered')
        if self.supported_multiplier < 1 or self.maximum_independent_reviews < 1:
            raise ValueError('Attention multipliers must be positive')
        if self.minimum_comparisons < 1:
            raise ValueError('Minimum comparisons must be positive')
        if not 0 <= self.minimum_coverage <= 1 or not 0 <= self.minimum_relative_support <= 1:
            raise ValueError('Attention score thresholds must be fractions')


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Blessing review time must carry a timezone')
    return parsed.astimezone(timezone.utc)


def _support_groups(record: dict) -> set[str]:
    """Unknown dependency is not evidence of independence."""

    groups = []
    for reference in record['support']:
        group = reference.get('independence_group')
        if not isinstance(group, str) or not group:
            return set()
        groups.append(group)
    return set(groups)


def _independent_review_count(records: list[dict]) -> int:
    """Count fresh actors with explicit disjoint source groups."""

    actors: set[str] = set()
    sources: set[str] = set()
    count = 0
    for record in sorted(records, key=lambda item: (_time(item['created_at']), item['id'])):
        actor = canonical(record['actor'])
        support = _support_groups(record)
        if count == 0 or actor not in actors and support and support.isdisjoint(sources):
            count += 1
        actors.add(actor)
        sources.update(support)
    return count


def _compact_vector(vector: dict) -> dict:
    return {
        label: {
            'status': value['status'],
            'assessments': [
                {key: row[key] for key in (
                    'tribunal_type_id', 'value', 'comparisons', 'opponent_count',
                    'coverage', 'abstentions',
                )}
                for row in value['assessments']
            ],
        }
        for label, value in vector.items()
    }


def _has_relative_support(main: dict, policy: BlessingAttentionPolicy) -> bool:
    if main['status'] != 'scored' or not main['assessments']:
        return False
    # Every scored tribunal must have enough comparison coverage. A favorable
    # result from one selected tribunal cannot conceal a weak second result.
    return all(
        row['value'] is not None
        and row['value'] >= policy.minimum_relative_support
        and row['comparisons'] >= policy.minimum_comparisons
        and row['coverage'] >= policy.minimum_coverage
        for row in main['assessments']
    )


def attention_report(
    collector: POICollector,
    store: BlessingStore,
    repository: ScoringRepository,
    *,
    now: datetime | None = None,
    policy: BlessingAttentionPolicy | None = None,
    show_all: bool = False,
    force_review: tuple[str, ...] = (),
    offset: int = 0,
    limit: int = 20,
) -> dict:
    """Select due POIs while keeping every current detection inspectable.

    This is a presentation view of the supplied evaluation. It neither reruns
    checks nor schedules a POI that a current check no longer emits.
    """
    # tarav.breadcrumb 540a3e31c24fcf622ff844d5f672712956186aecee9a15ac4570d2114b4363ba
    # tarav.breadcrumb d6390a89c59d8811e691e0242dd5f32f9859f2e7ddcae09daa0f2cb872e47796

    if not isinstance(collector, POICollector) or not isinstance(store, BlessingStore):
        raise TypeError('Expected a POICollector and BlessingStore')
    if not isinstance(repository, ScoringRepository):
        raise TypeError('Expected a ScoringRepository')
    if not isinstance(show_all, bool):
        raise TypeError('show_all must be a boolean')
    if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 1:
        raise ValueError('Expected nonnegative offset and positive limit')
    current = datetime.now(timezone.utc) if now is None else now
    if current.tzinfo is None:
        raise ValueError('Attention clock must carry a timezone')
    current = current.astimezone(timezone.utc)
    policy = policy or BlessingAttentionPolicy()
    if not isinstance(policy, BlessingAttentionPolicy):
        raise TypeError('Expected a BlessingAttentionPolicy')
    forced = set(force_review)
    if not all(isinstance(value, str) and value for value in forced):
        raise ValueError('Force-review IDs must be nonempty strings')
    snapshot = store.snapshot()
    blessings = [record for record in snapshot['records']
                 if issubclass(store.record_types[record['type']], BlessingRecord)]
    by_poi: dict[str, list[dict]] = {}
    for record in blessings:
        by_poi.setdefault(record['poi']['id'], []).append(record)
    rows = []
    vectors: dict[str, dict] = {}

    def vector_for(record: dict) -> dict:
        if record['id'] not in vectors:
            blessing_type = store.record_types[record['type']]
            vectors[record['id']] = _compact_vector(
                blessing_type.from_record(record).score_vector(repository))
        return vectors[record['id']]

    for poi in collector.pois:
        if not isinstance(poi, POI):
            raise TypeError('Collector contains a non-POI')
        record = poi.as_dict()
        identity = getattr(poi, 'identity', None)
        matching = by_poi.get(identity, []) if store.accepts(poi) else []
        attention = {'state': 'due', 'assessment': 'not-applicable',
                     'review_count': 0, 'independent_reviews': 0,
                     'last_review_at': None, 'next_attention_at': None,
                     'score_vector': {}}
        if matching:
            latest = max(matching, key=lambda item: (_time(item['created_at']), item['id']))
            last = _time(latest['created_at'])
            vector = vector_for(latest)
            main = vector['main']
            independent = _independent_review_count(matching)
            strong = bool(latest['support']) and _has_relative_support(main, policy)
            supported = ([record for record in matching if record['support']
                          and _has_relative_support(vector_for(record)['main'], policy)]
                         if strong else [])
            supported_independent = _independent_review_count(supported)
            multiplier = (policy.supported_multiplier
                          * min(supported_independent, policy.maximum_independent_reviews)
                          if strong else 1)
            delay = min(policy.first_delay * multiplier, policy.maximum_delay)
            next_at = last + delay
            attention = {
                'state': 'due' if current >= next_at else 'deferred',
                'assessment': main['status'],
                'relative_support': strong,
                'review_count': len(matching),
                'independent_reviews': independent,
                'supported_independent_reviews': supported_independent,
                'last_review_at': last.isoformat(),
                'next_attention_at': next_at.isoformat(),
                'score_vector': vector,
            }
        elif store.accepts(poi):
            attention['assessment'] = 'unassessed'
        attention['forced'] = identity in forced
        record['attention'] = attention
        if store.accepts(poi):
            record['blessing'] = store.standing(poi, snapshot=snapshot)
        rows.append(record)
    rows.sort(key=lambda row: (row.get('id', ''), row['type']))
    selected = [row for row in rows if show_all or row['attention']['state'] == 'due'
                or row['attention']['forced']]
    page = selected[offset:offset + limit]
    return {
        'total': len(rows), 'due': sum(row['attention']['state'] == 'due' for row in rows),
        'deferred': sum(row['attention']['state'] == 'deferred' for row in rows),
        'matching': len(selected), 'offset': offset, 'shown': len(page),
        'next_offset': offset + limit if offset + limit < len(selected) else None,
        'store_findings': snapshot['findings'], 'items': page,
    }


__all__ = ['BlessingAttentionPolicy', 'attention_report']
