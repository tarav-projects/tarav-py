from __future__ import annotations

import datetime
import stat
from pathlib import Path

from agentos.testing import AgentosTestEnvironment

from _helpers import read_jsonl_file


def _set_fake_agentos_home(monkeypatch, root: Path) -> Path:
    environment = AgentosTestEnvironment.create(root)
    environment.apply_environment(monkeypatch.setenv)
    return environment.agentos_home


def test_sample_hook_context_writes_private_dated_log(
    monkeypatch, tmp_path: Path
) -> None:
    home_root = _set_fake_agentos_home(monkeypatch, tmp_path)
    from agentos.agent.usage_report import (
        HOOK_CONTEXT_SAMPLE_CLASS,
        HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION,
        append_hook_context_sample,
        hook_context_sample_log_dir,
    )

    provider_home = tmp_path / "codex-home"
    raw_context = {
        "hook_event_name": "Stop",
        "session_id": "s1",
        "prompt": "possibly sensitive",
    }

    path = append_hook_context_sample(
        provider="codex",
        home=provider_home,
        account="br",
        raw_context=raw_context,
    )

    today = datetime.datetime.now(tz=datetime.UTC)
    assert path == hook_context_sample_log_dir() / f"{today:%Y%m%d}.jsonl"
    assert path.parent == home_root / "agent" / "usage-report-hook-samples"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    records = read_jsonl_file(path)
    assert records == [
        {
            "schema_version": HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION,
            "class": HOOK_CONTEXT_SAMPLE_CLASS,
            "recorded_at": records[0]["recorded_at"],
            "provider": "codex",
            "account": "br",
            "home": str(provider_home.expanduser().resolve()),
            "status": "sampled",
            "raw_context": raw_context,
        }
    ]
    assert records[0]["recorded_at"].endswith("Z")
    assert not (home_root / "agent" / "usage-registry").exists()


def test_sample_hook_context_retention_trims_oldest_matching_records(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    from agentos.agent.usage_report import append_hook_context_sample

    provider_home = tmp_path / "codex-home"

    for index in range(5):
        path = append_hook_context_sample(
            provider="codex",
            home=provider_home,
            account="br",
            raw_context={"n": index},
            max_records=3,
        )

    records = read_jsonl_file(path)
    assert [record["raw_context"]["n"] for record in records] == [2, 3, 4]


def test_sample_hook_context_retention_is_scoped_by_provider_home_account(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    from agentos.agent.usage_report import append_hook_context_sample

    home_a = tmp_path / "codex-a"
    home_b = tmp_path / "codex-b"
    path = append_hook_context_sample(
        provider="codex",
        home=home_a,
        account="br",
        raw_context={"home": "a0"},
        max_records=1,
    )
    append_hook_context_sample(
        provider="codex",
        home=home_b,
        account="br",
        raw_context={"home": "b0"},
        max_records=1,
    )
    append_hook_context_sample(
        provider="codex",
        home=home_a,
        account="br",
        raw_context={"home": "a1"},
        max_records=1,
    )

    records = read_jsonl_file(path)
    assert [record["raw_context"]["home"] for record in records] == ["b0", "a1"]


def test_sample_hook_context_rejects_unserializable_raw_context(
    monkeypatch, tmp_path: Path
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path)
    from agentos._core.errors import CliError
    from agentos.agent.usage_report import append_hook_context_sample

    try:
        append_hook_context_sample(
            provider="codex",
            home=tmp_path / "codex-home",
            raw_context={"bad": object()},
        )
    except CliError as exc:
        assert "hook context sample is not JSON serializable" in str(exc)
    else:
        raise AssertionError("expected CliError")
