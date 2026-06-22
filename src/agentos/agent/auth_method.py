"""The `Auth.Method` provider seam.

`Account.Model:Auth.Method` is an independent authentication method of an account
— a credential class that knows how to read/serialize its `Auth.Data`, extract the
`Account.Identity` that binds it to an account, and materialize it into a home.

This module holds the provider-agnostic abstraction only. Provider subclasses
(codex/claude/copilot) live with their provider packages and are wired in during
the per-provider cutover. See the `Account.Management` appendix in `agentos-pkg`.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from agentos.agent.account_status import AccountIdentity


@dataclass(frozen=True)
class AuthData:
    """A single credential payload read from a source or stored as an artifact.

    Content-addressed: identical payloads produce the same `content_id`, which is
    the `Auth.Data.Artifact` identity used for dedup in the registry.
    """

    payload: Mapping[str, object] = field(default_factory=dict)

    def content_id(self) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuthMethod(ABC):
    """Capability surface for one credential class.

    Subclasses set the class attributes and implement the three capabilities.
    `verify` and freshness derivation are reserved for a later rebuild.
    """

    name: ClassVar[str]
    provider: ClassVar[str]
    materializable: ClassVar[bool]

    @abstractmethod
    def read_auth_data(self, home: Path) -> AuthData | None:
        """Read the credential present in a home/source, or None if absent."""

    @abstractmethod
    def extract_identity(self, auth_data: AuthData) -> AccountIdentity | None:
        """Extract the `Account.Identity` from a credential, or None if not recognizable."""

    @abstractmethod
    def materialize(self, auth_data: AuthData, home: Path) -> None:
        """Write a credential's `Auth.Data` into a home. Pure write — no read-back/sync/promote."""


__all__ = ["AuthData", "AuthMethod"]
