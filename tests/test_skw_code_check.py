"""Strict `Non.Skw.Annotation` checks over configured Python code surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from agentos.skillware.build import check_project


def _project(root: Path, code: str) -> Path:
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
    (root / "src").mkdir()
    (root / "src" / "mod.py").write_text(code, encoding="utf-8")
    return root


CODE = (
    "# $kw: ^retry --note [CT] broker can double-deliver ^c20260722-21u\n"
    "# a bare leading comment\n"
    "def send(msg):\n"
    "    value = '# inside a string'\n"
    "    return _do(msg)  # an inline comment\n"
)


def _non_skw(project: Path):
    return [
        poi
        for poi in check_project(project).code.pois
        if poi.kind == "non-skw-annotation"
    ]


def test_python_tokenizer_flags_full_line_and_inline_comments(tmp_path: Path) -> None:
    flagged = _non_skw(_project(tmp_path, CODE))
    assert [poi.key for poi in flagged] == ["line 2:1", "line 5:22"]
    assert [poi.evidence["identity_payload"] for poi in flagged] == [
        "# a bare leading comment",
        "# an inline comment",
    ]


def test_strict_policy_flags_shebang_directive_and_separator(tmp_path: Path) -> None:
    code = (
        "# $kw: ^module --note [DF] module ^c20260722-21u\n"
        "#!/usr/bin/env python3\n"
        "x = 1  # noqa\n"
        "# --------\n"
    )
    flagged = _non_skw(_project(tmp_path, code))
    assert [poi.evidence["identity_payload"] for poi in flagged] == [
        "#!/usr/bin/env python3",
        "# noqa",
        "# --------",
    ]


def test_python_scanner_failure_gates_code_policy_checks(tmp_path: Path) -> None:
    project = _project(
        tmp_path,
        "# $kw: ^module --note [DF] module ^c20260722-21u\nx = '''\n",
    )
    pois = check_project(project).code.pois
    assert [poi.kind for poi in pois] == ["parse-error"]
    assert "python scanner failed" in pois[0].detail


def test_non_skw_annotation_is_default_on(tmp_path: Path) -> None:
    from agentos.skillware.commands import (
        _enabled_poi_selectors,
        _filter_pois,
        _skw_check_kinds,
    )

    kind = next(kind for kind in _skw_check_kinds() if kind.code == "non-skw-annotation")
    assert kind.default_on is True

    project = _project(tmp_path, CODE)

    class _Args:
        check: list = []
        skip: list = []

    enabled, known = _enabled_poi_selectors(_Args())
    kept = _filter_pois(check_project(project).code.pois, enabled, known)
    assert len([poi for poi in kept if poi.kind == "non-skw-annotation"]) == 2


def test_comment_poi_identity_changes_with_content(tmp_path: Path) -> None:
    project = _project(tmp_path, CODE)
    before = _non_skw(project)[0]
    path = project / "src/mod.py"
    path.write_text(CODE.replace("bare leading", "changed leading"), encoding="utf-8")
    after = _non_skw(project)[0]
    assert after.poi_hash != before.poi_hash


def test_comment_poi_identity_changes_when_comment_moves(tmp_path: Path) -> None:
    project = _project(tmp_path, CODE)
    before = _non_skw(project)[0]
    path = project / "src/mod.py"
    path.write_text(CODE.replace("# a bare", "\n# a bare"), encoding="utf-8")
    after = _non_skw(project)[0]
    assert after.evidence["identity_payload"] == before.evidence["identity_payload"]
    assert after.poi_hash != before.poi_hash


def test_exact_project_blessing_suppresses_only_current_comment(tmp_path: Path) -> None:
    from agentos.skillware.build import bless_code_poi

    project = _project(tmp_path, CODE)
    before = _non_skw(project)
    bless_code_poi(project, before[0].poi_hash)
    assert [poi.poi_hash for poi in _non_skw(project)] == [before[1].poi_hash]

    path = project / "src/mod.py"
    path.write_text(CODE.replace("bare leading", "changed leading"), encoding="utf-8")
    assert len(_non_skw(project)) == 2
