from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tarav.l0.kernel import Ship
from tarav.l1.cli import CliWorkflow, Command, commands_from_parser
from tarav.l1.live_help import LiveHelpWorkflow
from tarav.l1.usage import UsageRegistry
from tarav.l3.cli import cli as cli_adapter
from tarav.l3.runtime import create_runtime


# tarav.breadcrumb 8c6b363d7fdc570627db715abd9522cdd6b19a283c6473be28cd4d1b83c53a8e
def test_usage_registry_filters_queries_and_trims_day_files(tmp_path: Path) -> None:
    create_runtime(archive_root=tmp_path)
    registry = UsageRegistry(tmp_path, window_days=7)
    project = Ship("a1754ce5-777b-4935-a764-74b90ea823c6")

    assert registry.record(workflow=CliWorkflow, subject="skw document", payload={"exit_code": 0}, project=project)
    assert registry.record(workflow=LiveHelpWorkflow, subject="other", payload={"exit_code": 1})
    rows = registry.query(
        workflow=CliWorkflow, project=project, subject="skw document",
        expression="payload.exit_code == `0`",
    )
    assert len(rows) == 1
    assert rows[0]["subject"] == "skw document"
    assert registry.query(workflow=CliWorkflow, expression="payload.exit_code == `1`") == ()

    folder = registry.partition.directory / str(CliWorkflow().id)
    old = folder / f"{datetime.now(timezone.utc) - timedelta(days=9):%Y-%m-%d}-usage.jsonl"
    old.write_text(
        '{"recorded_at":"2020-01-01T00:00:00+00:00",'
        '"workflow":"' + str(CliWorkflow().id) + '","subject":"stale"}\n',
        encoding="utf-8",
    )
    assert registry.query(workflow=CliWorkflow, subject="stale") == ()
    registry.trim()
    assert not old.exists()
    assert len(registry.query(workflow=CliWorkflow)) == 1


def test_command_model_is_stable_and_raises_missing_help_poi() -> None:
    parser = argparse.ArgumentParser(prog="tarav")
    children = parser.add_subparsers()
    leaf = children.add_parser("probe")
    leaf.set_defaults(handler=lambda args: 0)

    first = commands_from_parser(parser)
    second = commands_from_parser(parser)
    assert [item.id for item in first] == [item.id for item in second]
    command = first[1]
    assert isinstance(command, Command)
    assert command.help_subject == "probe"
    assert command.to_record()["path"] == ["probe"]
    assert [poi.code for poi in command.checks[0].run().pois()] == ["cli.missing-help"]


def test_cli_help_and_safe_recent_use(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    secret = "private-example-value"

    assert cli_adapter.main(["usage", "query", "--subject", secret]) == 0
    capsys.readouterr()
    rows = runtime.usage.query(workflow=CliWorkflow, subject="usage query")
    assert len(rows) == 1
    assert rows[0]["payload"]["options"] == ["--subject"]
    assert secret not in str(rows)
    assert runtime.usage.record(
        workflow=LiveHelpWorkflow, subject="usage query", payload={"exit_code": 9},
    )

    with pytest.raises(SystemExit) as exit_info:
        cli_adapter.build_parser(runtime=runtime).parse_args(["usage", "query", "--help"])
    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "command:  usage query" in help_text
    assert "source:" in help_text
    assert "recent uses (1 of 1)" in help_text
    assert "exit 9" not in help_text
    assert secret not in help_text


def test_usage_write_failure_preserves_cli_outcome(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    monkeypatch.setattr(runtime.usage, "record", lambda **kwargs: False)
    assert cli_adapter.main(["usage", "query", "--limit", "0"]) == 0
    assert capsys.readouterr().out.strip() == "[]"


def test_python_remainder_is_absent_from_usage_trace(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    secret = "private-python-source-value"
    assert cli_adapter.main(["run", "--", "-c", f"print({secret!r})"]) == 0
    capsys.readouterr()
    rows = runtime.usage.query(workflow=CliWorkflow, subject="run")
    assert len(rows) == 1
    assert secret not in str(rows)
