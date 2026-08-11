# $kw: --from Provider.Home
from __future__ import annotations

import json
from pathlib import Path

from agentos.chatlas.paths import default_chatlas_root


def load_chatlas_run_produce_config(
    *,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    config_path = root / "config.json"
    if not config_path.is_file():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    chatlas_block = payload.get("chatlas", payload)
    if not isinstance(chatlas_block, dict):
        return {}
    run_produce = chatlas_block.get("run_produce", {})
    if not isinstance(run_produce, dict):
        return {}
    return dict(run_produce)


__all__ = ["load_chatlas_run_produce_config"]
