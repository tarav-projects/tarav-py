from __future__ import annotations

from pathlib import Path

import pytest

from chatlas._helpers import normal_model_fixture

from tarav.l1.chatlas import normal_model_cache
from tarav.l1.chatlas.index_writer import _upsert_session_index_rows
from tarav.l1.chatlas.normal_model.turn_ref import chat_turn_ref
from tarav.l1.chatlas.paths import SESSION_INDEX_ROOT
from tarav.l2.breadcrumb_workflows.chatlas_context import workflow

IDENTITY = "3" * 64
OLD = (("user", "first question"),)
NEW = (("user", "first question"), ("agent", "answer"), ("user", "second question"))


class Chat:
    """One indexed session whose raw data grows; builds are counted."""

    def __init__(self, root: Path, monkeypatch) -> None:
        self.root, self.turns, self.builds = root, OLD, 0
        self.source = root / "raw" / "chat.jsonl"
        self.source.parent.mkdir(parents=True)
        monkeypatch.setattr(normal_model_cache, "build_normal_model_from_row", self._model)
        monkeypatch.setattr(workflow, "compute_normal_model", self._compute)
        self.write("one\n")

    def write(self, text: str) -> None:
        self.source.write_text(text, encoding="utf-8")
        _upsert_session_index_rows(self.root / SESSION_INDEX_ROOT, rows=[{
            "provider": "codex", "instance": "work", "provider_instance_fingerprint": "f" * 64,
            "session_id": "chat", "identity_hash": IDENTITY, "uri": "agentos://chat",
            "last_activity_at": "2026-10-18T00:00:00Z",
            "backing_artifacts": [{"role": "transcript", "path": str(self.source)}],
        }])

    def _model(self, row, *, include_raw=False):
        return normal_model_fixture(self.source, identity_hash=IDENTITY, session_id="chat",
                                    turns=self.turns)

    def _compute(self, *, identity_hash, chatlas_root):
        self.builds += 1
        return self._model(None)

    def locator(self, index: int) -> dict:
        turns = self._model(None)["turns"]
        return chat_turn_ref(turns[index])

    def resolve(self, locator: dict, memo: dict) -> str:
        return workflow._resolve_turn(locator, IDENTITY, self.root, memo)["standing"]


@pytest.fixture
def chat(tmp_path: Path, monkeypatch) -> Chat:
    return Chat(tmp_path / "chatlas", monkeypatch)


def _cache(chat: Chat) -> normal_model_cache.NormalModelCache:
    from tarav.l1.chatlas.session_resolver import resolve_session_index_row

    row = resolve_session_index_row(identity_hash=IDENTITY, chatlas_root=chat.root)
    return normal_model_cache.NormalModelCache(row, chatlas_root=chat.root)


def test_a_turn_found_in_a_stale_cache_needs_no_rebuild(chat: Chat) -> None:
    _cache(chat).build()
    chat.turns = NEW
    chat.write("one\ntwo\n")
    assert _cache(chat).parts()["turns"].stale

    assert chat.resolve(chat.locator(0), {}) == "MATCHED"
    assert chat.builds == 0


def test_a_turn_missing_from_the_cache_is_looked_up_once_in_raw(chat: Chat) -> None:
    _cache(chat).build()
    chat.turns = NEW
    chat.write("one\ntwo\n")
    memo: dict = {}

    assert chat.resolve(chat.locator(2), memo) == "MATCHED"
    assert chat.resolve(chat.locator(1), memo) == "MATCHED"
    assert chat.builds == 1


def test_without_a_cache_the_audit_computes_and_writes_nothing(chat: Chat) -> None:
    assert chat.resolve(chat.locator(0), {}) == "MATCHED"

    assert chat.builds == 1
    assert not _cache(chat).path.exists()
