"""Explicit one-time code/data migration; never imported by runtime readers.

Use --root /absolute/archive/root to inspect, then --apply to execute.
Requires clean Git history so every prior Record remains recoverable.
DOIs, payloads, coordinates, and recorded observations are preserved.
"""

import argparse
import json
from pathlib import Path
import subprocess

from tarav._core.persistence import atomic_write_text
from tarav.archive.records import record_registry


def migrate(root: Path, *, apply: bool = False) -> dict:
    records = root.resolve(strict=True) / "records"
    status = subprocess.run(
        ["git", "-C", str(records), "status", "--porcelain"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if status:
        raise ValueError("Archive Records must have a clean recoverable Git checkpoint")
    checkpoint = subprocess.run(
        ["git", "-C", str(records), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    registry = record_registry()
    changes = []
    for path in sorted(records.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(records).parts:
            continue
        if path.suffix not in {".json", ".jsonl"}:
            continue
        original = path.read_text(encoding="utf-8")
        payloads = (
            [json.loads(line) for line in original.splitlines()]
            if path.suffix == ".jsonl"
            else [json.loads(original)]
        )
        changed = False
        for payload in payloads:
            if "class" not in payload:
                registry.resolve(payload)
                continue
            if payload.get("schema_version") != 1 or "type" in payload:
                raise ValueError(f"Unexpected schema in {path}")
            payload["type"] = payload.pop("class")
            payload["schema_version"] = 2
            if payload["type"] == "Tarav.Archive.Artifact.Registration.Record":
                payload["contract"] = {
                    "kind": payload["kind"],
                    "identity": payload["identity"],
                }
            registry.from_record(payload)
            changed = True
        if changed:
            content = (
                "".join(json.dumps(p, sort_keys=True) + "\n" for p in payloads)
                if path.suffix == ".jsonl"
                else json.dumps(payloads[0], indent=2, sort_keys=True) + "\n"
            )
            changes.append((path, content))
    # Validate the complete batch before any mutation.
    if apply:
        for path, content in changes:
            atomic_write_text(path, content)
    return {
        "root": str(records),
        "checkpoint": checkpoint,
        "changed_files": len(changes),
        "applied": apply,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), indent=2))
