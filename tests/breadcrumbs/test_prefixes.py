"""Surfaces carry 12-character Breadcrumb prefixes; the registry keeps full IDs (request 918)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l1.breadcrumbs.store import (
    BreadcrumbAmbiguous,
    BreadcrumbError,
    BreadcrumbNotFound,
    BreadcrumbStore,
)

SHARED = "0123456789ab"
FIRST = SHARED + "c" + "0" * 51
SECOND = SHARED + "d0" + "1" * 50
THIRD = SHARED + "dd" + "2" * 50
ALONE = "fedcba987654" + "3" * 52


@pytest.fixture
def store(tmp_path: Path) -> BreadcrumbStore:
    store = BreadcrumbStore(tmp_path / "store")
    for breadcrumb_id in (FIRST, SECOND, THIRD, ALONE):
        store.create(breadcrumb_id)
    return store


def test_a_unique_prefix_finds_its_full_id(store: BreadcrumbStore) -> None:
    assert store.find("fedcba987654") == ALONE
    assert store.find(ALONE) == ALONE
    assert store.find(SHARED + "c") == FIRST
    assert store.find(SHARED + "d0") == SECOND
    assert store.find(SHARED + "dd") == THIRD


# tarav.breadcrumb 6123e20d5ea255adb67656414eda766897f7cc1aa3906d03de1d79cdfeba9df5
def test_a_shared_prefix_is_an_error_naming_every_candidate(store: BreadcrumbStore) -> None:
    with pytest.raises(BreadcrumbAmbiguous) as raised:
        store.find(SHARED)
    assert raised.value.prefix == SHARED
    assert raised.value.candidates == (FIRST, SECOND, THIRD)
    assert all(candidate in str(raised.value) for candidate in (FIRST, SECOND, THIRD))

    with pytest.raises(BreadcrumbAmbiguous) as raised:
        store.find(SHARED + "d")
    assert raised.value.candidates == (SECOND, THIRD)


def test_retained_data_never_selects_a_candidate(store: BreadcrumbStore, tmp_path: Path) -> None:
    surface = tmp_path / "note.md"
    surface.write_text(f"Text\n<!-- tarav.breadcrumb {SHARED} -->\n", encoding="utf-8")
    store.observe_position(FIRST, file=str(surface), line=2)
    store.attach(FIRST, {"type": "Tarav.Test.Attachment"})
    with pytest.raises(BreadcrumbAmbiguous):
        store.load(f"tarav.breadcrumb {SHARED}")


def test_no_match_and_malformed_prefixes(store: BreadcrumbStore) -> None:
    with pytest.raises(BreadcrumbNotFound, match="aaaaaaaaaaaa"):
        store.find("aaaaaaaaaaaa")
    for malformed in ("0123456789a", "0123456789AB", "x" * 12, SHARED + "0" * 53):
        with pytest.raises(BreadcrumbError, match="12 to 64"):
            store.find(malformed)


def test_labels_and_loads_take_prefixes(store: BreadcrumbStore) -> None:
    assert store.label(ALONE) == "tarav.breadcrumb fedcba987654"
    loaded = store.load("tarav.breadcrumb fedcba987654")
    assert loaded.records.to_record()["id"] == ALONE
    with pytest.raises(BreadcrumbAmbiguous) as raised:
        store.label(FIRST)
    assert raised.value.candidates == (FIRST, SECOND, THIRD)


def test_a_later_addition_makes_a_prefix_ambiguous(tmp_path: Path) -> None:
    store = BreadcrumbStore(tmp_path / "store")
    store.create(FIRST)
    assert store.find(SHARED) == FIRST
    store.create(SECOND)
    with pytest.raises(BreadcrumbAmbiguous):
        store.find(SHARED)
