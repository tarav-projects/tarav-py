# $kw: --from Provider.Home.Adapter
"""`Provider.Home.Adapter` — the one Chatlas component with provider-native
data-home contact.

Discovery scans, session lookup, change signatures, and the home→archive copy
all enter through the adapter; every other Chatlas system answers from the
depot or reaches provider data by means of the adapter. The adapter reads any
provider-native layout — the live `Provider.Home` or its verbatim copy inside
the `Raw.Archive` (raw partitions mirror the home layout) — so provider-agent
discovery mechanics live nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from tarav.agent.primitives import AgentConfig, SessionSource
from tarav.agent.session_refs import (
    BackingArtifact,
    ProviderSessionRef,
    backing_artifacts_from_sources,
)

from tarav.chatlas.path_hygiene import path_has_symlink_component
from tarav.chatlas.raw_archive import (
    _copy_delta_session_sources as _raw_copy_delta_session_sources,
    _path_metadata_signature,
)


def _path_component(value: str) -> str:
    return quote(value, safe="._-")


def _session_cache_key(session_id: str) -> str:
    return _path_component(session_id)


@dataclass(frozen=True)
class ChatlasProviderInstance:
    agent: AgentConfig
    fingerprint: str
    source_home: str | None = None

    @property
    def provider(self) -> str:
        return self.agent.provider

    @property
    def instance(self) -> str:
        return self.agent.profile_id or self.fingerprint[:12]

    @property
    def partition_key(self) -> str:
        return f"{_path_component(self.provider)}/{_path_component(self.fingerprint)}"

    def raw_home(self, raw_root: Path) -> Path | None:
        if self.agent.home is None:
            return None
        return raw_root / self.partition_key / "home"


@dataclass(frozen=True)
class ChatlasDiscoveredSession:
    provider_instance: ChatlasProviderInstance
    session_ref: ProviderSessionRef

    @property
    def session_id(self) -> str:
        return self.session_ref.native_session_id

    @property
    def cache_key(self) -> str:
        return _session_cache_key(self.session_id)

    def sources(self) -> tuple[SessionSource, ...]:
        return self.session_ref.to_session().sources()

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return backing_artifacts_from_sources(self.sources())


@dataclass(frozen=True)
class ChatlasDeltaSession:
    session: ChatlasDiscoveredSession
    sources: tuple[SessionSource, ...]

    @property
    def session_id(self) -> str:
        return self.session.session_id


def provider_instance_home(instance: ChatlasProviderInstance) -> str | None:
    if instance.source_home is not None:
        return instance.source_home
    if instance.agent.home is None:
        return None
    return str(instance.agent.home)


def dedupe_sessions(
    sessions: list[ChatlasDiscoveredSession],
) -> list[ChatlasDiscoveredSession]:
    deduped: dict[tuple[str, str, str], ChatlasDiscoveredSession] = {}
    for session in sessions:
        key = (
            session.provider_instance.provider,
            session.provider_instance.fingerprint,
            session.session_id,
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = session
            continue
        left_ref = existing.session_ref
        right_ref = session.session_ref
        if hasattr(left_ref, "merge"):
            merged_ref = left_ref.merge(right_ref)
        else:
            merged_ref = left_ref
        deduped[key] = ChatlasDiscoveredSession(
            provider_instance=existing.provider_instance,
            session_ref=merged_ref,
        )
    return sorted(
        deduped.values(),
        key=lambda session: (
            session.provider_instance.provider,
            session.provider_instance.fingerprint,
            session.session_id,
        ),
    )


class ProviderHomeAdapter:
    """All provider-native home contact for one `ChatlasProviderInstance`."""

    def __init__(self, instance: ChatlasProviderInstance) -> None:
        self.instance = instance

    def discover(self) -> list[ChatlasDiscoveredSession]:
        agent = self.instance.agent
        if not hasattr(agent, "discover_session_refs"):
            return []
        sessions = [
            ChatlasDiscoveredSession(
                provider_instance=self.instance, session_ref=session_ref
            )
            for session_ref in agent.discover_session_refs()
        ]
        return dedupe_sessions(
            [
                session
                for session in sessions
                if not _session_has_symlinked_source(session)
            ]
        )

    def find_session_ref(self, session_id: str) -> ProviderSessionRef | None:
        agent = self.instance.agent
        finder = getattr(agent, "find_session_ref_by_id", None)
        if finder is not None:
            session_ref = finder(session_id)
        else:
            session_ref = self._discover_session_ref(session_id)
        if session_ref is None:
            return None
        discovered = ChatlasDiscoveredSession(
            provider_instance=self.instance, session_ref=session_ref
        )
        if _session_has_symlinked_source(discovered):
            return None
        return session_ref

    def find_session(self, session_id: str) -> ChatlasDiscoveredSession | None:
        session_ref = self.find_session_ref(session_id)
        if session_ref is None:
            return None
        return ChatlasDiscoveredSession(
            provider_instance=self.instance, session_ref=session_ref
        )

    def source_signature(self, source: SessionSource) -> dict[str, object]:
        signature = _path_metadata_signature(source.path)
        signature.update(
            {
                "role": source.role,
                "storage_kind": source.normalized_storage_kind(),
                "locator": source.locator,
            }
        )
        return signature

    def archive(
        self,
        delta_session: ChatlasDeltaSession,
        *,
        raw_root: Path,
        empty_report: dict[str, int],
    ) -> dict[str, int]:
        return _raw_copy_delta_session_sources(
            delta_session,
            raw_root=raw_root,
            empty_report=empty_report,
        )

    def _discover_session_ref(self, session_id: str) -> ProviderSessionRef | None:
        agent = self.instance.agent
        discover = getattr(agent, "discover_session_refs", None)
        if discover is None:
            return None
        for session_ref in discover():
            if getattr(session_ref, "native_session_id", None) == session_id:
                return session_ref
        return None


def _session_has_symlinked_source(session: ChatlasDiscoveredSession) -> bool:
    return any(
        path_has_symlink_component(source.path) for source in session.sources()
    )


__all__ = [
    "ChatlasDeltaSession",
    "ChatlasDiscoveredSession",
    "ChatlasProviderInstance",
    "ProviderHomeAdapter",
    "dedupe_sessions",
    "provider_instance_home",
]
