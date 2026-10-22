from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l1.agent.usage_registry import (
    append_usage_record,
    latest_account_usage_record,
    latest_usage_record,
)


def _legacy_record(home: Path, *, used: int) -> dict:
    return {
        "schema_version": 1,
        "class": "agentos.agent.usage-record",
        "recorded_at": "2026-09-01T00:00:00.000000Z",
        "provider": "codex",
        "account": "br",
        "home": str(home.resolve()),
        "source": "app_server",
        "payload": {"used": used},
    }


@pytest.fixture
def tarav_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "tarav-home"
    monkeypatch.setenv("TARAV_HOME", str(home))
    return home


def test_records_written_before_the_rename_stay_readable(
    tarav_home: Path, tmp_path: Path
) -> None:
    provider_home = tmp_path / "codex-br"
    registry = tarav_home / "agent" / "usage-registry"
    registry.mkdir(parents=True)
    (registry / "202609-usage.jsonl").write_text(
        json.dumps(_legacy_record(provider_home, used=42)) + "\n", encoding="utf-8"
    )

    record = latest_usage_record(
        provider="codex", account="br", home=provider_home, source="app_server"
    )

    assert record is not None
    assert record["payload"] == {"used": 42}


def test_new_records_use_the_tarav_class_and_win_over_legacy_history(
    tarav_home: Path, tmp_path: Path
) -> None:
    provider_home = tmp_path / "codex-br"
    registry = tarav_home / "agent" / "usage-registry"
    registry.mkdir(parents=True)
    (registry / "202609-usage.jsonl").write_text(
        json.dumps(_legacy_record(provider_home, used=42)) + "\n", encoding="utf-8"
    )

    path = append_usage_record(
        provider="codex",
        account="br",
        home=provider_home,
        source="app_server",
        payload={"used": 100},
    )

    written = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert written["class"] == "tarav.agent.usage-record"
    latest = latest_account_usage_record(provider="codex", account="br", source="app_server")
    assert latest is not None
    assert latest["payload"] == {"used": 100}


def test_records_of_unknown_classes_are_ignored(tarav_home: Path, tmp_path: Path) -> None:
    provider_home = tmp_path / "codex-br"
    registry = tarav_home / "agent" / "usage-registry"
    registry.mkdir(parents=True)
    foreign = {**_legacy_record(provider_home, used=7), "class": "other.record"}
    (registry / "202609-usage.jsonl").write_text(json.dumps(foreign) + "\n", encoding="utf-8")

    assert (
        latest_usage_record(provider="codex", account="br", home=provider_home, source="app_server")
        is None
    )
