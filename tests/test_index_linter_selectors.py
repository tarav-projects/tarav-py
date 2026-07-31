from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos.index.commands import _cmd_linter
from agentos.index.linter import (
    GateResult,
    LinterCheck,
)
from _index_linter_helpers import _clean_depot, _run, _write


def test_check_selector_derives_stable_kebab_slugs() -> None:
    from agentos.index.linter import check_selector

    assert (
        check_selector("Index.Linter/Check.DepotDependencies") == "depot-dependencies"
    )
    assert check_selector("Index.Linter/Line.Unlinked") == "line-unlinked"
    assert check_selector("Index.Linter/Check.ConfigSurfaces") == "config-surfaces"


def test_all_check_selectors_are_unique() -> None:
    from agentos.index.linter import CHECKS, check_selector

    selectors = [check_selector(c.code) for c in CHECKS]
    assert len(selectors) == len(set(selectors)), "check selectors must be unique"


def test_check_registry_reports_metadata() -> None:
    from agentos.index.linter import check_registry

    rows = {row["selector"]: row for row in check_registry()}
    assert "config-surfaces" in rows
    assert rows["config-surfaces"]["structural"] is True
    # a reportable, opt-in check registered off by default
    assert rows["dangling-mention"]["default_on"] is False


def _fake_checks():
    from agentos.index.linter import LinterCheck

    def _noop(state):
        return []

    def _ok(state):
        from agentos.index.linter import allowed

        return allowed()

    return (
        LinterCheck("S/Check.Structural", "structural", _ok, _noop, structural=True),
        LinterCheck("S/Check.OnByDefault", "on", _ok, _noop, default_on=True),
        LinterCheck("S/Check.OffByDefault", "off", _ok, _noop, default_on=False),
    )


def test_resolver_default_runs_default_on_only():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {check_selector(c.code) for c in resolve_enabled_checks(_fake_checks())}
    assert enabled == {"structural", "on-by-default"}


def test_resolver_include_enables_a_default_off_check():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {
        check_selector(c.code)
        for c in resolve_enabled_checks(_fake_checks(), include=("off-by-default",))
    }
    assert "off-by-default" in enabled


def test_resolver_exclude_removes_reportable_but_not_structural():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {
        check_selector(c.code)
        for c in resolve_enabled_checks(
            _fake_checks(), exclude=("on-by-default", "structural")
        )
    }
    assert "on-by-default" not in enabled
    assert "structural" in enabled  # structural is never disableable


def test_resolver_skip_wins_on_conflict():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {
        check_selector(c.code)
        for c in resolve_enabled_checks(
            _fake_checks(), include=("off-by-default",), exclude=("off-by-default",)
        )
    }
    assert "off-by-default" not in enabled


def test_resolver_unknown_selector_errors():
    import pytest

    from agentos._core.errors import CliError
    from agentos.index.linter import resolve_enabled_checks

    with pytest.raises(CliError):
        resolve_enabled_checks(_fake_checks(), include=("nope",))


def test_run_linter_exclude_skips_a_reportable_check(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import CHECK_CONCEPT_DUPLICATES

    monkeypatch.chdir(tmp_path)
    depot = _clean_depot(tmp_path)
    ran = {r.code for r in _run(depot_paths=(str(depot),)).check_results}
    assert CHECK_CONCEPT_DUPLICATES in ran  # runs by default
    ran_excluded = {
        r.code
        for r in _run(
            depot_paths=(str(depot),), exclude=("concept-duplicates",)
        ).check_results
    }
    assert CHECK_CONCEPT_DUPLICATES not in ran_excluded


def test_run_linter_exclude_cannot_disable_a_structural_check(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import CHECK_CONFIG_SURFACES

    monkeypatch.chdir(tmp_path)
    depot = _clean_depot(tmp_path)
    ran = {
        r.code
        for r in _run(
            depot_paths=(str(depot),), exclude=("config-surfaces",)
        ).check_results
    }
    assert CHECK_CONFIG_SURFACES in ran  # structural: exclude has no effect


def test_dangling_mention_check_is_default_off_and_opt_in(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_DANGLING_MENTION

    monkeypatch.chdir(tmp_path)
    # a depot mentioning a concept whose block does not exist -> a dangling mention
    depot = tmp_path / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Present.Concept\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Present.Concept\n\n- [DF] `Present.Concept` leans on `Missing.Concept`\n****\n",
    )
    default_run = _run(depot_paths=(str(depot),))
    assert not [f for f in default_run.findings if f.code == DEPOT_DANGLING_MENTION]

    opted_in = _run(depot_paths=(str(depot),), include=("dangling-mention",))
    dangling = [f for f in opted_in.findings if f.code == DEPOT_DANGLING_MENTION]
    assert "Missing.Concept" in {f.details["concept"] for f in dangling}


def _linter_ns(**over):
    base = dict(
        depot=[],
        index=[],
        appendix=[],
        json=True,
        coverage=[],
        scope=[],
        warn_unlinked=False,
        check=[],
        skip=[],
        list_checks=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def test_cli_list_checks_lists_selectors_and_exits(capsys) -> None:
    exit_code = _cmd_linter(_linter_ns(list_checks=True))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "dangling-mention" in out and "[off]" in out
    assert "config-surfaces" in out and "structural" in out


def test_cli_list_checks_includes_composition_root_checks(capsys) -> None:
    extra = LinterCheck(
        code="Index.Linter/Line.Approval",
        title="external approval check",
        gate=lambda _state: GateResult(allowed=True),
        run=lambda _state: [],
        default_on=False,
    )
    exit_code = _cmd_linter(
        _linter_ns(
            list_checks=True,
            _extra_linter_checks=(extra,),
        )
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "line-approval" in out
    assert "external approval check" in out


def test_cli_check_flag_opts_into_dangling_mention(
    capsys, monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_DANGLING_MENTION

    monkeypatch.chdir(tmp_path)
    depot = tmp_path / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Present.Concept\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Present.Concept\n\n- [DF] `Present.Concept` leans on `Missing.Concept`\n****\n",
    )
    _cmd_linter(_linter_ns(depot=["depot"], check=["dangling-mention"]))
    payload = json.loads(capsys.readouterr().out)
    codes = {poi["class"]["address"] for poi in payload["pois"]}
    assert DEPOT_DANGLING_MENTION in codes


def test_cli_unknown_selector_is_an_error(monkeypatch, tmp_path: Path) -> None:
    import pytest

    from agentos._core.errors import CliError

    monkeypatch.chdir(tmp_path)
    _clean_depot(tmp_path)
    with pytest.raises(CliError):
        _cmd_linter(_linter_ns(depot=["depot"], skip=["does-not-exist"]))
