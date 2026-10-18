"""Typed, recomputable result of pairwise ranking."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from copy import deepcopy

from pydantic import ConfigDict

from tarav.l0.kernel import TaravClass, TypeShip, entity

from ..score import Score
from .workflow import RANKING_WORKFLOW_SHIP


class RankingScore(Score, Mapping[str, object]):
    """One Assertion's relative result within one Tribunal population."""
    # tarav.context 6734aba0:33c08d1be038423c

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('7dc65ad8-4dfe-4650-a0a0-6698d1220680'),
            name='Tarav.Scoring.Ranking.Score',
            workflow=RANKING_WORKFLOW_SHIP,
        )

    class RecordInterface(Score.RecordInterface):
        model_config = ConfigDict(strict=True, extra='forbid')

        type: str
        assertion_ref: dict
        case_ids: list[str]
        wins: int
        losses: int
        ties: int
        abstentions: int
        comparisons: int
        opponent_count: int
        possible_opponents: int
        value: float | None
        coverage: float
        tribunal_type_id: str

    def __init__(self, row: Mapping[str, object]):
        super().__init__()
        if 'type' in row:
            raise ValueError('A score row must not supply its Type')
        self._row = json.loads(json.dumps(dict(row), allow_nan=False))
        self._record = {'type': entity(type(self)).name, **self._row}
        type(self).records.parse_record(self._record)

    def __getitem__(self, key: str) -> object:
        return deepcopy(self._row[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._row)

    def __len__(self) -> int:
        return len(self._row)

    def as_row(self) -> dict[str, object]:
        """Return the existing row-shaped public payload without its Type tag."""
        return deepcopy(self._row)

    @classmethod
    def _from_record(cls, data):
        return cls({key: value for key, value in data.model_dump().items() if key != 'type'})

    class Records(Score.Records):
        def record_example(self):
            cls = self._owner
            return cls({
                'assertion_ref': {'type': 'Example.Assertion.Reference'},
                'case_ids': [], 'wins': 0, 'losses': 0, 'ties': 0,
                'abstentions': 0, 'comparisons': 0, 'opponent_count': 0,
                'possible_opponents': 0, 'value': None, 'coverage': 0.0,
                'tribunal_type_id': '00000000-0000-4000-8000-000000000006',
            }).records.to_record()
