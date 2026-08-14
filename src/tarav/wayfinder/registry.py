# $kw: ^wayfinder-registry --from Wayfinder.Registry --note [DF] locked global resolution memory with open relocation hints ^c20260729-46u
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from tarav._core.clock import utc_now_iso
from tarav._core.persistence import atomic_write_json
from tarav._core.project import tarav_home_dir

from .model import WayfinderError, WayfinderReferenceRoot


REGISTRY_SCHEMA = "tarav.wayfinder.registry.v1"


class CorruptWayfinderRegistry(WayfinderError):
    pass


@dataclass(frozen=True)
class WayfinderRegistration:
    root: WayfinderReferenceRoot
    path: Path
    verified_at: str
    relocation_hints: tuple[object, ...] = ()
    identity_evidence: object | None = None

    def as_dict(self) -> dict[str, object]:
        last_resolution: dict[str, object] = {
            "kind": "filesystem",
            "path": str(self.path),
            "verified_at": self.verified_at,
        }
        if self.identity_evidence is not None:
            last_resolution["identity_evidence"] = self.identity_evidence
        return {
            "root": self.root.as_dict(),
            "last_resolution": last_resolution,
            "relocation_hints": list(self.relocation_hints),
        }


@dataclass(frozen=True)
class WayfinderRegistryFinding:
    code: str
    message: str
    root: dict[str, str] | None = None
    path: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "root": self.root,
            "path": self.path,
        }


@dataclass(frozen=True)
class WayfinderRegistryCheck:
    findings: tuple[WayfinderRegistryFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "poi",
            "findings": [finding.as_dict() for finding in self.findings],
        }


class WayfinderRegistry:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        home: Path | None = None,
    ) -> None:
        override = os.getenv("TARAV_WAYFINDER_REGISTRY")
        if path is not None:
            selected = Path(path)
        elif override:
            selected = Path(override)
        else:
            selected = (home or tarav_home_dir()) / "wayfinder" / "registry.json"
        self.path = selected.expanduser().resolve()

    def entries(self) -> tuple[WayfinderRegistration, ...]:
        if not self.path.is_file():
            return ()
        with self._lock(exclusive=False):
            return self._read_unlocked()

    def get(self, root: WayfinderReferenceRoot) -> WayfinderRegistration | None:
        return next((entry for entry in self.entries() if entry.root == root), None)

    def register(
        self,
        root: WayfinderReferenceRoot,
        path: Path | str,
        *,
        relocation_hints: tuple[object, ...] = (),
        identity_evidence: object | None = None,
    ) -> WayfinderRegistration:
        resolved = Path(path).expanduser().resolve()
        _verify_root(root, resolved)
        hints = tuple(_normalize_json(hint) for hint in relocation_hints)
        evidence = (
            _normalize_json(identity_evidence)
            if identity_evidence is not None
            else None
        )
        registration = WayfinderRegistration(
            root=root,
            path=resolved,
            verified_at=utc_now_iso(),
            relocation_hints=hints,
            identity_evidence=evidence,
        )
        with self._lock(exclusive=True):
            entries = [
                entry for entry in self._read_unlocked() if entry.root != root
            ]
            entries.append(registration)
            entries.sort(key=lambda entry: entry.root.key)
            _write_json_atomic(
                self.path,
                {
                    "schema": REGISTRY_SCHEMA,
                    "entries": [entry.as_dict() for entry in entries],
                },
            )
        return registration

    def check(self) -> WayfinderRegistryCheck:
        try:
            entries = self.entries()
        except CorruptWayfinderRegistry as exc:
            return WayfinderRegistryCheck(
                findings=(
                    WayfinderRegistryFinding(
                        code="invalid-registry",
                        message=str(exc),
                        path=str(self.path),
                    ),
                )
            )
        findings: list[WayfinderRegistryFinding] = []
        for entry in entries:
            try:
                _verify_root(entry.root, entry.path)
            except WayfinderError as exc:
                findings.append(
                    WayfinderRegistryFinding(
                        code="stale-location",
                        message=str(exc),
                        root=entry.root.as_dict(),
                        path=str(entry.path),
                    )
                )
        return WayfinderRegistryCheck(findings=tuple(findings))

    def _read_unlocked(self) -> tuple[WayfinderRegistration, ...]:
        if not self.path.is_file():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorruptWayfinderRegistry(
                f"cannot read Wayfinder registry {self.path}: {exc}"
            ) from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "entries"}
            or payload.get("schema") != REGISTRY_SCHEMA
            or not isinstance(payload.get("entries"), list)
        ):
            raise CorruptWayfinderRegistry(
                f"invalid Wayfinder registry schema at {self.path}"
            )
        entries: list[WayfinderRegistration] = []
        seen: set[str] = set()
        for raw in payload["entries"]:
            entry = _registration_from_dict(raw, self.path)
            if entry.root.key in seen:
                raise CorruptWayfinderRegistry(
                    f"duplicate root registration: {entry.root.key}"
                )
            seen.add(entry.root.key)
            entries.append(entry)
        return tuple(entries)

    @contextmanager
    def _lock(self, *, exclusive: bool) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH,
            )
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _registration_from_dict(
    payload: object, registry_path: Path
) -> WayfinderRegistration:
    if not isinstance(payload, dict) or set(payload) != {
        "root",
        "last_resolution",
        "relocation_hints",
    }:
        raise CorruptWayfinderRegistry(
            f"invalid registration entry in {registry_path}"
        )
    last = payload["last_resolution"]
    if not isinstance(last, dict) or set(last) not in (
        {"kind", "path", "verified_at"},
        {"kind", "path", "verified_at", "identity_evidence"},
    ):
        raise CorruptWayfinderRegistry(
            f"invalid last_resolution entry in {registry_path}"
        )
    if (
        last.get("kind") != "filesystem"
        or not isinstance(last.get("path"), str)
        or not Path(last["path"]).is_absolute()
        or not isinstance(last.get("verified_at"), str)
        or not isinstance(payload["relocation_hints"], list)
    ):
        raise CorruptWayfinderRegistry(
            f"invalid filesystem registration in {registry_path}"
        )
    try:
        root = WayfinderReferenceRoot.from_dict(payload["root"])
        hints = tuple(_normalize_json(hint) for hint in payload["relocation_hints"])
        evidence = (
            _normalize_json(last["identity_evidence"])
            if "identity_evidence" in last
            else None
        )
    except WayfinderError as exc:
        raise CorruptWayfinderRegistry(str(exc)) from exc
    return WayfinderRegistration(
        root=root,
        path=Path(last["path"]),
        verified_at=last["verified_at"],
        relocation_hints=hints,
        identity_evidence=evidence,
    )


def _verify_root(root: WayfinderReferenceRoot, path: Path) -> None:
    if not path.is_dir():
        raise WayfinderError(f"registered root is not a reachable directory: {path}")
    if root.type in {"package.skill", "index.depot"} and not (
        path / "000-INDEX.md"
    ).is_file():
        raise WayfinderError(f"registered Index root has no 000-INDEX.md: {path}")


def _normalize_json(value: object) -> object:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise WayfinderError("registry metadata must be JSON-serializable") from exc


def _write_json_atomic(path: Path, payload: object) -> None:
    atomic_write_json(path, payload)


__all__ = [
    "CorruptWayfinderRegistry",
    "REGISTRY_SCHEMA",
    "WayfinderRegistration",
    "WayfinderRegistry",
    "WayfinderRegistryCheck",
    "WayfinderRegistryFinding",
]
