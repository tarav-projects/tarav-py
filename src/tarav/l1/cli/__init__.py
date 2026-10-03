"""The built argparse tree projected as Tarav command objects."""

from __future__ import annotations

import argparse
import inspect
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, WorkflowShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult
from tarav.l1.live_help import LiveHelpProvider


CLI_WORKFLOW_SHIP = WorkflowShip("66ab1312-5e49-4849-8503-1315f461b4bd")
_COMMAND_NAMESPACE = UUID("568520b3-d876-43cb-8bfd-6c2e4f13d5a0")


# tarav.breadcrumb 4d74d3599852862caba881695d886f0407039f0012b353ce9cafe7e9777b2daa
class CliWorkflow(TaravWorkflow):
    workflow_name = "cli"
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
        # tarav.breadcrumb 82aaddbb87253228672ab53ea85d0f081d8c5f17ad5ccedefd507eff630406fa
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

    @property
    def checks(self) -> tuple[Check, ...]:
        return (CommandMetadataCheck(self),)


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
            problems.append(CheckPOI(
                self, "cli.missing-help", "Command has no description",
                situation={"command": self.command.help_subject},
            ))
        if self.command.handler is not None and self.command.source_location is None:
            problems.append(CheckPOI(
                self, "cli.missing-source", "Command handler source is unavailable",
                situation={"command": self.command.help_subject},
            ))
        if self.command.handler is not None and self.command.usage_descriptor is None:
            problems.append(CheckPOI(
                self, "cli.missing-usage-descriptor",
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


__all__ = ["CliWorkflow", "Command", "CommandMetadataCheck", "commands_from_parser"]
