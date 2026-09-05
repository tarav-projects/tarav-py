# $kw: ^test-tournament-components --from Match.Component.Registry --note [DC] a component is written under the hash of its own content, and writing one already present is a no-op ^<anchor-on-landing>
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tarav.tournament.components import (
    ComponentMissingError,
    ComponentRegistry,
    address_of,
)
from tarav.tournament.model import TournamentError


def test_a_component_round_trips_through_its_address(tmp_path: Path) -> None:
    registry = ComponentRegistry(tmp_path)
    address = registry.put(b"- [CT] a line")
    assert registry.get(address) == b"- [CT] a line"
    assert registry.has(address)


def test_identical_content_yields_one_address_and_one_file(tmp_path: Path) -> None:
    registry = ComponentRegistry(tmp_path)
    first = registry.put(b"same")
    second = registry.put(b"same")
    assert first == second
    assert len(list(registry.root.rglob("*"))) == 2  # one shard dir, one file


def test_a_repeat_put_does_not_rewrite_the_file(tmp_path: Path) -> None:
    """No-op means no-op: the bytes on disk are already the answer."""
    registry = ComponentRegistry(tmp_path)
    address = registry.put(b"once")
    path = registry.path_for(address)
    before = path.stat().st_mtime_ns
    registry.put(b"once")
    assert path.stat().st_mtime_ns == before


def test_a_missing_component_names_the_address(tmp_path: Path) -> None:
    registry = ComponentRegistry(tmp_path)
    address = address_of(b"never stored")
    with pytest.raises(ComponentMissingError) as excinfo:
        registry.get(address)
    assert address in str(excinfo.value)
    assert not registry.has(address)


def test_concurrent_writers_of_one_component_leave_one_file(tmp_path: Path) -> None:
    """run_pool fans out over threads and they share this registry."""
    registry = ComponentRegistry(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        addresses = set(pool.map(lambda _: registry.put(b"contended"), range(64)))
    assert len(addresses) == 1
    assert len(list(registry.root.rglob("*.tmp"))) == 0
    assert registry.get(addresses.pop()) == b"contended"


def test_a_malformed_address_is_refused(tmp_path: Path) -> None:
    registry = ComponentRegistry(tmp_path)
    for bad in ("nope", "sha256:", "sha256:zz", "md5:" + "a" * 64):
        with pytest.raises(TournamentError):
            registry.path_for(bad)


def test_the_registry_lives_under_the_depot_root(tmp_path: Path) -> None:
    registry = ComponentRegistry(tmp_path)
    assert registry.root == tmp_path.resolve() / "components"
