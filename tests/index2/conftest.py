from __future__ import annotations

from pathlib import Path

import pytest

from tarav.index2.config import Geography


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
    return root


@pytest.fixture
def user_root(tmp_path: Path) -> Path:
    root = tmp_path / "user-tier"
    root.mkdir()
    return root


@pytest.fixture
def geo(project_root: Path, user_root: Path) -> Geography:
    return Geography(project_root=project_root, user_root=user_root)


@pytest.fixture
def chat(monkeypatch):
    """Install a fake archive and return a builder for its turns.

    Gates are checked against an immutable chat, so the tests need one — but not a real
    provider home, which is user-scoped and absent on any other machine.
    """

    from tarav.index2.chatlas import ChatMessage, ChatSession

    sessions: dict[str, ChatSession] = {}

    def build(session_id: str, turns: list[tuple[str, str, str]]) -> ChatSession:
        session = ChatSession(
            session_id=session_id,
            messages=tuple(
                ChatMessage(
                    session_id=session_id,
                    address=address,
                    side=side,
                    text=text,
                    at=None,
                    carries_touch=side == "user",
                )
                for address, side, text in turns
            ),
        )
        sessions[session_id] = session
        return session

    def fake_load(_geo, session_id):
        from tarav.index2.chatlas import ChatError

        if session_id not in sessions:
            raise ChatError(f"no archived session {session_id!r}")
        return sessions[session_id]

    monkeypatch.setattr("tarav.index2.gates.load_session", fake_load)
    monkeypatch.setattr("tarav.index2.linter.load_session", fake_load)
    return build
