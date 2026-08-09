# $kw: ^tournament-components --from Match.Component.Registry --from Tournament.Depot --note [DF] a Match.Component.Registry is the content-addressed store holding each distinct part a Match.Template names, once for a whole Tournament.Depot --supp ^c20260809-26u ^<anchor-on-landing>
"""The depot's content-addressed store of match parts.

Every part a ``Match.Template`` names — the brief, each player presentation, the
footnote template, and the template itself — is written under the hash of its own
bytes. Writing one already present is a no-op, so a player that meets a hundred
opponents has its presentation stored once.

The registry is depot-wide while ``definitions/``, ``records/``, and ``tickets/``
are per-tournament: dedup across tournaments is free and costs nothing to allow.

Writes are atomic. ``run_pool`` fans matches out over threads and several may
register the same component at once; content addressing makes that idempotent, but
a reader must still never observe a half-written file.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from agentos.tournament.depot import resolve_depot_root
from agentos.tournament.model import TournamentError

COMPONENTS_DIRNAME = "components"

ADDRESS_PREFIX = "sha256:"
# Two hex characters of shard prefix: 256 directories, which keeps a large depot
# off any one filesystem's per-directory limits without a deep tree.
SHARD_WIDTH = 2


class ComponentMissingError(TournamentError):
    """A named component is not in the registry."""


def address_of(data: bytes) -> str:
    return ADDRESS_PREFIX + hashlib.sha256(data).hexdigest()


class ComponentRegistry:
    """One depot's ``components/`` directory."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = resolve_depot_root(root) / COMPONENTS_DIRNAME

    def put(self, data: bytes) -> str:
        """Store one component and return its address; a repeat is a no-op."""
        address = address_of(data)
        path = self.path_for(address)
        if path.exists():
            return address
        path.parent.mkdir(parents=True, exist_ok=True)
        # Same directory, so the replace is atomic on every supported platform.
        # The temp name must be unique per writer rather than per content: threads
        # registering the same component race to the same final path deliberately,
        # and sharing a temp name would have one consume the other's file.
        temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
        return address

    def get(self, address: str) -> bytes:
        path = self.path_for(address)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise ComponentMissingError(
                f"match component not in this depot: {address}"
            ) from None

    def has(self, address: str) -> bool:
        return self.path_for(address).exists()

    def path_for(self, address: str) -> Path:
        digest = _digest(address)
        return self.root / digest[:SHARD_WIDTH] / digest


def _digest(address: str) -> str:
    if not isinstance(address, str) or not address.startswith(ADDRESS_PREFIX):
        raise TournamentError(
            f"a component address must start with {ADDRESS_PREFIX!r}: {address!r}"
        )
    digest = address[len(ADDRESS_PREFIX) :]
    if len(digest) != 64 or not all(char in "0123456789abcdef" for char in digest):
        raise TournamentError(f"malformed component address: {address!r}")
    return digest
