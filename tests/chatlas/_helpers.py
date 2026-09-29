from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav.l0.testing import TaravTestEnvironment


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_codex_work_profile(
    environment: TaravTestEnvironment,
    codex_home: Path,
) -> None:
    environment.write_profile(
        "codex-work",
        provider="codex",
        homes=[str(codex_home)],
    )


def write_chatlas_codex_source(
    environment: TaravTestEnvironment,
    codex_home: Path,
    *,
    chatlas_config: dict[str, object] | None = None,
) -> None:
    config: dict[str, object] = {
        "sources": [
            {
                "provider": "codex",
                "home": str(codex_home),
            },
        ],
    }
    if chatlas_config is not None:
        config.update(chatlas_config)
    environment.write_global_config(chatlas=config)


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_file(path: Path) -> list[Any]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def captured_json(capsys: object) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
