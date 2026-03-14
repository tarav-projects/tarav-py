from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError

QUARANTINE_HOME = Path("~/.taraproject/quarantine-tapes").expanduser()
QUARANTINE_MANIFEST_FILENAME = "manifest.json"


def quarantine_tapes(
    tape_paths: list[Path],
    *,
    quarantine_home: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    home = (quarantine_home or QUARANTINE_HOME).expanduser().resolve()

    resolved_paths: list[Path] = []
    for p in tape_paths:
        resolved = p.expanduser().resolve()
        if not resolved.is_dir():
            raise CliError(f"tape path is not a directory: {resolved}")
        resolved_paths.append(resolved)

    if not resolved_paths:
        return {
            "dry_run": dry_run,
            "quarantined": False,
            "quarantine_id": None,
            "quarantine_path": None,
            "tapes": [],
        }

    quarantine_id = str(uuid.uuid4())
    quarantine_dir = home / quarantine_id

    tapes_info: list[dict[str, object]] = []
    for tape_path in resolved_paths:
        tape_name = tape_path.name
        dest = quarantine_dir / tape_name
        tapes_info.append({
            "tape_name": tape_name,
            "original_path": str(tape_path),
            "quarantine_path": str(dest),
        })

    if dry_run:
        return {
            "dry_run": True,
            "quarantined": False,
            "quarantine_id": quarantine_id,
            "quarantine_path": str(quarantine_dir),
            "tapes": tapes_info,
        }

    quarantine_dir.mkdir(parents=True, exist_ok=True)

    for info in tapes_info:
        shutil.move(info["original_path"], info["quarantine_path"])

    manifest = {
        "quarantine_id": quarantine_id,
        "created_at": utc_now_iso(),
        "tapes": [
            {
                "tape_name": t["tape_name"],
                "original_path": t["original_path"],
            }
            for t in tapes_info
        ],
    }
    manifest_path = quarantine_dir / QUARANTINE_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "dry_run": False,
        "quarantined": True,
        "quarantine_id": quarantine_id,
        "quarantine_path": str(quarantine_dir),
        "tapes": tapes_info,
    }
