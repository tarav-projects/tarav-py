from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from agentos._core.project import normalize_project_target
from agentos._core.errors import CliError
from agentos.chat.core import configured_provider_instances, supported_provider_families
from agentos.chat.providers import ProviderInstance


def _list_provider_instances(
    *,
    provider: str | None,
    start_path: Path,
) -> tuple[ProviderInstance, ...]:
    instances = configured_provider_instances(start_path=start_path)
    if provider is None:
        return instances
    return tuple(instance for instance in instances if instance.family == provider)


def _resolve_provider_instance(
    *,
    provider: str,
    instance_id: str | None,
    start_path: Path,
) -> ProviderInstance:
    matching = [
        instance
        for instance in configured_provider_instances(start_path=start_path)
        if instance.family == provider
    ]
    if not matching:
        raise CliError(f"no configured provider instances found for provider {provider}")

    if instance_id is not None:
        for instance in matching:
            if instance.instance_id == instance_id:
                return instance
        raise CliError(
            f"no provider instance {instance_id!r} found for provider {provider}"
        )

    if len(matching) == 1:
        return matching[0]

    available = ", ".join(instance.instance_id or "<default>" for instance in matching)
    raise CliError(
        f"provider {provider} is ambiguous; pass --instance (available: {available})"
    )


def _format_instance_line(instance: ProviderInstance) -> str:
    instance_id = instance.instance_id or "<default>"
    suffix_parts: list[str] = [f"id={instance_id}"]
    if instance.label is not None and instance.label != instance.instance_id:
        suffix_parts.append(instance.label)
    if instance.default_model is not None:
        suffix_parts.append(f"model={instance.default_model}")
    if instance.homes:
        homes_text = ", ".join(f"{key}={path}" for key, path in instance.homes)
        suffix_parts.append(f"homes={homes_text}")

    return f"{instance.family} [{'; '.join(suffix_parts)}]"


def _config_start_path(args: argparse.Namespace) -> Path:
    if args.project is not None:
        return normalize_project_target(args.project)
    return Path.cwd().resolve()


def _cmd_agent_list(args: argparse.Namespace) -> int:
    config_start_path = _config_start_path(args)
    instances = _list_provider_instances(
        provider=args.provider,
        start_path=config_start_path,
    )
    if args.json:
        payload = {
            "instances": [instance.summary() for instance in instances],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if not instances:
        if args.provider is None:
            print("No agent provider instances configured.")
        else:
            print(f"No agent provider instances configured for provider {args.provider}.")
        return 0

    for instance in instances:
        print(_format_instance_line(instance))
    return 0


def _resolve_prompt(prompt_parts: list[str]) -> str:
    if prompt_parts and prompt_parts[0] == "--":
        prompt_parts = prompt_parts[1:]
    if prompt_parts:
        return " ".join(prompt_parts)
    if sys.stdin.isatty():
        raise CliError("prompt is required (pass it after -- or pipe stdin)")
    prompt = sys.stdin.read()
    if not prompt.strip():
        raise CliError("prompt is empty")
    return prompt


def _build_agent_command(
    instance: ProviderInstance,
    *,
    prompt: str,
    model: str | None,
) -> list[str]:
    if not instance.cli_command:
        raise CliError(
            f"provider instance {instance.instance_id or '<default>'} for {instance.family} has no cli_command"
        )

    command = list(instance.cli_command)
    command.extend(instance.run_args)
    effective_model = model or instance.default_model
    if effective_model is not None:
        if instance.model_flag is None:
            raise CliError(
                f"provider instance {instance.instance_id or '<default>'} for {instance.family} does not define model_flag"
            )
        command.extend([instance.model_flag, effective_model])

    if instance.prompt_flag is not None:
        command.extend([instance.prompt_flag, prompt])
    else:
        command.append(prompt)
    return command


def _cmd_agent_run(args: argparse.Namespace) -> int:
    config_start_path = _config_start_path(args)
    cwd = Path(args.cwd).expanduser().resolve() if args.cwd else Path.cwd().resolve()
    instance = _resolve_provider_instance(
        provider=args.provider,
        instance_id=args.instance,
        start_path=config_start_path,
    )
    prompt = _resolve_prompt(args.prompt)
    command = _build_agent_command(
        instance,
        prompt=prompt,
        model=args.model,
    )

    env = os.environ.copy()
    env.update(dict(instance.env))

    if args.dry_run:
        print(shlex.join(command))
        return 0

    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError(f"agent executable not found: {exc.filename}") from exc
    return int(result.returncode)


def register_agent_commands(subparsers: argparse._SubParsersAction) -> None:
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run configured agent provider instances with global/project config resolution.",
    )
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    list_parser = agent_subparsers.add_parser(
        "list",
        help="List available agent provider instances.",
    )
    list_parser.add_argument(
        "--provider",
        default=None,
        choices=tuple(provider.family for provider in supported_provider_families()),
        help="Optional provider family filter.",
    )
    list_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Project target override for config resolution. Bare --project targets current pwd. Agent commands do not require an existing project.",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Print instances as JSON.",
    )
    list_parser.set_defaults(handler=_cmd_agent_list)

    run_parser = agent_subparsers.add_parser(
        "run",
        help="Run one provider instance with a prompt.",
    )
    run_parser.add_argument(
        "--provider",
        required=True,
        choices=tuple(provider.family for provider in supported_provider_families()),
        help="Provider family to run.",
    )
    run_parser.add_argument(
        "--instance",
        default=None,
        help="Configured provider instance id. Optional when provider resolution is unambiguous.",
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help="Model override.",
    )
    run_parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Project target override for config resolution. Bare --project targets current pwd. Agent commands do not require an existing project.",
    )
    run_parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory override for the launched agent process (default: current directory).",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved command instead of running it.",
    )
    run_parser.add_argument(
        "prompt",
        nargs=argparse.REMAINDER,
        help="Prompt to pass after --, or omit and pipe stdin.",
    )
    run_parser.set_defaults(handler=_cmd_agent_run)
