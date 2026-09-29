# $kw: --from Account.Management --from Provider.Instance
"""The `Auth.Method` provider seam.

`Account.Model::Auth.Method` is an independent authentication method of an account
— a credential class that knows how to read/serialize its `Auth.Data`, extract the
`Account.Identity` that binds it to an account, and materialize it into a home.

This module holds the provider-agnostic abstraction only. Provider subclasses
(codex/claude/copilot) live with their provider packages and are wired in during
the per-provider cutover. See the `Account.Management` appendix in `tarav-pkg`.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from tarav.l1.agent.account_status import AccountIdentity


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
    `verify` is reserved for a later rebuild.
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

    @abstractmethod
    def ref_id(self, auth_data: AuthData) -> str:
        """The `Auth.Ref` id — the stable pointer the registry activates.

        Unique per credential-version of an ``account/method``; the method defines
        it (there is no inherited default). Artifact-backed methods return the
        `Auth.Data` content id, so the ref doubles as the stored artifact key."""

    def rotation_rank(self, auth_data: AuthData, captured_at: float) -> float | None:
        """The head-of-line key for rotation — higher means "should be active".

        Read only from registry-resident data: the stored `Auth.Data` payload and
        the artifact's capture time (epoch seconds). The default ranks by capture
        time; providers override with a payload date (e.g. token expiry). Return
        None to opt this artifact out of automatic rotation (manual only)."""

        return captured_at


__all__ = ["AuthData", "AuthMethod"]
