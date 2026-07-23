"""`Non.Skw.Annotation` check over skw-managed code surfaces (default-off)."""

from __future__ import annotations

import json
from pathlib import Path

from agentos.skillware.build import check_skill


def _managed_pkg(root: Path, code: str) -> Path:
    """A minimal skw package with an empty src and one .py code surface."""
    skill = root / "skill"
    (skill / ".skw" / "src").mkdir(parents=True)
    (skill / ".skw" / "skw.json").write_text(json.dumps({}), encoding="utf-8")
    (skill / "mod.py").write_text(code, encoding="utf-8")
    return skill


CODE = (
    "# $kw: ^retry --note [CT] broker can double-deliver ^c20260722-21u\n"
    "# a bare leading comment\n"
    "def send(msg):\n"
    "    # an inner bare comment\n"
    "    return _do(msg)\n"
)


def _kinds(pois):
    return [p.kind for p in pois]


def test_non_skw_annotation_flags_bare_comments_only(tmp_path: Path) -> None:
    skill = _managed_pkg(tmp_path, CODE)
    report = check_skill(skill)
    flagged = [p for p in report.pois if p.kind == "non-skw-annotation"]
    # exactly the two bare comments; the `# $kw:` machinery line is not flagged
    assert len(flagged) == 2
    keys = sorted(p.key for p in flagged)
    assert keys == ["line 2", "line 4"]


def test_unmanaged_code_surface_is_not_scanned(tmp_path: Path) -> None:
    # no `# $kw:` machinery anywhere → the file is not a managed surface
    skill = _managed_pkg(tmp_path, "# just a comment\nx = 1\n")
    report = check_skill(skill)
    assert not [p for p in report.pois if p.kind == "non-skw-annotation"]


def test_non_skw_annotation_is_default_off(tmp_path: Path) -> None:
    from agentos.skillware.commands import (
        _enabled_poi_selectors,
        _filter_pois,
        _skw_check_kinds,
    )

    kind = next(k for k in _skw_check_kinds() if k.code == "non-skw-annotation")
    assert kind.default_on is False

    skill = _managed_pkg(tmp_path, CODE)
    report = check_skill(skill)

    class _Args:
        check: list = []
        skip: list = []

    enabled, known = _enabled_poi_selectors(_Args())
    kept = _filter_pois(report.pois, enabled, known)
    assert not [p for p in kept if p.kind == "non-skw-annotation"]

    class _OptIn:
        check = ["non-skw-annotation"]
        skip: list = []

    enabled2, known2 = _enabled_poi_selectors(_OptIn())
    kept2 = _filter_pois(report.pois, enabled2, known2)
    assert len([p for p in kept2 if p.kind == "non-skw-annotation"]) == 2


def test_bless_clears_a_non_skw_annotation(tmp_path: Path) -> None:
    from agentos.skillware.build import bless_pois_by_kind

    skill = _managed_pkg(tmp_path, CODE)
    before = [p for p in check_skill(skill).pois if p.kind == "non-skw-annotation"]
    assert len(before) == 2
    bless_pois_by_kind(skill, "non-skw-annotation")
    after = [p for p in check_skill(skill).pois if p.kind == "non-skw-annotation"]
    assert not after
