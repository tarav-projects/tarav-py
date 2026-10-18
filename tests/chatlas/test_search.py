from __future__ import annotations

from pathlib import Path

import pytest

from chatlas._helpers import normal_model_fixture

from tarav.l0._core.errors import CliError
from tarav.l1.chatlas import normal_model_cache
from tarav.l1.chatlas.index_writer import _upsert_session_index_rows
from tarav.l1.chatlas.paths import SESSION_INDEX_ROOT
from tarav.l1.chatlas.search import ChatlasSearchEngine, ChatlasSearchQuery
from tarav.l1.search import SearchQuery

OLD, NEW = "1" * 64, "2" * 64
CHATS = {
    OLD: ("old-chat", "/work/alpha", "2026-10-01T00:00:00Z",
          (("user", "Where is the cache?"), ("agent", "The cache is in normal-model."))),
    NEW: ("new-chat", "/work/beta/app", "2026-10-18T00:00:00Z",
          (("user", "search the CACHE again"), ("agent", "Searching."))),
}


class Depot:
    def __init__(self, root: Path, monkeypatch) -> None:
        self.root = root
        self.builds: list[str] = []
        self.unbuildable: set[str] = set()
        monkeypatch.setattr(normal_model_cache, "build_normal_model_from_row", self._build)
        for identity in CHATS:
            self.index(identity)

    def transcript(self, identity: str) -> Path:
        return self.root / "raw" / f"{identity[:4]}.jsonl"

    def index(self, identity: str, *, text: str = "raw\n") -> None:
        session_id, project, activity, _turns = CHATS[identity]
        source = self.transcript(identity)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
        _upsert_session_index_rows(self.root / SESSION_INDEX_ROOT, rows=[{
            "provider": "codex", "instance": "work", "provider_instance_fingerprint": "f" * 64,
            "session_id": session_id, "identity_hash": identity, "uri": f"agentos://{session_id}",
            "project_path": project, "last_activity_at": activity,
            "backing_artifacts": [{"role": "transcript", "path": str(source)}],
        }])

    def _build(self, row, *, include_raw=False):
        identity = row["identity_hash"]
        self.builds.append(identity)
        if identity in self.unbuildable:
            raise CliError("Chatlas found no recognized codex transcript artifact")
        session_id, _project, _activity, turns = CHATS[identity]
        return normal_model_fixture(self.transcript(identity), identity_hash=identity,
                                    session_id=session_id, turns=turns)

    def search(self, *args, **kwargs):
        engine = ChatlasSearchEngine(chatlas_root=self.root)
        return engine.search.run(ChatlasSearchQuery(*args, **kwargs))


@pytest.fixture
def depot(tmp_path: Path, monkeypatch) -> Depot:
    return Depot(tmp_path / "chatlas", monkeypatch)


def _texts(result) -> list[str]:
    return [
        hit.value.message["text"] if hit.value.target == "messages"
        else " | ".join(message["text"] for message in hit.value.turn.messages)
        for hit in result.hits
    ]


def test_turns_are_found_across_chats_newest_first(depot: Depot) -> None:
    result = depot.search("cache")

    assert _texts(result) == [
        "search the CACHE again",
        "The cache is in normal-model.",
        "Where is the cache?",
    ]
    first = result.hits[0].value
    assert first.target == "turns"
    assert first.session["session_id"] == "new-chat"
    assert first.session["project_path"] == "/work/beta/app"
    assert set(first.parts) == {"main", "turns", "messages"}
    assert all(part.fresh for part in first.parts.values())
    assert first.turn.started_at is None
    assert sorted(depot.builds) == [OLD, NEW]


def test_messages_can_be_searched_on_their_own(depot: Depot) -> None:
    result = depot.search("cache", target="messages", side="agent")

    assert _texts(result) == ["The cache is in normal-model."]
    assert set(result.hits[0].value.parts) == {"main", "messages"}
    assert result.hits[0].value.turn is None


def test_session_filters_come_from_the_index(depot: Depot) -> None:
    assert _texts(depot.search("cache", project="/work/beta")) == ["search the CACHE again"]
    assert _texts(depot.search("cache", project="/work/bet")) == []
    assert _texts(depot.search("cache", until="2026-10-02T00:00:00Z", side="user")) == [
        "Where is the cache?"]
    assert _texts(depot.search("cache", since="2026-10-02T00:00:00Z")) == [
        "search the CACHE again"]
    assert depot.builds == [NEW, OLD]


def test_the_first_hits_end_the_scan(depot: Depot) -> None:
    result = depot.search("cache", max_hits=1)

    assert _texts(result) == ["search the CACHE again"]
    assert depot.builds == [NEW]


def test_missing_caches_are_built_unless_the_caller_declines(depot: Depot) -> None:
    assert depot.search("cache", build_missing=False).hits == ()
    depot.search("again")
    depot.search("again")

    assert sorted(depot.builds) == [OLD, NEW]


def test_a_stale_cache_is_searched_and_flagged(depot: Depot) -> None:
    depot.search("cache")
    depot.index(NEW, text="raw, grown\n")

    hit = depot.search("again").hits[0].value

    assert hit.session["session_id"] == "new-chat"
    assert {part.stale for part in hit.parts.values()} == {True}
    assert hit.session["raw_version"] == hit.parts["turns"].current_raw_version
    assert len(depot.builds) == 2


def test_a_chat_that_cannot_be_built_is_skipped(depot: Depot) -> None:
    depot.unbuildable.add(NEW)

    assert _texts(depot.search("cache", side="user")) == ["Where is the cache?"]


def test_turn_start_times_are_opt_in(depot: Depot) -> None:
    hit = depot.search("again", times=True).hits[0].value

    assert hit.turn.started_at == "2026-10-18T00:00:01Z"
    assert set(hit.parts) == {"main", "turns", "messages", "events"}


def test_the_engine_only_answers_chatlas_queries(depot: Depot) -> None:
    engine = ChatlasSearchEngine(chatlas_root=depot.root)

    assert engine.search.run(SearchQuery()).declined
    with pytest.raises(ValueError, match="target"):
        ChatlasSearchQuery("cache", target="events")
    with pytest.raises(ValueError, match="since"):
        ChatlasSearchQuery("cache", since="yesterday")
