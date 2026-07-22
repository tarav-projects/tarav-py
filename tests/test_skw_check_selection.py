"""skw check selection over POI kinds via the shared skwlint core (Impl.Req 702 port)."""

import argparse
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.skwlint import check_registry, check_selector, poi, resolve_enabled_checks
from agentos.skillware.commands import (
    _cmd_skillware_check,
    _enabled_poi_selectors,
    _filter_pois,
    _skw_check_kinds,
)


def test_core_selector_maps_bare_kebab_kind_to_itself() -> None:
    assert check_selector("derived-stale") == "derived-stale"
    assert check_selector("undeclared-dependency") == "undeclared-dependency"


def test_skw_kinds_mark_hard_gating_kinds_structural() -> None:
    rows = {r["selector"]: r for r in check_registry(_skw_check_kinds())}
    assert rows["parse-error"]["structural"] is True
    assert rows["unresolvable"]["structural"] is True
    assert rows["derived-stale"]["structural"] is False
    assert rows["derived-stale"]["default_on"] is True


def _fake_pois():
    return [
        poi("derived-stale", Path("a"), "X", "h", "stale"),
        poi("undeclared-dependency", Path("a"), "Y", "h", "undeclared"),
        poi("parse-error", Path("a"), None, "h", "bad"),
    ]


def _kinds_args(**over):
    base = dict(check=[], skip=[])
    base.update(over)
    return argparse.Namespace(**base)


def test_filter_excludes_a_reportable_kind() -> None:
    enabled, known = _enabled_poi_selectors(_kinds_args(skip=["derived-stale"]))
    kept = {p.kind for p in _filter_pois(_fake_pois(), enabled, known)}
    assert "derived-stale" not in kept
    assert "undeclared-dependency" in kept


def test_filter_cannot_exclude_a_structural_kind() -> None:
    enabled, known = _enabled_poi_selectors(_kinds_args(skip=["parse-error"]))
    kept = {p.kind for p in _filter_pois(_fake_pois(), enabled, known)}
    assert "parse-error" in kept  # structural: always shown


def test_filter_keeps_unknown_kind_not_in_registry() -> None:
    enabled, known = _enabled_poi_selectors(_kinds_args())
    extra = _fake_pois() + [poi("mystery-kind", Path("a"), None, "h", "?")]
    kept = {p.kind for p in _filter_pois(extra, enabled, known)}
    assert "mystery-kind" in kept  # never silently hidden


def test_unknown_selector_is_an_error() -> None:
    with pytest.raises(CliError):
        _enabled_poi_selectors(_kinds_args(skip=["does-not-exist"]))


def test_list_checks_lists_kinds_and_exits(capsys) -> None:
    args = argparse.Namespace(skill=None, json=False, check=[], skip=[], list_checks=True)
    exit_code = _cmd_skillware_check(args)
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "derived-stale" in out
    assert "parse-error" in out and "structural" in out
