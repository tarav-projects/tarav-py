from __future__ import annotations

from pathlib import Path

from tarav.anchory import AnchoryDepot
from tarav.anchory.poi import ANCHORY_POI_CODES, build_anchory_linter_report
from tarav.bloberia.core import BloberiaDepot
from tarav.skillware.managed_blocks import create_tarav_wayfinder
from tarav.poi.adapters.bloberia import (
    BLOBERIA_POI_CODES,
    bloberia_finding_to_poi,
    build_bloberia_linter_report,
)
from tarav.poi import build_poi_report, tarav_poi_class_reference
from tarav.bloberia.core import BloberiaCheckFinding
from tarav.poi.adapters.mdblocks import (
    MDBLOCKS_POI_CODES,
    build_mdblocks_linter_report,
)


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


def test_bloberia_check_adapts_existing_findings_to_common_pois(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TARAV_WAYFINDER_REGISTRY", str(tmp_path / "wayfinder.json"))
    depot = BloberiaDepot(tmp_path / "bloberia")
    record = depot.root / "records" / "invalid.json"
    record.parent.mkdir(parents=True)
    record.write_text("{", encoding="utf-8")

    result = depot.check()
    report = build_bloberia_linter_report(
        result,
        depot=depot.root,
        wayfinder=create_tarav_wayfinder(),
    )
    payload = report.as_dict()

    assert set(BLOBERIA_POI_CODES) >= {finding.code for finding in result.findings}
    assert payload["pois"][0]["class"]["address"].startswith("Bloberia.Linter/")
    assert payload["summary"]["poi_count"] == len(result.findings)
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


def test_real_finding_resolves_to_its_annotated_check_without_catalog() -> None:
    finding = BloberiaCheckFinding(
        code="invalid-json",
        path="records/bad.json",
        message="invalid JSON",
    )
    instance = bloberia_finding_to_poi(finding)
    report = build_poi_report(
        (instance,),
        wayfinder=create_tarav_wayfinder(
            project_root=Path(__file__).resolve().parents[1]
        ),
    )

    group = report.groups[0]
    assert group.reference.type == "managed.block"
    assert group.documentation.target["host"] == {
        "kind": "function",
        "name": "_invalid_json",
    }
    assert "def _invalid_json" in group.documentation.target["content"]


def test_index_poi_classes_resolve_to_their_emitting_code() -> None:
    wayfinder = create_tarav_wayfinder(
        project_root=Path(__file__).resolve().parents[1]
    )
    expected_hosts = {
        "Index.Linter/Gate.Evidence.Invalid": "_gate_evidence_invalid_finding",
        "Index.Linter/Gate.Evidence.Unavailable": (
            "_gate_evidence_unavailable_finding"
        ),
        "Index.Linter/Support.Unresolved": "_support_unresolved_finding",
        "Index.Linter/Support.Unreachable": "_support_unreachable_finding",
        "Index.Linter/Trace.Forked": "_trace_forked_finding",
    }

    for poi_class, function_name in expected_hosts.items():
        resolved = wayfinder.resolve(tarav_poi_class_reference(poi_class))
        assert resolved.target["host"] == {
            "kind": "function",
            "name": function_name,
        }
