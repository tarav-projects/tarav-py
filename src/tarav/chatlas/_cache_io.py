from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CHATLAS_CACHE_SCHEMA_VERSION = 2


def load_chatlas_cache_section(
    cache_path: Path,
    *,
    entries_key: str,
) -> dict[str, Any]:
    if not cache_path.is_file():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != _CHATLAS_CACHE_SCHEMA_VERSION:
        return {}
    entries = payload.get(entries_key)
    if not isinstance(entries, dict):
        return {}
    return entries


def write_chatlas_cache_section(
    cache_path: Path,
    *,
    cache_schema: str,
    entries_key: str,
    entries: dict[str, Any],
) -> None:
    payload = {
        "schema": cache_schema,
        "schema_version": _CHATLAS_CACHE_SCHEMA_VERSION,
        entries_key: entries,
    }
    write_text_if_changed(cache_path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def write_text_if_changed(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")
