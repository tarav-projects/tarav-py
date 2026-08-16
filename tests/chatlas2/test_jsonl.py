from __future__ import annotations

import re
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.chatlas2.jsonl import JsonlCandidateScan, iter_jsonl_objects


def test_scan_happens_before_decode_and_may_admit_false_positives(
    tmp_path: Path,
) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(
        'not-json\n{"noise":"needle","value":"miss"}\n{"value":"needle"}\n',
        encoding="utf-8",
    )

    candidates = iter_jsonl_objects(
        path,
        scan=JsonlCandidateScan(literals=("needle",)),
    )
    assert [record for record in candidates if record.get("value") == "needle"] == [
        {"value": "needle"}
    ]

    with pytest.raises(CliError, match="invalid JSON"):
        list(iter_jsonl_objects(path))


def test_compiled_regex_selects_multiple_serialized_addresses(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"event_address":"aaa","value":1}',
                '{"event_address":"bbb","value":2}',
                '{"event_address":"ccc","value":3}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    scan = JsonlCandidateScan(pattern=re.compile(r'"event_address":"(?:aaa|ccc)"'))

    assert [record["value"] for record in iter_jsonl_objects(path, scan=scan)] == [
        1,
        3,
    ]
