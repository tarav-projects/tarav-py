"""Strict file-level Annotation.Point policy for configured skw-code surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from agentos.skillware.build import check_project

HEADER = "# $kw: ^mod --note [DF] the module ^c20260722-21u\n"


def _project(root: Path, files: dict[str, str]) -> Path:
    (root / ".agentos").mkdir()
    (root / ".agentos" / "project.json").write_text("{}", encoding="utf-8")
    (root / ".skw").mkdir()
    (root / ".skw" / "skw.json").write_text(
        json.dumps(
            {
                "code_surfaces": [
                    {"language": "python", "include": ["src/**/*.py"]}
                ]
            }
        ),
        encoding="utf-8",
    )
    for relative, code in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
    return root


def _kinds(report, kind: str):
    return [poi for poi in report.code.pois if poi.kind == kind]


def test_line1_header_has_no_attachment_policy_pois(tmp_path: Path) -> None:
    project = _project(tmp_path, {"src/mod.py": HEADER + "x = 1\n"})
    report = check_project(project)
    assert not _kinds(report, "missing-header")
    assert not _kinds(report, "illegal-attachment")


def test_configured_unannotated_file_has_missing_header(tmp_path: Path) -> None:
    project = _project(tmp_path, {"src/mod.py": "x = 1\n"})
    missing = _kinds(check_project(project), "missing-header")
    assert len(missing) == 1
    assert missing[0].target_path == Path("src/mod.py")
    assert missing[0].key == "file"


def test_midfile_only_block_is_missing_header_and_illegal(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {"src/mod.py": "x = 1\n# $kw: --from Design.Thing\ny = 2\n"},
    )
    report = check_project(project)
    assert len(_kinds(report, "missing-header")) == 1
    assert [poi.key for poi in _kinds(report, "illegal-attachment")] == ["line 2"]


def test_second_block_is_illegal_but_header_present(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {"src/mod.py": HEADER + "x = 1\n# $kw: --from Design.Thing\ny = 2\n"},
    )
    report = check_project(project)
    assert not _kinds(report, "missing-header")
    assert [poi.key for poi in _kinds(report, "illegal-attachment")] == ["line 3"]


def test_kw_inside_string_does_not_make_a_header(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        {"src/mod.py": 'HELP = "wrap it as # $kw: --note"\nx = 1\n'},
    )
    report = check_project(project)
    assert len(_kinds(report, "missing-header")) == 1
    assert not _kinds(report, "illegal-attachment")
    assert not _kinds(report, "non-skw-annotation")


def test_kw_line_inside_multiline_string_does_not_make_a_header(
    tmp_path: Path,
) -> None:
    project = _project(
        tmp_path,
        {"src/mod.py": 'HELP = """\n# $kw: --note fake\n"""\n'},
    )
    report = check_project(project)
    assert len(_kinds(report, "missing-header")) == 1
    assert not _kinds(report, "illegal-attachment")
