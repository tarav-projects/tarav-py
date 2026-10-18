from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l1.cli import CliWorkflow, Command, CommandUse, commands_from_parser
from tarav.l1.live_help import LiveHelpProvider, LiveHelpWorkflow, render_live_help
from tarav.l1.usage import UsageRegistry, UsageTrace
from tarav.l3.cli import cli as cli_adapter
from tarav.l3.runtime import create_runtime


# tarav.breadcrumb 8c6b363d7fdc
def test_usage_registry_filters_queries_and_trims_day_files(tmp_path: Path) -> None:
    create_runtime(archive_root=tmp_path)
    registry = UsageRegistry(tmp_path, window_days=7)
    project = Ship("a1754ce5-777b-4935-a764-74b90ea823c6")

    assert registry.record(trace_type=CommandUse, workflow=CliWorkflow,
                           subject="skw document", payload={"exit_code": 0}, project=project)
    assert registry.record(trace_type=UsageTrace, workflow=LiveHelpWorkflow,
                           subject="other", payload={"exit_code": 1})
    rows = registry.query(
        workflow=CliWorkflow, project=project, subject="skw document",
        expression="payload.exit_code == `0`",
    )
    assert len(rows) == 1
    assert rows[0]["subject"] == "skw document"
    assert rows[0]["type"] == "Tarav.CLI.Command.Use"
    assert registry.query(trace_type=CommandUse) == rows
    assert registry.query(trace_type="Tarav.Usage.Trace")[0]["subject"] == "other"
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
    assert command.records.to_record()["path"] == ["probe"]
    # tarav.breadcrumb d65d6209603f
    assert [type(poi).__name__ for poi in command.checks.run().pois()] == [
        "CommandHelpMissing", "CommandUsageDescriptorMissing",
    ]


def test_cli_help_shows_the_command_described_use(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    value = "example-subject-value"

    assert cli_adapter.main(["usage", "query", "--subject", value]) == 0
    capsys.readouterr()
    rows = runtime.usage.query(workflow=CliWorkflow, subject="usage query")
    assert len(rows) == 1
    assert rows[0]["payload"]["use"] == {"subject": value}
    assert runtime.usage.record(
        trace_type=UsageTrace,
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
    assert f"subject: {value}" in help_text


def test_legacy_rows_remain_queryable_but_not_live_help_examples(tmp_path: Path) -> None:
    registry = UsageRegistry(tmp_path)
    assert registry.record(trace_type=CommandUse, workflow=CliWorkflow,
                           subject="probe", payload={"exit_code": 0})
    folder = registry.partition.directory / str(CliWorkflow().id)
    day_file = folder / f"{datetime.now(timezone.utc):%Y-%m-%d}-usage.jsonl"
    legacy = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "workflow": str(CliWorkflow().id), "subject": "probe",
        "project": None, "payload": {"exit_code": 9},
    }
    with day_file.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(legacy) + "\n")
    assert len(registry.query(workflow=CliWorkflow, subject="probe")) == 2
    assert len(registry.query(workflow=CliWorkflow, subject="probe",
                              trace_type=CommandUse)) == 1
    provider = Command(("probe",), argparse.ArgumentParser())
    output = render_live_help(provider, registry)
    assert "recent uses (1 of 1):" in output
    assert "exit 0" in output
    assert "exit 9" not in output


def test_live_help_uses_provider_type_without_dispatching_from_record(tmp_path: Path) -> None:
    class ExampleTrace(UsageTrace):
        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("1812596d-11e9-4587-9063-ce6a1ce63055"),
                name="Example.Usage.Trace",
            )

        @classmethod
        def render_trace(cls, row):
            return (f"  example: {row['payload']['detail']}",)

    class ExampleProvider(LiveHelpProvider):
        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("98039f10-9579-41d2-968b-d77078075ae7"),
                name="Example.LiveHelp.Provider",
            )

        help_subject = "probe"
        help_workflow = CliWorkflow
        help_trace_type = ExampleTrace
        help_heading = "example"
        source_location = None

    registry = UsageRegistry(tmp_path)
    assert registry.record(trace_type=ExampleTrace, workflow=CliWorkflow,
                           subject="probe", payload={"detail": "shown"})
    assert registry.record(trace_type=CommandUse, workflow=CliWorkflow,
                           subject="probe", payload={"exit_code": 9})
    output = render_live_help(ExampleProvider(), registry)
    assert "example:  probe" in output
    assert "recent uses (1 of 1):" in output
    assert "example: shown" in output
    assert "exit 9" not in output


def test_usage_write_failure_preserves_cli_outcome(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    monkeypatch.setattr(runtime.usage, "record", lambda **kwargs: False)
    assert cli_adapter.main(["usage", "query", "--limit", "0"]) == 0
    assert capsys.readouterr().out.strip() == "[]"


# tarav.breadcrumb a956247074a2
def test_run_describes_code_without_storing_it(tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    code = "print('python-source-value: " + "x" * 200 + "')"
    assert cli_adapter.main(["run", "--", "-c", code]) == 0
    capsys.readouterr()
    rows = runtime.usage.query(workflow=CliWorkflow, subject="run")
    assert len(rows) == 1
    use = rows[0]["payload"]["use"]
    assert use["mode"] == "code"
    assert use["code"]["chars"] == len(code)
    assert code not in str(rows)


def test_short_run_code_remains_verbatim_and_breadcrumb_audit_describes_surface(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    runtime = create_runtime(archive_root=tmp_path)
    monkeypatch.setattr(cli_adapter, "create_runtime", lambda: runtime)
    code = "print(1)"
    assert cli_adapter.main(["run", "--", "-c", code]) == 0
    capsys.readouterr()
    row = runtime.usage.query(workflow=CliWorkflow, subject="run",
                              trace_type=CommandUse)[0]
    assert row["payload"]["use"]["code"] == code

    parser = cli_adapter.build_parser(runtime=runtime)
    args = parser.parse_args([
        "breadcrumbs", "audit", "chatlas-context",
        "--surface", str(tmp_path / "example.md"),
    ])
    command = args._tarav_command
    assert command.usage_descriptor(args) == {"surface": str(tmp_path / "example.md")}
    query_args = parser.parse_args(["usage", "query", "--type", "Tarav.CLI.Command.Use"])
    assert query_args.trace_type == "Tarav.CLI.Command.Use"
