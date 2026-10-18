from __future__ import annotations

from pathlib import Path

import pytest

from chatlas._helpers import normal_model_fixture

from tarav.l0._core.errors import CliError
from tarav.l1.chatlas.normal_model import ChatlasNormalModel
from tarav.l1.chatlas.query import ChatlasQuery, ChatlasQueryEngine


def _model_without_events(tmp_path: Path) -> ChatlasNormalModel:
    model = ChatlasNormalModel.materialize(
        tmp_path / "model",
        normal_model_fixture(tmp_path / "source.jsonl",
                             turns=(("user", "find the cache"), ("agent", "found it"))),
    )
    (model.directory / "events.jsonl").unlink()
    return model


def test_a_query_without_times_reads_no_events(tmp_path: Path) -> None:
    reader = _model_without_events(tmp_path)

    result = ChatlasQueryEngine(reader).run(
        ChatlasQuery(text_contains="CACHE", times=False)
    )

    assert [match.messages[0]["text"] for match in result.matches] == ["find the cache"]
    assert result.matches[0].started_at is None
    assert result.query.to_dict()["times"] is False


def test_turn_start_times_still_come_from_events_by_default(tmp_path: Path) -> None:
    reader = _model_without_events(tmp_path)

    with pytest.raises(CliError, match="invalid Normal Model stream"):
        ChatlasQueryEngine(reader).run(ChatlasQuery(text_contains="cache"))
