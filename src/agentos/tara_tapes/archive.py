from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError

ARCHIVE_HOME = Path("~/.taraproject/archived-tapes").expanduser()
ARCHIVE_MANIFEST_FILENAME = "manifest.json"


def archive_tapes(
    tape_paths: list[Path],
    *,
    archive_home: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    home = (archive_home or ARCHIVE_HOME).expanduser().resolve()

    resolved_paths: list[Path] = []
    for p in tape_paths:
        resolved = p.expanduser().resolve()
        if not resolved.is_dir():
            raise CliError(f"tape path is not a directory: {resolved}")
        resolved_paths.append(resolved)

    if not resolved_paths:
        return {
            "dry_run": dry_run,
            "archived": False,
            "archive_id": None,
            "archive_path": None,
            "tapes": [],
        }

    archive_id = str(uuid.uuid4())
    archive_dir = home / archive_id

    tapes_info: list[dict[str, object]] = []
    for tape_path in resolved_paths:
        tape_name = tape_path.name
        dest = archive_dir / tape_name
        tapes_info.append({
            "tape_name": tape_name,
            "original_path": str(tape_path),
            "archive_path": str(dest),
        })

    if dry_run:
        return {
            "dry_run": True,
            "archived": False,
            "archive_id": archive_id,
            "archive_path": str(archive_dir),
            "tapes": tapes_info,
        }

    archive_dir.mkdir(parents=True, exist_ok=True)

    for info in tapes_info:
        shutil.move(info["original_path"], info["archive_path"])

    manifest = {
        "archive_id": archive_id,
        "created_at": utc_now_iso(),
        "tapes": [
            {
                "tape_name": t["tape_name"],
                "original_path": t["original_path"],
            }
            for t in tapes_info
        ],
    }
    manifest_path = archive_dir / ARCHIVE_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "dry_run": False,
        "archived": True,
        "archive_id": archive_id,
        "archive_path": str(archive_dir),
        "tapes": tapes_info,
    }
