from __future__ import annotations

from pathlib import Path

import pytest

from chatlas._helpers import normal_model_fixture

from tarav.l1.chatlas import normal_model_cache
from tarav.l1.chatlas.index_store import load_chatlas_session_index_rows
from tarav.l1.chatlas.index_writer import _upsert_session_index_rows
from tarav.l1.chatlas.normal_models_index import NormalModelsIndex
from tarav.l1.chatlas.paths import SESSION_INDEX_ROOT

ALPHA, BETA = "a" * 64, "b" * 64
TURNS = {
    ALPHA: (("user", "Where is the cache?"), ("agent", "The cache lives in normal-model.")),
    BETA: (("user", "index the chats"),),
}


class Depot:
    def __init__(self, root: Path, monkeypatch) -> None:
        self.root = root
        self.turns = dict(TURNS)
        monkeypatch.setattr(normal_model_cache, "build_normal_model_from_row", self._model)
        for identity in TURNS:
            self.capture(identity, "one\n")

    def capture(self, identity: str, text: str) -> None:
        source = self.root / "raw" / f"{identity[:4]}.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
        _upsert_session_index_rows(self.root / SESSION_INDEX_ROOT, rows=[{
            "provider": "codex", "instance": "work", "provider_instance_fingerprint": "f" * 64,
            "session_id": identity[:4], "identity_hash": identity, "uri": f"agentos://{identity[:4]}",
            "project_path": "/work/alpha" if identity == ALPHA else "/work/beta",
            "last_activity_at": "2026-10-18T00:00:00Z",
            "backing_artifacts": [{"role": "transcript", "path": str(source)}],
        }])

    def _model(self, row, *, include_raw=False):
        identity = row["identity_hash"]
        return normal_model_fixture(self.root / "raw" / f"{identity[:4]}.jsonl",
                                    identity_hash=identity, session_id=identity[:4],
                                    turns=self.turns[identity])

    def rows(self) -> list[dict]:
        return list(load_chatlas_session_index_rows(chatlas_root=self.root).rows)

    def cache(self, identity: str) -> None:
        row = next(row for row in self.rows() if row["identity_hash"] == identity)
        normal_model_cache.NormalModelCache(row, chatlas_root=self.root).build()


@pytest.fixture
def depot(tmp_path: Path, monkeypatch) -> Depot:
    return Depot(tmp_path / "chatlas", monkeypatch)


def _states(index: NormalModelsIndex, depot: Depot) -> dict[str, dict[str, str]]:
    return {identity: {part: standing.state for part, standing in parts.items()}
            for identity, parts in index.standing(depot.rows()).items()}


def test_the_index_holds_the_cached_messages_and_turns_of_each_session(depot: Depot) -> None:
    depot.cache(ALPHA)
    index = NormalModelsIndex(chatlas_root=depot.root)

    report = index.update(depot.rows())

    assert index.path == depot.root / "index" / "normal-models.sqlite"
    assert report.indexed == (ALPHA,)
    assert report.skipped == (BETA,)
    assert index.query(
        "select side, text, turn_hash is not null as in_turn from messages "
        "where identity = ? order by position", (ALPHA,)
    ) == [
        {"side": "user", "text": "Where is the cache?", "in_turn": 1},
        {"side": "agent", "text": "The cache lives in normal-model.", "in_turn": 1},
    ]
    assert index.query("select count(*) as n from turns") == [{"n": 2}]
    assert index.query(
        "select m.text from messages_fts f join messages m on m.id = f.rowid "
        "where messages_fts match 'cache' order by m.position"
    ) == [{"text": "Where is the cache?"}, {"text": "The cache lives in normal-model."}]


def test_each_indexed_part_records_the_cache_version_it_consumed(depot: Depot) -> None:
    index = NormalModelsIndex(chatlas_root=depot.root)
    depot.cache(ALPHA)
    depot.cache(BETA)
    assert _states(index, depot)[ALPHA] == {"messages": "missing", "turns": "missing"}

    index.update(depot.rows())
    assert _states(index, depot)[ALPHA] == {"messages": "fresh", "turns": "fresh"}

    depot.turns[ALPHA] = (*TURNS[ALPHA], ("user", "and the index?"))
    depot.capture(ALPHA, "one\ntwo\n")
    depot.cache(ALPHA)
    assert _states(index, depot) == {
        ALPHA: {"messages": "stale", "turns": "stale"},
        BETA: {"messages": "fresh", "turns": "fresh"},
    }
    assert index.update(depot.rows(), policy="missing").indexed == ()

    report = index.update(depot.rows())
    assert report.indexed == (ALPHA,)
    assert index.query("select count(*) as n from messages where identity = ?", (ALPHA,)) == [{"n": 3}]
    assert index.query("select count(*) as n from messages_fts where messages_fts match 'index'") == [
        {"n": 2}]


def test_queries_read_without_writing(depot: Depot) -> None:
    depot.cache(BETA)
    index = NormalModelsIndex(chatlas_root=depot.root)
    index.update(depot.rows())

    with pytest.raises(Exception, match="readonly"):
        index.query("delete from messages")
    assert index.query("select count(*) as n from messages") == [{"n": 1}]
