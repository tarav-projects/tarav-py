from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos.tara_tapes.check import check_tape, discover_tape_candidates

QUARANTINE_HOME = Path("~/.taraproject/quarantine-tapes").expanduser()
QUARANTINE_MANIFEST_FILENAME = "manifest.json"


def quarantine_tapes(
    root: Path,
    *,
    quarantine_home: Path | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    root = root.expanduser().resolve()
    home = (quarantine_home or QUARANTINE_HOME).expanduser().resolve()

    candidates = discover_tape_candidates(root)

    non_conformant: list[dict[str, object]] = []
    conformant_count = 0

    for tape_path in candidates:
        result = check_tape(tape_path)
        if result["conformant"]:
            conformant_count += 1
        else:
            non_conformant.append(result)

    if not non_conformant:
        return {
            "dry_run": dry_run,
            "quarantined": False,
            "source_root": str(root),
            "tape_count": len(candidates),
            "conformant_count": conformant_count,
            "non_conformant_count": 0,
            "quarantine_id": None,
            "quarantine_path": None,
            "tapes": [],
        }

    quarantine_id = str(uuid.uuid4())
    quarantine_dir = home / quarantine_id

    tapes_info: list[dict[str, object]] = []
    for result in non_conformant:
        tape_path = Path(result["tape_path"])
        tape_name = tape_path.name
        dest = quarantine_dir / tape_name
        tapes_info.append({
            "tape_name": tape_name,
            "original_path": str(tape_path),
            "quarantine_path": str(dest),
            "issues": result["issues"],
            "manifest": result.get("manifest"),
        })

    if dry_run:
        return {
            "dry_run": True,
            "quarantined": False,
            "source_root": str(root),
            "tape_count": len(candidates),
            "conformant_count": conformant_count,
            "non_conformant_count": len(non_conformant),
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
        "source_root": str(root),
        "tapes": [
            {
                "tape_name": t["tape_name"],
                "original_path": t["original_path"],
                "issues": t["issues"],
                "manifest": t["manifest"],
            }
            for t in tapes_info
        ],
    }
    manifest_path = quarantine_dir / QUARANTINE_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "dry_run": False,
        "quarantined": True,
        "source_root": str(root),
        "tape_count": len(candidates),
        "conformant_count": conformant_count,
        "non_conformant_count": len(non_conformant),
        "quarantine_id": quarantine_id,
        "quarantine_path": str(quarantine_dir),
        "tapes": tapes_info,
    }
