from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


@dataclass(frozen=True)
class ProviderFamily:
    family: str


@dataclass(frozen=True)
class ProviderInstanceAnchor:
    role: str
    path: Path
    slot: str | None = None

    def identity_key(self) -> tuple[str, str | None, str]:
        return (self.role, self.slot, str(self.path))

    def summary(self) -> dict[str, str]:
        payload = {
            "role": self.role,
            "path": str(self.path),
        }
        if self.slot is not None:
            payload["slot"] = self.slot
        return payload


def _provider_instance_fingerprint(
    *,
    family: str,
    anchors: tuple[ProviderInstanceAnchor, ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(family.encode("utf-8"))
    for anchor in anchors:
        digest.update(b"\0")
        digest.update(anchor.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update((anchor.slot or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(anchor.path).encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class ProviderInstance:
    family: str
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    cli_command: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    timeout_sec: int | None = None
    live_usage_refresh: bool | None = None
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    anchors: tuple[ProviderInstanceAnchor, ...] = ()
    is_default: bool = False

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    @property
    def fingerprint(self) -> str:
        if self.anchors:
            return _provider_instance_fingerprint(
                family=self.family,
                anchors=self.anchors,
            )

        fallback_anchors = tuple(
            ProviderInstanceAnchor(role=f"direct_target_{index + 1}", path=path)
            for index, path in enumerate(self.direct_targets)
        ) + tuple(
            ProviderInstanceAnchor(role=f"sqlite_db_{index + 1}", path=path)
            for index, path in enumerate(self.sqlite_db_paths)
        )
        return _provider_instance_fingerprint(
            family=self.family,
            anchors=fallback_anchors,
        )

    def matches_fingerprint_prefix(self, fingerprint_prefix: str) -> bool:
        normalized_prefix = fingerprint_prefix.strip().lower()
        if not normalized_prefix:
            return False
        return self.fingerprint.startswith(normalized_prefix)

    def identity_key(self) -> tuple[object, ...]:
        if self.anchors:
            return (
                self.family,
                tuple(anchor.identity_key() for anchor in self.anchors),
            )
        return (
            self.family,
            self.instance_id,
            tuple((key, str(path)) for key, path in self.homes),
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.env,
            self.timeout_sec,
            self.live_usage_refresh,
            self.includes,
            self.excludes,
        )

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": self.family,
            "fingerprint": self.fingerprint,
            "is_default": self.is_default,
        }
        if self.instance_id is not None:
            payload["instance_id"] = self.instance_id
        if self.label is not None:
            payload["label"] = self.label
        if self.anchors:
            payload["anchors"] = [anchor.summary() for anchor in self.anchors]
        if self.homes:
            payload["homes"] = {key: str(path) for key, path in self.homes}
        if self.direct_targets:
            payload["direct_targets"] = [str(path) for path in self.direct_targets]
        if self.grep_targets:
            payload["grep_targets"] = [str(path) for path in self.grep_targets]
        if self.sqlite_db_paths:
            payload["sqlite_db_paths"] = [str(path) for path in self.sqlite_db_paths]
        if self.cli_command:
            payload["cli_command"] = list(self.cli_command)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.live_usage_refresh is not None:
            payload["live_usage_refresh"] = self.live_usage_refresh
        if self.includes:
            payload["includes"] = list(self.includes)
        if self.excludes:
            payload["excludes"] = list(self.excludes)
        return payload

    def uri_component(self) -> str:
        return quote(self.fingerprint, safe="")


__all__ = [
    "ProviderFamily",
    "ProviderInstance",
    "ProviderInstanceAnchor",
]
