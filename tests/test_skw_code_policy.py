"""File-level Annotation.Point policy for skw-code: illegal-attachment / missing-header."""

from __future__ import annotations

import json
from pathlib import Path

from agentos.skillware.build import check_skill

HEADER = "# $kw: ^mod --note [DF] the module ^c20260722-21u\n"


def _managed_pkg(root: Path, code: str) -> Path:
    skill = root / "skill"
    (skill / ".skw" / "src").mkdir(parents=True)
    (skill / ".skw" / "skw.json").write_text(json.dumps({}), encoding="utf-8")
    (skill / "mod.py").write_text(code, encoding="utf-8")
    return skill


def _kinds(report, kind):
    return [p for p in report.pois if p.kind == kind]


def test_line1_header_has_no_policy_pois(tmp_path: Path) -> None:
    skill = _managed_pkg(tmp_path, HEADER + "def f():\n    return 1\n")
    report = check_skill(skill)
    assert not _kinds(report, "missing-header")
    assert not _kinds(report, "illegal-attachment")


def test_midfile_only_block_is_missing_header_and_illegal(tmp_path: Path) -> None:
    # a managed file whose only annotation sits mid-file, no line-1 header
    code = "x = 1\n# $kw: --from Design.Thing\ndef f():\n    return 1\n"
    skill = _managed_pkg(tmp_path, code)
    report = check_skill(skill)
    assert len(_kinds(report, "missing-header")) == 1
    illegal = _kinds(report, "illegal-attachment")
    assert [p.key for p in illegal] == ["line 2"]


def test_second_block_is_illegal_but_header_present(tmp_path: Path) -> None:
    code = HEADER + "def f():\n    return 1\n# $kw: --from Design.Thing\ny = 2\n"
    skill = _managed_pkg(tmp_path, code)
    report = check_skill(skill)
    assert not _kinds(report, "missing-header")  # line-1 header present
    illegal = _kinds(report, "illegal-attachment")
    assert [p.key for p in illegal] == ["line 4"]


def test_mentions_kw_in_string_is_not_managed(tmp_path: Path) -> None:
    # a file that only *mentions* $kw in a string (no `# $kw:` machinery line)
    # is not a managed surface — no missing-header false positive
    code = 'HELP = "wrap it as # $kw: --note"\nx = 1\n'
    skill = _managed_pkg(tmp_path, code)
    report = check_skill(skill)
    assert not _kinds(report, "missing-header")
    assert not _kinds(report, "illegal-attachment")
    assert not _kinds(report, "non-skw-annotation")


def test_policy_configurable_not_required(tmp_path: Path) -> None:
    from agentos.skillware.build import CodeAttachPolicy, _code_surface_pois

    # a mid-file-only managed file, presence relaxed → no missing-header
    (tmp_path / "mod.py").write_text(
        "x = 1\n# $kw: --from Design.Thing\n", encoding="utf-8"
    )
    pois = _code_surface_pois(tmp_path, CodeAttachPolicy(file_required=False))
    assert not [p for p in pois if p.kind == "missing-header"]
    # the block is still off the file point → still illegal
    assert [p.key for p in pois if p.kind == "illegal-attachment"] == ["line 2"]
