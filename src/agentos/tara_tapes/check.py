from __future__ import annotations

import json
from pathlib import Path

from agentos.tara_tapes.core import (
    MANIFEST_FILENAME,
    SEGMENTS_DIRNAME,
    STAGE_DIRNAME,
    TARA_TAPE_SPEC_VERSION,
)


def check_tape(tape_path: Path) -> dict[str, object]:
    tape_path = tape_path.expanduser().resolve()
    issues: list[str] = []

    if not tape_path.is_dir():
        return {
            "tape_path": str(tape_path),
            "conformant": False,
            "issues": ["path is not a directory"],
        }

    manifest_path = tape_path / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {
            "tape_path": str(tape_path),
            "conformant": False,
            "issues": [f"missing {MANIFEST_FILENAME}"],
        }

    # Parse manifest
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "tape_path": str(tape_path),
            "conformant": False,
            "issues": [f"invalid {MANIFEST_FILENAME}: {exc}"],
        }

    if not isinstance(manifest, dict):
        issues.append(f"{MANIFEST_FILENAME} is not a JSON object")
    else:
        # Check required fields
        tape_name = manifest.get("tape_name")
        if not isinstance(tape_name, str) or not tape_name.strip():
            issues.append("missing or empty tape_name")

        spec_version = manifest.get("tara_tape_spec")
        if spec_version != TARA_TAPE_SPEC_VERSION:
            issues.append(
                f"tara_tape_spec is {spec_version!r}, expected {TARA_TAPE_SPEC_VERSION!r}"
            )

        created_at = manifest.get("created_at")
        if not isinstance(created_at, str) or not created_at.strip():
            issues.append("missing or empty created_at")

    # Check directory layout
    segments_dir = tape_path / SEGMENTS_DIRNAME
    if not segments_dir.exists():
        issues.append(f"missing {SEGMENTS_DIRNAME}/ directory")
    elif not segments_dir.is_dir():
        issues.append(f"{SEGMENTS_DIRNAME} exists but is not a directory")
    else:
        # Check segment files
        for entry in sorted(segments_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_file():
                issues.append(f"non-file entry in {SEGMENTS_DIRNAME}/: {entry.name}")
            elif entry.suffix != ".jsonl":
                issues.append(f"non-jsonl file in {SEGMENTS_DIRNAME}/: {entry.name}")
            else:
                # Validate JSONL content
                segment_issues = _check_jsonl_file(entry)
                for issue in segment_issues:
                    issues.append(f"{SEGMENTS_DIRNAME}/{entry.name}: {issue}")

    stage_dir = tape_path / STAGE_DIRNAME
    if not stage_dir.exists():
        issues.append(f"missing {STAGE_DIRNAME}/ directory")
    elif not stage_dir.is_dir():
        issues.append(f"{STAGE_DIRNAME} exists but is not a directory")

    conformant = len(issues) == 0
    result: dict[str, object] = {
        "tape_path": str(tape_path),
        "conformant": conformant,
        "issues": issues,
    }
    if isinstance(manifest, dict):
        result["manifest"] = manifest
    return result


def _check_jsonl_file(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.rstrip("\n")
                if not line.strip():
                    issues.append(f"blank line at line {line_no}")
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    issues.append(f"invalid JSON at line {line_no}")
    except OSError as exc:
        issues.append(f"cannot read file: {exc}")
    return issues
