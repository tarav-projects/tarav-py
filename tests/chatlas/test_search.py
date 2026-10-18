from __future__ import annotations

from pathlib import Path

import pytest

from chatlas._helpers import normal_model_fixture

from tarav.l1.chatlas import normal_model_cache
from tarav.l1.chatlas import stages as stages_module
from tarav.l1.chatlas.index_writer import _upsert_session_index_rows
from tarav.l1.chatlas.paths import SESSION_INDEX_ROOT
from tarav.l1.chatlas.search import ChatlasSearchEngine, ChatlasSearchQuery
from tarav.l1.chatlas.stages import ChatlasStages
from tarav.l1.search import SearchQuery
from tarav.l3.runtime import create_runtime

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
        self.unbuildable: set[str] = set()
        self.captures: list[dict] = []
        monkeypatch.setattr(normal_model_cache, "build_normal_model_from_row", self._build)
        monkeypatch.setattr(stages_module, "chatlas_update",
                            lambda **scope: self.captures.append(scope) or {"status": "ok"})
        for identity in CHATS:
            self.index_row(identity)

    def index_row(self, identity: str) -> None:
        session_id, project, activity, _turns = CHATS[identity]
        source = self.root / "raw" / f"{identity[:4]}.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("raw\n", encoding="utf-8")
        _upsert_session_index_rows(self.root / SESSION_INDEX_ROOT, rows=[{
            "provider": "codex", "instance": "work", "provider_instance_fingerprint": "f" * 64,
            "session_id": session_id, "identity_hash": identity, "uri": f"agentos://{session_id}",
            "project_path": project, "last_activity_at": activity,
            "backing_artifacts": [{"role": "transcript", "path": str(source)}],
        }])

    def _build(self, row, *, include_raw=False):
        from tarav.l0._core.errors import CliError

        identity = row["identity_hash"]
        if identity in self.unbuildable:
            raise CliError("Chatlas found no recognized codex transcript artifact")
        session_id, _project, _activity, turns = CHATS[identity]
        return normal_model_fixture(self.root / "raw" / f"{identity[:4]}.jsonl",
                                    identity_hash=identity, session_id=session_id, turns=turns)

    def prepare(self) -> None:
        ChatlasStages(chatlas_root=self.root).run(stages=("cache", "index"))

    def search(self, *args, **kwargs):
        engine = ChatlasSearchEngine(chatlas_root=self.root)
        return engine.search.run(ChatlasSearchQuery(*args, **kwargs))


@pytest.fixture
def depot(tmp_path: Path, monkeypatch) -> Depot:
    return Depot(tmp_path / "chatlas", monkeypatch)


def _texts(result) -> list[str]:
    return [" | ".join(message["text"] for message in hit.value.messages) for hit in result.hits]


def test_turns_are_found_across_chats_newest_first(depot: Depot) -> None:
    depot.prepare()

    result = depot.search("cache")

    assert _texts(result) == ["search the CACHE again", "The cache is in normal-model.",
                              "Where is the cache?"]
    first = result.hits[0].value
    assert first.target == "turns"
    assert first.session["session_id"] == "new-chat"
    assert first.session["project_path"] == "/work/beta/app"
    assert first.turn["side"] == "user" and len(first.turn["turn_hash"]) == 64


def test_messages_words_substrings_and_raw_fts(depot: Depot) -> None:
    depot.prepare()

    assert _texts(depot.search("cache", target="messages", side="agent")) == [
        "The cache is in normal-model."]
    assert _texts(depot.search(contains="ormal-mod", target="messages")) == [
        "The cache is in normal-model."]
    assert _texts(depot.search(match="search OR where", target="messages")) == [
        "search the CACHE again", "Where is the cache?"]
    assert _texts(depot.search("cache is in", target="messages")) == [
        "The cache is in normal-model."]


def test_session_filters_and_the_first_hits(depot: Depot) -> None:
    depot.prepare()

    assert _texts(depot.search("cache", project="/work/beta")) == ["search the CACHE again"]
    assert _texts(depot.search("cache", project="/work/bet")) == []
    assert _texts(depot.search("cache", until="2026-10-02T00:00:00Z", side="user")) == [
        "Where is the cache?"]
    assert _texts(depot.search("cache", since="2026-10-02T00:00:00Z")) == [
        "search the CACHE again"]
    assert _texts(depot.search("cache", max_hits=1)) == ["search the CACHE again"]


def test_search_reads_the_index_as_it_is_unless_asked_to_update(depot: Depot) -> None:
    with pytest.raises(FileNotFoundError, match="index"):
        depot.search("again")

    result = depot.search("again", cache=True, index=True)
    assert _texts(result) == ["search the CACHE again"]
    assert depot.captures == []
    depot.search("again", capture=True, provider="codex")
    assert [scope["providers"] for scope in depot.captures] == [("codex",)]


def test_a_chat_that_cannot_be_built_is_left_out(depot: Depot) -> None:
    depot.unbuildable.add(NEW)

    assert _texts(depot.search("cache", side="user", cache=True, index=True)) == [
        "Where is the cache?"]


def test_the_engine_only_answers_chatlas_queries(depot: Depot) -> None:
    engine = ChatlasSearchEngine(chatlas_root=depot.root)

    assert engine.search.run(SearchQuery()).declined
    with pytest.raises(ValueError, match="target"):
        ChatlasSearchQuery("cache", target="events")
    with pytest.raises(ValueError, match="since"):
        ChatlasSearchQuery("cache", since="yesterday")


def test_the_runtime_search_service_routes_to_chatlas(depot: Depot) -> None:
    depot.prepare()
    service = create_runtime().search
    service.engines["chatlas"].chatlas_root = depot.root

    result = service.search.run(ChatlasSearchQuery("again"))

    assert _texts(result) == ["search the CACHE again"]
    assert result.hits[0].engines == ("chatlas",)
