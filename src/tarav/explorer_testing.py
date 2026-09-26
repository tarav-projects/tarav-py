"""Reusable Explorer contract checks for Tarav and external workflows.

Concrete pytest classes inherit contract tests and implement abstract support.
Factories receive pytest's temporary directory; no registry or runner is needed.
No production Explorer operation depends on this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from tarav.kernel import (
    Explorer,
    ExplorerEntry,
    ExplorerFolder,
    ExplorerList,
    TaravObject,
)


ExplorerValue = ExplorerFolder | ExplorerList
Key = str | int


@dataclass(frozen=True)
class ExplorerCase:
    value: ExplorerValue
    keys: tuple[Key, ...]
    explorer: Explorer | None = None
    child: Key | None = None
    leaf: Key | None = None
    other_child: Key | None = None


class ExplorerContractTests(ABC):
    """Subclass as TestSomething; pytest discovers the inherited test methods.

    Use tmp_path for disposable storage. Implementations requiring additional
    resources can use autouse pytest fixtures with yield/finally teardown.
    This module itself does not import pytest.
    """

    @abstractmethod
    def make_case(self, tmp_path: Path) -> ExplorerCase:
        """Build isolated objects with known contents."""

    @abstractmethod
    def assert_value(self, case: ExplorerCase, key: Key, value: TaravObject) -> None:
        """Check against fixture expectations, not another call to open()."""

    def test_collection_contract(self, tmp_path: Path) -> None:
        case = self.make_case(tmp_path)
        check_collection(case.value, case.keys)
        for entry in case.value.ls():
            key = entry.name if isinstance(case.value, ExplorerFolder) else int(entry.name)
            self.assert_value(case, key, entry.open())
        for key in case.keys:
            self.assert_value(case, key, case.value.get(key).open())
            self.assert_value(case, key, case.value.open(key))

    def test_navigation_contract(self, tmp_path: Path) -> None:
        case = self.make_case(tmp_path)
        assert case.explorer is not None, "Navigation fixture must supply an explorer"
        for key in case.keys:
            before = navigation_state(case.explorer)
            self.assert_value(case, key, case.explorer.open(key))
            assert navigation_state(case.explorer) == before
        check_navigation(case)


def navigation_state(explorer: Explorer) -> tuple:
    """Snapshot shared Explorer state without requiring location equality."""
    return (
        id(explorer.current),
        tuple(map(id, explorer._back_stack)),
        tuple(map(id, explorer._forward_stack)),
        explorer.pwd(),
    )


def check_collection(value: ExplorerValue, keys: tuple[Key, ...]) -> None:
    """Check listing, selection, and opening without workflow assumptions."""

    entries = value.ls()
    assert isinstance(entries, tuple)
    assert len(entries) == len(keys)
    names = tuple(entry.name for entry in entries)
    expected = tuple(str(key) for key in keys)
    if isinstance(value, ExplorerFolder):
        assert set(names) == set(expected)
    else:
        assert names == expected
    for key in keys:
        listed = next(entry for entry in entries if entry.name == str(key))
        assert isinstance(listed, ExplorerEntry)
        selected = value.get(key)
        assert selected.name == listed.name
        assert isinstance(listed.open(), TaravObject)
        assert type(value.open(key)) is type(selected.open())
    missing: Key = "missing" if isinstance(value, ExplorerFolder) else len(keys)
    wrong_type: Key = 0 if isinstance(value, ExplorerFolder) else "0"
    try:
        value.get(wrong_type)
    except TypeError:
        pass
    else:
        raise AssertionError("get() accepted the wrong key type")
    try:
        value.get(missing)
    except (KeyError, IndexError):
        pass
    else:
        raise AssertionError("get() accepted a missing placement")


def check_navigation(case: ExplorerCase) -> None:
    """Check read neutrality, leaf rejection, history, and branching."""

    explorer = case.explorer
    assert explorer is not None
    start = explorer.pwd()
    before = navigation_state(explorer)
    listed_names = tuple(entry.name for entry in explorer.ls())
    expected_names = tuple(str(key) for key in case.keys)
    if isinstance(case.value, ExplorerFolder):
        assert set(listed_names) == set(expected_names)
    else:
        assert listed_names == expected_names
    for key in case.keys:
        assert explorer.get(key).name == str(key)
        assert isinstance(explorer.open(key), TaravObject)
    assert explorer.pwd() == start
    assert navigation_state(explorer) == before
    if case.leaf is not None:
        try:
            explorer.cd(case.leaf)
        except NotADirectoryError:
            pass
        else:
            raise AssertionError("cd() accepted a non-navigable leaf")
        assert explorer.pwd() == start
        assert navigation_state(explorer) == before
    if case.child is None:
        return
    explorer.cd(case.child)
    child_path = explorer.pwd()
    assert child_path != start
    explorer.back()
    assert explorer.pwd() == start
    before_reads = navigation_state(explorer)
    explorer.ls()
    for key in case.keys:
        explorer.get(key)
        explorer.open(key)
    assert navigation_state(explorer) == before_reads
    explorer.forward()
    assert explorer.pwd() == child_path
    explorer.back()
    if case.other_child is not None:
        explorer.cd(case.other_child)
        branch_path = explorer.pwd()
        assert branch_path != child_path
        explorer.forward()
        assert explorer.pwd() == branch_path


__all__ = [
    "ExplorerCase",
    "ExplorerContractTests",
    "check_collection",
    "check_navigation",
]
