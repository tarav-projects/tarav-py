from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from chatlas.test_normal_models_index import ALPHA, BETA, Depot

from tarav.l1.chatlas import stages as stages_module
from tarav.l1.chatlas.stages import ChatlasStages


@pytest.fixture
def depot(tmp_path: Path, monkeypatch) -> Depot:
    return Depot(tmp_path / "chatlas", monkeypatch)


@pytest.fixture
def captured(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(stages_module, "chatlas_update",
                        lambda **scope: calls.append(scope) or {"status": "ok"})
    return calls


def _states(stages: ChatlasStages, rows) -> dict[str, tuple[str, str]]:
    standing = stages.standing(rows)
    return {identity: (item.cache["turns"].state, item.index["turns"].state)
            for identity, item in standing.items()}


def test_each_stage_reports_its_standing_and_updates_on_its_own(depot: Depot) -> None:
    stages = ChatlasStages(chatlas_root=depot.root)
    rows = stages.select()
    assert _states(stages, rows) == {ALPHA: ("missing", "missing"), BETA: ("missing", "missing")}

    assert stages.update_cache(rows).done == (ALPHA, BETA)
    assert _states(stages, rows) == {ALPHA: ("fresh", "missing"), BETA: ("fresh", "missing")}
    assert stages.update_index(rows).indexed == (ALPHA, BETA)
    assert _states(stages, rows) == {ALPHA: ("fresh", "fresh"), BETA: ("fresh", "fresh")}

    depot.capture(ALPHA, "one\ntwo\n")
    rows = stages.select()
    assert _states(stages, rows)[ALPHA] == ("stale", "fresh")
    assert stages.update_cache(rows, policy="missing").done == ()
    assert stages.update_cache(rows).done == (ALPHA,)
    assert _states(stages, rows)[ALPHA] == ("fresh", "stale")


def test_a_selection_narrows_every_stage(depot: Depot, captured: list[dict]) -> None:
    stages = ChatlasStages(chatlas_root=depot.root)

    report = stages.run(project="/work/beta", stages=("capture", "cache", "index"))

    assert captured == [{"providers": None, "session_ids": (), "window_seconds": None,
                         "chatlas_root": depot.root}]
    assert report["cache"].done == (BETA,)
    assert report["index"].indexed == (BETA,)
    assert set(stages.standing(stages.select(project="/work/alpha"))) == {ALPHA}


def test_capture_scope_follows_provider_identities_and_window(
    depot: Depot, captured: list[dict]
) -> None:
    stages = ChatlasStages(chatlas_root=depot.root)
    since = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    stages.capture(provider="codex", identities=(ALPHA,), since=since)

    (scope,) = captured
    assert scope["providers"] == ("codex",)
    assert scope["session_ids"] == (ALPHA[:4],)
    assert 7100 < scope["window_seconds"] <= 7200


def test_running_no_stage_does_nothing(depot: Depot, captured: list[dict]) -> None:
    stages = ChatlasStages(chatlas_root=depot.root)

    assert stages.run(stages=()) == {}
    assert captured == []
    assert not (depot.root / "index" / "normal-models.sqlite").exists()
    with pytest.raises(ValueError, match="stage"):
        stages.run(stages=("compress",))
