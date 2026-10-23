"""Global command-token routing and construction of external argument vectors."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shlex
from typing import Sequence

from tarav.l0._core.errors import CliError
from tarav.l0._core.home import tarav_home_dir


def _argv(value: object, field: str) -> tuple[str, ...]:
    if (not isinstance(value, list) or not value
            or any(not isinstance(token, str) or "\0" in token for token in value)
            or not value[0]):
        raise ValueError(f"{field} must be a nonempty string array with a nonempty first token and no NUL bytes")
    return tuple(value)


# tarav.breadcrumb 04f41c0839ac
@dataclass(frozen=True)
class CommandRoute:
    """Replace one command path, preserving its trailing arguments."""

    command: tuple[str, ...]
    argv: tuple[str, ...]
    shell_command: tuple[str, ...] | None = None

    def invocation(self, arguments: Sequence[str]) -> tuple[str, ...]:
        if self.shell_command is not None:
            return (*self.argv, shlex.join((*self.shell_command, *arguments)))
        return (*self.argv, *arguments)


@dataclass(frozen=True)
class CommandRouter:
    routes: tuple[CommandRoute, ...] = ()

    @classmethod
    def load(cls, path: Path | None = None) -> CommandRouter:
        """Read optional global configuration without creating it."""
        path = path if path is not None else tarav_home_dir() / "cli-routes.json"
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls()
        except (OSError, UnicodeError) as exc:
            raise CliError(f"cannot read {path}: {exc}") from exc
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict) or set(payload) != {"routes"}:
                raise ValueError("expected a JSON object containing only 'routes'")
            if not isinstance(payload["routes"], list):
                raise ValueError("routes must be an array")
            routes: list[CommandRoute] = []
            seen: set[tuple[str, ...]] = set()
            for index, entry in enumerate(payload["routes"]):
                field = f"routes[{index}]"
                if (not isinstance(entry, dict) or not {"command", "argv"} <= entry.keys()
                        or entry.keys() - {"command", "argv", "shell_command"}):
                    raise ValueError(f"{field} requires command, argv and optional shell_command only")
                command = _argv(entry["command"], f"{field}.command")
                if any(not token or any(char.isspace() for char in token) for token in command):
                    raise ValueError(f"{field}.command must contain separate nonempty command tokens")
                if command in seen:
                    raise ValueError(f"duplicate command route: {shlex.join(command)}")
                seen.add(command)
                routes.append(CommandRoute(
                    command=command,
                    argv=_argv(entry["argv"], f"{field}.argv"),
                    shell_command=(_argv(entry["shell_command"], f"{field}.shell_command")
                                   if "shell_command" in entry else None),
                ))
            return cls(tuple(routes))
        except (ValueError, TypeError) as exc:
            raise CliError(f"invalid {path}: {exc}") from exc

    def resolve(self, arguments: Sequence[str]) -> tuple[str, ...] | None:
        """Choose the longest exact leading token path; never parse its options."""
        matched = [route for route in self.routes
                   if tuple(arguments[:len(route.command)]) == route.command]
        if not matched:
            return None
        route = max(matched, key=lambda route: len(route.command))
        return route.invocation(arguments[len(route.command):])
