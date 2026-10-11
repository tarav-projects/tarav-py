"""Revisable attention over currently detected POIs and the Blessings of their actions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from tarav.l1.actions.pois import POIActions
from tarav.l1.poi import POI, POICollector
from tarav.l1.poi.actionable import BlessablePOI
from tarav.l2.scoring import ScoringRepository


@dataclass(frozen=True)
class BlessingAttentionPolicy:
    """Conservative deferral parameters, never a truth score or detection rule."""

    first_delay: timedelta = timedelta(days=1)
    maximum_delay: timedelta = timedelta(days=30)
    supported_multiplier: int = 3
    minimum_comparisons: int = 2
    minimum_coverage: float = 0.5
    minimum_relative_support: float = 0.5

    def __post_init__(self):
        if self.first_delay <= timedelta(0) or self.maximum_delay < self.first_delay:
            raise ValueError('Attention delays must be positive and ordered')
        if self.supported_multiplier < 1:
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
    actions: POIActions,
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
    checks nor schedules a POI that a current check no longer emits. A POI
    whose action is blessed is deferred from the time of its Blessing, longer
    when the Blessing offers support and its acceptance is well scored.
    """
    # tarav.breadcrumb 540a3e31c24fcf622ff844d5f672712956186aecee9a15ac4570d2114b4363ba
    # tarav.breadcrumb d6390a89c59d8811e691e0242dd5f32f9859f2e7ddcae09daa0f2cb872e47796

    if not isinstance(collector, POICollector) or not isinstance(actions, POIActions):
        raise TypeError('Expected a POICollector and POIActions')
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
    rows = []
    for poi in collector.pois:
        if not isinstance(poi, POI):
            raise TypeError('Collector contains a non-POI')
        record = poi.as_dict()
        identity = getattr(poi, 'identity', None)
        blessable = isinstance(poi, BlessablePOI)
        blessing = actions.blessing(poi) if blessable else None
        attention = {'state': 'due',
                     'assessment': 'unassessed' if blessable else 'not-applicable',
                     'blessed_at': None, 'next_attention_at': None, 'score_vector': {}}
        if blessing is not None:
            blessed_at = _time(blessing.data['at'])
            vector = _compact_vector(blessing.score_vector(repository))
            main = vector['main']
            strong = bool(blessing.data['support']) and _has_relative_support(main, policy)
            delay = min(policy.first_delay * (policy.supported_multiplier if strong else 1),
                        policy.maximum_delay)
            next_at = blessed_at + delay
            attention = {
                'state': 'due' if current >= next_at else 'deferred',
                'assessment': main['status'],
                'relative_support': strong,
                'blessed_at': blessed_at.isoformat(),
                'next_attention_at': next_at.isoformat(),
                'score_vector': vector,
            }
        attention['forced'] = identity in forced
        record['attention'] = attention
        if blessable:
            record['blessing'] = actions.blessing_standing(poi)
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
        'items': page,
    }


__all__ = ['BlessingAttentionPolicy', 'attention_report']
