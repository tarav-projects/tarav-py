from __future__ import annotations

from pathlib import Path

from tarav.anchory import AnchoryDepot
from tarav.anchory.poi import ANCHORY_POI_CODES, build_anchory_linter_report
from tarav.poi.adapters.mdblocks import (
    MDBLOCKS_POI_CODES,
    build_mdblocks_linter_report,
)
from tarav.skillware.managed_blocks import create_tarav_wayfinder


def test_anchory_check_adapts_existing_findings_to_common_pois(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TARAV_WAYFINDER_REGISTRY", str(tmp_path / "wayfinder.json"))
    depot = AnchoryDepot(tmp_path / "anchory")
    shard = depot.root / "global" / "00.json"
    shard.parent.mkdir(parents=True)
    shard.write_text("{", encoding="utf-8")

    result = depot.check()
    report = build_anchory_linter_report(result, depot=depot.root)
    payload = report.as_dict()

    assert set(ANCHORY_POI_CODES) >= {finding.code for finding in result.findings}
    assert payload["pois"][0]["class"]["address"] == "Anchory.Linter/Json.Invalid"
    assert payload["domain"]["status"] == "error"
    assert "findings" not in payload


def test_mdblocks_report_preserves_counts_without_duplicate_issue_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TARAV_WAYFINDER_REGISTRY", str(tmp_path / "wayfinder.json"))
    payload = {
        "root": str(tmp_path),
        "file_count": 1,
        "issue_count": 1,
        "error_count": 1,
        "warning_count": 0,
        "files": [
            {
                "path": "bad.md",
                "issue_count": 1,
                "error_count": 1,
                "warning_count": 0,
                "issues": [],
            }
        ],
        "issues": [
            {
                "severity": "error",
                "code": "unclosed_code_fence",
                "path": "bad.md",
                "line": 3,
                "path_line": "bad.md:3",
                "message": "File appears to contain an unclosed fenced code block.",
            }
        ],
    }

    report = build_mdblocks_linter_report(
        payload,
        wayfinder=create_tarav_wayfinder(),
    )
    result = report.as_dict()

    assert set(MDBLOCKS_POI_CODES) >= {"unclosed_code_fence"}
    assert result["pois"][0]["class"]["address"] == (
        "Markdown.Block.Linter/CodeFence.Unclosed"
    )
    assert result["summary"]["error_count"] == 1
    assert "issues" not in result
    assert "issues" not in result["domain"]["files"][0]
