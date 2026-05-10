"""Index doctor — health checks for notes/index/."""

from __future__ import annotations

import json
from pathlib import Path

from agentos._core.scan import resolve_root_dir, resolve_targets_under_root
from agentos.mdblocks.core import (
    MarkdownScanConfig,
    lint_markdown_blocks,
    scan_markdown_blocks,
    HARD_MAX_BLOCK_LINES,
)


def _find_index_dir(root: Path) -> Path | None:
    """Locate the notes/index/ directory relative to root."""
    candidate = root / "notes" / "index"
    return candidate if candidate.is_dir() else None


def _check_reserved_files(index_dir: Path) -> list[dict[str, object]]:
    """Check that reserved index files exist."""
    issues: list[dict[str, object]] = []
    for name, role in [
        ("000-index.md", "file-organization entry point"),
        ("001-ontology.md", "ontological entry point (symbol table)"),
    ]:
        path = index_dir / name
        if not path.exists():
            issues.append({
                "severity": "error",
                "code": "missing-reserved-file",
                "path": name,
                "message": f"Reserved file `{name}` ({role}) is missing.",
            })
        elif path.stat().st_size == 0:
            issues.append({
                "severity": "warning",
                "code": "empty-reserved-file",
                "path": name,
                "message": f"Reserved file `{name}` exists but is empty.",
            })
    return issues


def _check_separator_coverage(index_dir: Path, root: Path) -> list[dict[str, object]]:
    """Check that all index notes use **** separators between H2 blocks."""
    issues: list[dict[str, object]] = []

    md_files = sorted(index_dir.glob("*.md"))
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        lines = text.splitlines()

        h2_count = sum(1 for line in lines if line.startswith("## "))
        has_separator = "****" in text

        if h2_count > 1 and not has_separator:
            rel_path = str(md_file.relative_to(root))
            issues.append({
                "severity": "warning",
                "code": "missing-separators",
                "path": rel_path,
                "message": (
                    f"File has {h2_count} H2 headings but no `****` separators. "
                    f"Index notes require separators between H2-level blocks."
                ),
            })

    return issues


def run_doctor(
    root: Path,
    *,
    emit_json: bool = False,
) -> dict[str, object]:
    """Run index doctor checks and return a structured report."""
    root = resolve_root_dir(root)
    index_dir = _find_index_dir(root)

    report: dict[str, object] = {
        "root": str(root),
        "index_dir": str(index_dir) if index_dir else None,
    }

    if index_dir is None:
        report["status"] = "error"
        report["message"] = "No notes/index/ directory found."
        report["issues"] = []
        report["issue_count"] = 0
        return report

    all_issues: list[dict[str, object]] = []

    # 1. Reserved files check
    all_issues.extend(_check_reserved_files(index_dir))

    # 2. Separator coverage check
    all_issues.extend(_check_separator_coverage(index_dir, root))

    # 3. Run mdblocks lint on index notes
    targets = resolve_targets_under_root(root, [str(index_dir.relative_to(root))])
    lint_config = MarkdownScanConfig(
        root=root,
        targets=targets,
        excludes=(),
        min_level=2,
        max_level=6,
        start_line=None,
        end_line=None,
        recursive=True,
        include_content=False,
    )
    lint_result = lint_markdown_blocks(config=lint_config)

    # Extract lint issues into our format
    for file_report in lint_result.get("files", []):
        for issue in file_report.get("issues", []):
            all_issues.append({
                "severity": issue["severity"],
                "code": f"lint-{issue['code']}",
                "path": issue["path"],
                "message": issue["message"],
            })

    error_count = sum(1 for i in all_issues if i["severity"] == "error")
    warning_count = sum(1 for i in all_issues if i["severity"] == "warning")

    report["status"] = "ok" if error_count == 0 else "unhealthy"
    report["issues"] = all_issues
    report["issue_count"] = len(all_issues)
    report["error_count"] = error_count
    report["warning_count"] = warning_count
    report["file_count"] = len(list(index_dir.glob("*.md")))

    return report
