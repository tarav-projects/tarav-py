"""The built argparse tree projected as Tarav command objects."""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, WorkflowShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, CheckSuite
from tarav.l1.live_help import LiveHelpProvider
from tarav.l1.usage import UsageTrace


CLI_WORKFLOW_SHIP = WorkflowShip("66ab1312-5e49-4849-8503-1315f461b4bd")
_COMMAND_NAMESPACE = UUID("568520b3-d876-43cb-8bfd-6c2e4f13d5a0")


# tarav.breadcrumb 4d74d3599852
class CliWorkflow(TaravWorkflow):
    constitution = "Expose the installed Tarav command tree as inspectable objects."

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b3dc521d-faa8-4c1d-b976-dc61121b77bf"),
            name="Tarav.Workflow.CLI", workflow=CLI_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls) -> WorkflowShip:
        return CLI_WORKFLOW_SHIP


# tarav.breadcrumb eb43ccb7c351
class CommandUse(UsageTrace):
    """A CLI invocation, rendered by the workflow that knows its payload."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("ae5c5356-8701-4ed0-872c-a4984b382813"),
            name="Tarav.CLI.Command.Use",
            workflow=CLI_WORKFLOW_SHIP,
        )

    @classmethod
    def render_trace(cls, row: dict[str, object]) -> tuple[str, ...]:
        payload = row.get("payload")
        values = payload if isinstance(payload, dict) else {}
        stamp = str(row.get("recorded_at", ""))[:16].replace("T", " ")
        lines = [f"  {stamp}  exit {values.get('exit_code', '?')}"]
        descriptor = values.get("use")
        if isinstance(descriptor, dict):
            # tarav.breadcrumb fb608dd92ba4
            for key, value in descriptor.items():
                shown = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
                lines.append(f"                    {key}: {shown}")
        if values.get("cwd"):
            lines.append(f"                    cwd {values['cwd']}")
        return tuple(lines)


class Command(TaravEntity, CheckProvider, LiveHelpProvider):
    """One parser node; its readable path determines its stable Ship."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("e984ba90-47ab-4d31-91e2-1253db69e04c"),
            name="Tarav.CLI.Command", workflow=CLI_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        type: Literal["Tarav.CLI.Command"]
        path: list[str]
        description: str

    def __init__(
        self, path: tuple[str, ...], parser: argparse.ArgumentParser,
        *, help_text: str | None = None,
    ) -> None:
        super().__init__(Ship(uuid5(_COMMAND_NAMESPACE, "tarav " + " ".join(path))))
        self.path = path
        self.parser = parser
        self.handler = parser.get_default("handler")
        # tarav.breadcrumb 82aaddbb8725
        # A command owner may declare `set_defaults(usage_descriptor=fn)`, where
        # fn(args) returns a small mapping describing that call for later readers.
        self.usage_descriptor = parser.get_default("usage_descriptor")
        self.description = parser.description or help_text or ""

    @classmethod
    def _from_record(cls, record_data: BaseModel):
        raise TypeError("Commands are resolved from the current parser tree")

    def _to_record(self) -> dict[str, object]:
        return {
            **super()._to_record(),
            "path": list(self.path),
            "description": self.description,
        }

    @property
    def help_subject(self) -> str:
        return " ".join(self.path)

    @property
    def help_workflow(self) -> type[TaravWorkflow]:
        return CliWorkflow

    @property
    def help_trace_type(self) -> type[UsageTrace]:
        return CommandUse

    @property
    def help_heading(self) -> str:
        return "command"

    @property
    def source_location(self) -> tuple[Path, int] | None:
        if self.handler is None:
            return None
        try:
            source = inspect.getsourcefile(self.handler)
            _, line = inspect.getsourcelines(self.handler)
            if source is None:
                return None
            return Path(source).resolve(strict=True), line
        except (OSError, TypeError, ValueError):
            return None

    # tarav.breadcrumb e0231acfee1f
    class Checks(CheckProvider.Checks):
        def suite(self) -> CheckSuite:
            return CheckSuite((CommandMetadataCheck(self.obj),))


class CommandMetadataPOI(CheckPOI):
    """Family, never raised: a command lacks metadata agents rely on."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9d22138e-af8c-4aec-8ce6-1583d45c6e91"),
                          name="Tarav.CLI.Command.Metadata.POI", workflow=CLI_WORKFLOW_SHIP)


class CommandHelpMissing(CommandMetadataPOI):
    """A command has no description."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bdf59ffa-b0f1-4e9a-bff0-24a6a3fb8ee0"),
                          name="Tarav.CLI.Command.Metadata.HelpMissing", workflow=CLI_WORKFLOW_SHIP)


class CommandSourceUnavailable(CommandMetadataPOI):
    """A command handler's source location cannot be found."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ec58ad21-cbcd-47c6-8d62-fcf6367462b3"),
                          name="Tarav.CLI.Command.Metadata.SourceUnavailable", workflow=CLI_WORKFLOW_SHIP)


class CommandUsageDescriptorMissing(CommandMetadataPOI):
    """A command does not describe its calls for the Usage Registry."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e6ae640d-f2f7-46f8-83a3-a633b78ddaf6"),
                          name="Tarav.CLI.Command.Metadata.UsageDescriptorMissing", workflow=CLI_WORKFLOW_SHIP)


class CommandMetadataCheck(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("3252956d-80cd-4b15-ae7e-a7c238557410"),
            name="Tarav.CLI.Command.Metadata.Check", workflow=CLI_WORKFLOW_SHIP,
        )

    def __init__(self, command: Command) -> None:
        super().__init__()
        self.command = command

    def _run(self) -> CheckResult:
        problems: list[CheckPOI] = []
        if not self.command.description and self.command.path:
            problems.append(CommandHelpMissing(
                self, "Command has no description",
                situation={"command": self.command.help_subject},
            ))
        if self.command.handler is not None and self.command.source_location is None:
            problems.append(CommandSourceUnavailable(
                self, "Command handler source is unavailable",
                situation={"command": self.command.help_subject},
            ))
        if self.command.handler is not None and self.command.usage_descriptor is None:
            problems.append(CommandUsageDescriptorMissing(
                self,
                "Command does not describe its calls for the Usage Registry",
                situation={"command": self.command.help_subject},
            ))
        return CheckResult(self, status="completed", pois=problems)


def commands_from_parser(parser: argparse.ArgumentParser) -> tuple[Command, ...]:
    """Derive command objects from the actual argparse tree, including groups."""
    result: list[Command] = []

    def walk(node: argparse.ArgumentParser, path: tuple[str, ...], help_text: str | None = None) -> None:
        result.append(Command(path, node, help_text=help_text))
        for action in node._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    choice_help = next(
                        (choice.help for choice in action._choices_actions if choice.dest == name),
                        None,
                    )
                    walk(child, (*path, name), choice_help)

    walk(parser, ())
    return tuple(result)


__all__ = ["CliWorkflow", "CommandUse", "Command", "CommandMetadataCheck", "commands_from_parser"]
