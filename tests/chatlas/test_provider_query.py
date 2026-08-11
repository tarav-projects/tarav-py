from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.chatlas.provider_home_adapter import ChatlasProviderInstance
from agentos.chatlas.provider_query import chatlas_provider_query


@dataclass(frozen=True)
class _FakeSession:
    path: Path

    def sources(self) -> tuple[object, ...]:
        return ()


@dataclass(frozen=True)
class _FakeSessionRef:
    native_session_id: str

    def to_session(self) -> _FakeSession:
        return _FakeSession(path=Path("/tmp/session.jsonl"))

    def display_name(self) -> str:
        return "fallback session"


@dataclass(frozen=True)
class _DiscoveryOnlyAgent:
    provider: str = "gemini-cli"
    profile_id: str | None = None
    home: Path | None = Path("/tmp/gemini-home")

    def fingerprint(self) -> str:
        return "fingerprint"

    def discover_session_refs(self) -> tuple[_FakeSessionRef, ...]:
        return (_FakeSessionRef(native_session_id="session-1"),)


def test_provider_query_falls_back_to_discovery_when_direct_lookup_is_missing(
    monkeypatch,
) -> None:
    instance = ChatlasProviderInstance(agent=_DiscoveryOnlyAgent(), fingerprint="fingerprint")
    monkeypatch.setattr(
        "agentos.chatlas.provider_query.selected_provider_instances",
        lambda *, providers, start_path: (instance,),
    )

    payload = chatlas_provider_query(
        provider="gemini-cli",
        session_ids=("session-1",),
    )

    assert payload["row_count"] == 1
    assert payload["rows"][0]["found"] is True
    assert payload["rows"][0]["display_name"] == "fallback session"
