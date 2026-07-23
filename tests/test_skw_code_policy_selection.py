"""Check-selection for the code policy POIs: default-on and skippable."""

from __future__ import annotations

from agentos.skillware.commands import _skw_check_kinds


def _kind(code):
    return next(k for k in _skw_check_kinds() if k.code == code)


def test_policy_kinds_are_default_on_reportable() -> None:
    for code in ("illegal-attachment", "missing-header"):
        k = _kind(code)
        assert k.default_on is True
        assert k.structural is False  # skippable, not always-on


def test_policy_kinds_are_skippable() -> None:
    from agentos.skwlint import check_selector, resolve_enabled_checks

    kinds = _skw_check_kinds()
    enabled = resolve_enabled_checks(kinds, include=(), exclude=("illegal-attachment",))
    selectors = {check_selector(k.code) for k in enabled}
    assert "illegal-attachment" not in selectors
    assert "missing-header" in selectors  # unaffected
