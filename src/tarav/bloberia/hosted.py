"""The hosted Tarav.Bloberia registry."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.persistence import atomic_write_json, atomic_write_text
from tarav.l0._core.record_depot import OpaqueRecordDepot, RecordDepotError, TYPE_FILES


BLOBERIA_CLASS = "Tarav.Bloberia"
BLOBERIA_SCHEMA_VERSION = 1
BLOBERIA_DIRNAME = "bloberia"
BLOBERIA_DEFINITION_FILENAME = "bloberia.json"


class TaravBloberiaError(RuntimeError):
    pass


class TaravBloberiaNotInitializedError(TaravBloberiaError):
    pass


class InvalidTaravBloberiaInputError(TaravBloberiaError):
    pass


def default_tarav_bloberia_root() -> Path:
    return default_tarav_data_root() / BLOBERIA_DIRNAME


def _git_init(root: Path) -> None:
    result = subprocess.run(
        ("git", "-C", str(root), "init", "-q"),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or "git init failed"
        raise TaravBloberiaError(
            f"Could not initialize Tarav.Bloberia repository: {detail}"
        )


@dataclass(frozen=True, slots=True)
class TaravBloberia:
    """One global Agent-managed registry of opaque JSON records."""

    root: Path
    _depot: OpaqueRecordDepot

    @classmethod
    def create(cls, root: Path | None = None) -> TaravBloberia:
        resolved = (root or default_tarav_bloberia_root()).expanduser().resolve()
        definition_path = resolved / BLOBERIA_DEFINITION_FILENAME
        if definition_path.is_file():
            return cls.open(resolved)
        if resolved.exists() and any(resolved.iterdir()):
            raise TaravBloberiaError(
                f"Tarav.Bloberia root is non-empty but not initialized: {resolved}"
            )

        resolved.mkdir(parents=True, exist_ok=True)
        _git_init(resolved)
        atomic_write_text(resolved / ".gitignore", ".record-depot.lock\n")
        atomic_write_json(
            definition_path,
            {
                "class": BLOBERIA_CLASS,
                "schema_version": BLOBERIA_SCHEMA_VERSION,
            },
        )
        depot = OpaqueRecordDepot(
            resolved,
            depot_type=TYPE_FILES,
            git=".",
            git_interval_seconds=0,
        ).initialize()
        return cls(root=resolved, _depot=depot)

    @classmethod
    def open(cls, root: Path | None = None) -> TaravBloberia:
        resolved = (root or default_tarav_bloberia_root()).expanduser().resolve()
        definition_path = resolved / BLOBERIA_DEFINITION_FILENAME
        if not definition_path.is_file() or not (resolved / ".git").is_dir():
            raise TaravBloberiaNotInitializedError(
                f"Tarav.Bloberia is not initialized: {resolved}"
            )
        try:
            definition = json.loads(definition_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TaravBloberiaError(
                f"Unreadable Tarav.Bloberia definition: {definition_path}"
            ) from exc
        if definition != {
            "class": BLOBERIA_CLASS,
            "schema_version": BLOBERIA_SCHEMA_VERSION,
        }:
            raise TaravBloberiaError(
                f"Unsupported Tarav.Bloberia definition: {definition_path}"
            )

        try:
            depot = OpaqueRecordDepot(
                resolved,
                depot_type=TYPE_FILES,
                git=".",
                git_interval_seconds=0,
            )
        except RecordDepotError as exc:
            raise TaravBloberiaError(str(exc)) from exc
        return cls(root=resolved, _depot=depot)

    def write(self, record: object) -> object:
        try:
            self._depot.insert(record)
        except RecordDepotError as exc:
            raise InvalidTaravBloberiaInputError(str(exc)) from exc
        return record

    def records(self) -> tuple[object, ...]:
        try:
            return tuple(self._depot.iterate())
        except RecordDepotError as exc:
            raise TaravBloberiaError(str(exc)) from exc

    def search(self, text: str) -> tuple[object, ...]:
        if not isinstance(text, str) or not text.strip():
            raise InvalidTaravBloberiaInputError(
                "Tarav.Bloberia search text must be non-empty"
            )
        needle = text.casefold()
        return tuple(
            record
            for record in self.records()
            if needle
            in json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).casefold()
        )


__all__ = [
    "BLOBERIA_CLASS",
    "BLOBERIA_SCHEMA_VERSION",
    "InvalidTaravBloberiaInputError",
    "TaravBloberia",
    "TaravBloberiaError",
    "TaravBloberiaNotInitializedError",
    "default_tarav_bloberia_root",
]
