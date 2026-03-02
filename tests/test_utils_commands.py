from __future__ import annotations

import json
from uuid import UUID

from agentos.cli import main


def _assert_valid_uuid(text: str) -> None:
    parsed = UUID(text)
    assert str(parsed) == text


def test_utils_uuid_default_outputs_single_uuid(capsys) -> None:
    assert main(["utils", "uuid"]) == 0
    out = capsys.readouterr().out.strip()
    assert out
    _assert_valid_uuid(out)


def test_utils_uuid_count_outputs_multiple_lines(capsys) -> None:
    assert main(["utils", "uuid", "--count", "3"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 3
    for line in lines:
        _assert_valid_uuid(line)


def test_utils_uuid_json_outputs_payload(capsys) -> None:
    assert main(["utils", "uuid", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command"] == "utils uuid"
    assert payload["count"] == 1
    assert isinstance(payload["uuids"], list)
    assert len(payload["uuids"]) == 1
    _assert_valid_uuid(payload["uuid"])
    _assert_valid_uuid(payload["uuids"][0])


def test_utils_uuid_rejects_invalid_count(capsys) -> None:
    assert main(["utils", "uuid", "--count", "0"]) == 1
    stderr = capsys.readouterr().err
    assert "--count must be >= 1" in stderr
