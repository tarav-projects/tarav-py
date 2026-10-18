"""Indexed conversation navigation, independent of Model availability.

Folder keys are native session IDs by default. Use ``key_by="identity_hash"``
for a globally unambiguous listing, or scope native IDs by provider/instance.
Neither listing nor opening a Session captures or normalizes provider data.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from tarav.l0.kernel import (
    ExplorerEntry,
    ExplorerFolder,
    TaravClass,
    TaravObject,
    TypeShip,
)
from tarav.l1.chatlas.identity import CHATLAS_WORKFLOW_SHIP
from tarav.l1.chatlas.index_store import load_chatlas_session_index_rows
from tarav.l1.chatlas.normal_model import (
    ChatlasNormalModel,
    provide_normal_model_reader,
)
from tarav.l1.chatlas.normal_model_cache import PARTS, NormalModelCache
from tarav.l1.chatlas.paths import default_chatlas_root
from tarav.l1.chatlas.session_identity import session_identity_hash
from tarav.l1.chatlas.session_resolver import (
    ChatlasSessionAmbiguous,
    resolve_session_index_row,
)
from tarav.l0.kernel import LoadedRecord


class ChatSession(TaravObject):
    """A portable conversation selector with a runtime-bound retained depot."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("348fab89-7c1d-46b7-87aa-d690d2447651"),
            name="Chatlas.Session",
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        provider: str = Field(min_length=1)
        instance: str = Field(min_length=1)
        session_id: str = Field(min_length=1)
        identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

        @model_validator(mode="after")
        def check_identity(self) -> Self:
            expected = session_identity_hash(
                provider=self.provider,
                instance=self.instance,
                session_id=self.session_id,
            )
            if self.identity_hash != expected:
                raise ValueError("Session identity_hash does not match its selector")
            return self

    def __init__(
        self,
        *,
        provider: str,
        instance: str,
        session_id: str,
        identity_hash: str | None = None,
        chatlas_root: Path | None = None,
    ) -> None:
        super().__init__()
        selector = self.RecordInterface.model_validate(
            {
                "provider": provider,
                "instance": instance,
                "session_id": session_id,
                "identity_hash": identity_hash
                if identity_hash is not None
                else session_identity_hash(
                    provider=provider, instance=instance, session_id=session_id
                ),
            }
        )
        self.provider = selector.provider
        self.instance = selector.instance
        self.session_id = selector.session_id
        self.identity_hash = selector.identity_hash
        self.bind_root(
            chatlas_root if chatlas_root is not None else default_chatlas_root()
        )

    def bind_root(self, chatlas_root: Path) -> Self:
        """Explicitly select runtime storage; the root is never part of the Record."""
        self.chatlas_root = chatlas_root.expanduser().resolve()
        return self

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls(
            provider=loaded.data.provider,
            instance=loaded.data.instance,
            session_id=loaded.data.session_id,
            identity_hash=loaded.data.identity_hash,
        )

    def _to_record(self) -> dict[str, object]:
        return {
            **super()._to_record(),
            "provider": self.provider,
            "instance": self.instance,
            "session_id": self.session_id,
            "identity_hash": self.identity_hash,
        }

    class Records(TaravObject.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return cls(
                provider="codex", instance="example", session_id="example"
            ).records.to_record()


    def model(
        self, *, refresh: bool = False, parts: tuple[str, ...] = PARTS
    ) -> ChatlasNormalModel:
        """The cached Model when the requested parts are fresh, otherwise a new build."""
        return provide_normal_model_reader(
            provider=self.provider,
            instance=self.instance,
            session_id=self.session_id,
            identity_hash=self.identity_hash,
            chatlas_root=self.chatlas_root,
            refresh=refresh,
            parts=parts,
        )

    # tarav.breadcrumb d46b1b89319d
    def cache(self) -> NormalModelCache:
        """The cached parts and their standing, read or built without policy."""
        row = resolve_session_index_row(
            identity_hash=self.identity_hash,
            provider=self.provider,
            instance=self.instance,
            chatlas_root=self.chatlas_root,
        )
        return NormalModelCache(row, chatlas_root=self.chatlas_root)


class ChatSessionEntry(ExplorerEntry):
    """An indexed placement; opening constructs only the Session selector."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("c5ac8cae-a523-46a9-855c-2515ccf156b5"),
            name="Chatlas.Session.Entry",
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    def __init__(self, name: str, row: dict[str, Any], chatlas_root: Path) -> None:
        super().__init__()
        self._name = name
        self.metadata = dict(row)
        self.chatlas_root = chatlas_root

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self.metadata['provider']}:{self.metadata['session_id']} ({self.metadata['instance']})"

    def open(self) -> ChatSession:
        return ChatSession(
            provider=self.metadata["provider"],
            instance=self.metadata["instance"],
            session_id=self.metadata["session_id"],
            identity_hash=self.metadata["identity_hash"],
            chatlas_root=self.chatlas_root,
        )


class ChatSessions(ExplorerFolder):
    """Read-only view over the existing Session Index, with explicit key semantics."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("2cbb0996-a0a9-4c63-a2b4-2fb4c4c023a3"),
            name="Chatlas.Sessions",
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    def __init__(
        self,
        *,
        chatlas_root: Path | None = None,
        provider: str | None = None,
        instance: str | None = None,
        key_by: Literal["session_id", "identity_hash"] = "session_id",
    ) -> None:
        super().__init__()
        if key_by not in ("session_id", "identity_hash"):
            raise ValueError("Session keys must be session_id or identity_hash")
        self.chatlas_root = (
            (chatlas_root if chatlas_root is not None else default_chatlas_root())
            .expanduser()
            .resolve()
        )
        self.provider = provider
        self.instance = instance
        self.key_by = key_by

    def _entry(self, row: dict[str, Any]) -> ChatSessionEntry:
        return ChatSessionEntry(row[self.key_by], row, self.chatlas_root)

    def ls(self) -> tuple[ChatSessionEntry, ...]:
        index = load_chatlas_session_index_rows(
            chatlas_root=self.chatlas_root,
            providers=(self.provider,) if self.provider is not None else None,
        )
        rows = [
            row
            for row in index.rows
            if self.instance is None or row.get("instance") == self.instance
        ]
        if any(
            count > 1 for count in Counter(row[self.key_by] for row in rows).values()
        ):
            raise ChatlasSessionAmbiguous(
                "Session listing has duplicate keys; scope provider/instance or use key_by='identity_hash'"
            )
        return tuple(self._entry(row) for row in rows)

    def get(self, name: str) -> ChatSessionEntry:
        if not isinstance(name, str):
            raise TypeError("Session folder keys must be strings")
        if self.key_by == "identity_hash":
            return self.get_by_identity(identity_hash=name)
        row = resolve_session_index_row(
            session_id=name,
            provider=self.provider,
            instance=self.instance,
            chatlas_root=self.chatlas_root,
        )
        return self._entry(row)

    def get_by_identity(self, *, identity_hash: str) -> ChatSessionEntry:
        """Select an exact identity without guessing the meaning of a string."""
        if not isinstance(identity_hash, str):
            raise TypeError("Session identity_hash must be a string")
        row = resolve_session_index_row(
            identity_hash=identity_hash,
            provider=self.provider,
            instance=self.instance,
            chatlas_root=self.chatlas_root,
        )
        return self._entry(row)


__all__ = ["ChatSession", "ChatSessionEntry", "ChatSessions"]
