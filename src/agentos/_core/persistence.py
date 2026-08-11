# $kw: --from Stable.Surface
"""Small, dependency-free persistence primitives shared across Agentos domains."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    """Durably replace ``path`` with UTF-8 ``text`` from the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    ensure_ascii: bool = True,
) -> None:
    """Serialize JSON with a trailing newline and atomically replace ``path``."""
    atomic_write_text(
        path,
        json.dumps(
            payload,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
        )
        + "\n",
    )


__all__ = ["atomic_write_json", "atomic_write_text"]
