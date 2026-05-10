from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir, global_config_path, load_global_config
from agentos.agent.primitives import AgentConfig
from agentos.chat.providers import (
    AGENT_INSTANCE_CONFIG_SOURCE,
    agent_config_entries_from_config,
    agent_config_from_config_entry,
)
from agentos.codex.agent import CodexAgent

CODEX_AUTH_FILENAME = "auth.json"
CODEX_DEFAULT_EXECUTABLE = "/opt/homebrew/bin/codex"
CODEX_DEFAULT_HOME_DIRNAME = ".codex"
CODEX_DEFAULT_BASE_ARGS = ("--dangerously-bypass-approvals-and-sandbox",)
CODEX_HOME_ENV_VAR = "CODEX_HOME"
CODEX_MUX_CONFIG_PATH = ("codex", "mux")
CODEX_MANAGED_ACCOUNTS_DIR = ("accounts", "codex")


@dataclass(frozen=True)
class CodexMuxConfig:
    default_home: Path
    accounts_root: Path
    executable: str
    base_args: tuple[str, ...]


def _config_value_at_object_path(config: dict[str, object], *, object_path: tuple[str, ...]) -> object | None:
    current: object = config
    current_path: list[str] = []
    for key in object_path:
        current_path.append(key)
        if not isinstance(current, dict):
            raise CliError(f"config field {'.'.join(current_path[:-1])} must be a JSON object")
        next_value = current.get(key)
        if next_value is None:
            return None
        current = next_value
    return current


def _require_non_empty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalize_path_value(value: object, *, field_name: str) -> Path:
    return Path(_require_non_empty_string(value, field_name=field_name)).expanduser().resolve()


def _normalize_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CliError(f"{field_name} must be a JSON array")
    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(
            _require_non_empty_string(
                item,
                field_name=f"{field_name}[{index}]",
            )
        )
    return tuple(normalized)


def _load_global_agent_instances(config: dict[str, object]) -> tuple[AgentConfig, ...]:
    entries = agent_config_entries_from_config(
        config,
        source=AGENT_INSTANCE_CONFIG_SOURCE,
    )
    instances = tuple(agent_config_from_config_entry(entry) for entry in entries)
    seen_ids: dict[str, AgentConfig] = {}
    for instance in instances:
        if instance.instance_id is None:
            raise CliError("agent.instances ids must not be empty")
        existing = seen_ids.get(instance.instance_id)
        if existing is None:
            seen_ids[instance.instance_id] = instance
            continue
        raise CliError(
            "agent.instances ids must be unique; "
            f"duplicate id {instance.instance_id} for providers "
            f"{existing.provider} and {instance.provider}"
        )
    return instances


def _resolve_codex_mux_default_instance(
    raw_default_instance_id: object,
    *,
    config: dict[str, object],
) -> CodexAgent:
    default_instance_id = validate_string_for_path(
        _require_non_empty_string(
            raw_default_instance_id,
            field_name="codex.mux.default_instance_id",
        ),
        field_name="codex.mux.default_instance_id",
    )
    configs_by_id = {
        instance.instance_id: instance
        for instance in _load_global_agent_instances(config)
        if instance.instance_id is not None
    }
    instance = configs_by_id.get(default_instance_id)
    if instance is None:
        raise CliError(
            "codex.mux.default_instance_id references unknown agent instance id: "
            f"{default_instance_id}"
        )
    if instance.provider != "codex":
        raise CliError(
            "codex.mux.default_instance_id must reference an agent.instances codex entry; "
            f"got {default_instance_id} ({instance.provider})"
        )
    return CodexAgent.from_config(instance)


def _resolve_codex_mux_instance_home(instance: CodexAgent) -> Path:
    homes = instance.homes_map()
    home = homes.get("home")
    if home is None and len(instance.homes) == 1:
        home = instance.homes[0][1]
    if home is None:
        raise CliError(
            f"agent.instances entry {instance.instance_id!r} for provider codex "
            "must define home for codex.mux.default_instance_id"
        )
    return home


def _resolve_codex_mux_instance_executable(instance: CodexAgent) -> str:
    if not instance.cli_command:
        raise CliError(
            f"agent.instances entry {instance.instance_id!r} for provider codex "
            "must define cli_command for codex.mux.default_instance_id"
        )
    return instance.cli_command[0]


def _resolve_codex_mux_instance_base_args(instance: CodexAgent) -> tuple[str, ...]:
    cli_tail = instance.cli_command[1:] if len(instance.cli_command) > 1 else ()
    return (*cli_tail, *instance.run_args)


def _load_codex_mux_config() -> CodexMuxConfig:
    config_path = global_config_path(agentos_home_dir())
    config: dict[str, object] = {}
    if config_path.exists():
        config = load_global_config(config_path)

    raw_mux = _config_value_at_object_path(config, object_path=CODEX_MUX_CONFIG_PATH)
    if raw_mux is None:
        mux_config: dict[str, object] = {}
    elif not isinstance(raw_mux, dict):
        raise CliError("config field codex.mux must be a JSON object")
    else:
        mux_config = raw_mux

    raw_default_instance_id = mux_config.get("default_instance_id")
    default_instance: CodexAgent | None = None
    if raw_default_instance_id is not None:
        default_instance = _resolve_codex_mux_default_instance(
            raw_default_instance_id,
            config=config,
        )

    raw_default_home = mux_config.get("default_home")
    raw_accounts_root = mux_config.get(
        "accounts_root",
        str(agentos_home_dir().joinpath(*CODEX_MANAGED_ACCOUNTS_DIR)),
    )
    raw_executable = mux_config.get("executable")
    raw_base_args = mux_config.get("base_args")

    if raw_default_home is None:
        default_home = (
            _resolve_codex_mux_instance_home(default_instance)
            if default_instance is not None
            else (Path.home() / CODEX_DEFAULT_HOME_DIRNAME).expanduser().resolve()
        )
    else:
        default_home = _normalize_path_value(raw_default_home, field_name="codex.mux.default_home")

    if raw_executable is None:
        executable = (
            _resolve_codex_mux_instance_executable(default_instance)
            if default_instance is not None
            else CODEX_DEFAULT_EXECUTABLE
        )
    else:
        executable = _require_non_empty_string(raw_executable, field_name="codex.mux.executable")

    if raw_base_args is None:
        if default_instance is not None:
            base_args = _resolve_codex_mux_instance_base_args(default_instance)
        else:
            base_args = CODEX_DEFAULT_BASE_ARGS
    else:
        base_args = _normalize_string_tuple(raw_base_args, field_name="codex.mux.base_args")

    return CodexMuxConfig(
        default_home=default_home,
        accounts_root=_normalize_path_value(raw_accounts_root, field_name="codex.mux.accounts_root"),
        executable=executable,
        base_args=base_args,
    )


def _resolve_codex_home(args: argparse.Namespace, *, config: CodexMuxConfig) -> Path:
    if args.home is not None:
        return _normalize_path_value(args.home, field_name="home")
    return config.default_home


def _resolve_codex_auth_path(*, codex_home: Path) -> Path:
    return codex_home / CODEX_AUTH_FILENAME


def _resolve_managed_codex_account_auth_path(account: str, *, config: CodexMuxConfig) -> Path:
    normalized_account = validate_string_for_path(account, field_name="account")
    return config.accounts_root / normalized_account / CODEX_AUTH_FILENAME


def _read_symlink_target(path: Path) -> Path:
    raw_target = os.readlink(path)
    target_path = Path(raw_target)
    if target_path.is_absolute():
        return target_path
    return (path.parent / target_path).resolve()


def _replace_path_with_symlink(*, path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_link = path.parent / f".{path.name}.agentos-tmp-{os.getpid()}"
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
    try:
        temp_link.symlink_to(target)
        os.replace(temp_link, path)
    finally:
        if temp_link.exists() or temp_link.is_symlink():
            temp_link.unlink()


def _link_codex_auth_for_account(
    account: str,
    *,
    codex_home: Path,
    config: CodexMuxConfig,
    mutate: bool = True,
) -> tuple[Path, Path]:
    source_auth = _resolve_managed_codex_account_auth_path(account, config=config)
    if not source_auth.exists():
        raise CliError(f"codex account auth file does not exist: {source_auth}")
    if not source_auth.is_file():
        raise CliError(f"codex account auth path is not a file: {source_auth}")

    destination_auth = _resolve_codex_auth_path(codex_home=codex_home)
    if destination_auth.is_symlink():
        current_target = _read_symlink_target(destination_auth)
        if current_target == source_auth:
            return (source_auth, destination_auth)
    elif destination_auth.exists():
        raise CliError(
            "refusing to replace non-symlink codex auth file: "
            f"{destination_auth}; move it under {source_auth.parent} or replace it manually"
        )

    if mutate:
        _replace_path_with_symlink(path=destination_auth, target=source_auth)
    return (source_auth, destination_auth)


def _normalize_codex_passthrough_args(raw_args: list[str]) -> list[str]:
    if raw_args and raw_args[0] == "--":
        return raw_args[1:]
    return raw_args


def _build_codex_command(*, config: CodexMuxConfig, codex_args: list[str]) -> list[str]:
    return [config.executable, *config.base_args, *codex_args]


def _format_codex_command(command: list[str], *, env_overrides: dict[str, str]) -> str:
    env_prefix = " ".join(
        f"{key}={shlex.quote(value)}"
        for key, value in sorted(env_overrides.items())
    )
    if not env_prefix:
        return shlex.join(command)
    return f"{env_prefix} {shlex.join(command)}"


def _cmd_codex(args: argparse.Namespace) -> int:
    config = _load_codex_mux_config()
    codex_home = _resolve_codex_home(args, config=config)
    codex_args = _normalize_codex_passthrough_args(list(args.codex_args))

    if args.just_link and args.account is None:
        raise CliError("--just-link requires --account")
    if args.just_link and codex_args:
        raise CliError("--just-link does not accept forwarded Codex arguments")

    if args.account is not None:
        source_auth, destination_auth = _link_codex_auth_for_account(
            args.account,
            codex_home=codex_home,
            config=config,
            mutate=not args.dry_run,
        )
    else:
        source_auth = None
        destination_auth = None

    if args.just_link:
        if args.dry_run and source_auth is not None and destination_auth is not None:
            print(f"link {destination_auth} -> {source_auth}")
        return 0

    command = _build_codex_command(
        config=config,
        codex_args=codex_args,
    )
    env = os.environ.copy()
    env[CODEX_HOME_ENV_VAR] = str(codex_home)

    if args.dry_run:
        if source_auth is not None and destination_auth is not None:
            print(f"link {destination_auth} -> {source_auth}")
        print(_format_codex_command(command, env_overrides={CODEX_HOME_ENV_VAR: str(codex_home)}))
        return 0

    try:
        result = subprocess.run(
            command,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliError(f"codex executable not found: {exc.filename}") from exc
    return int(result.returncode)


def register_codex_commands(subparsers: argparse._SubParsersAction) -> None:
    codex_parser = subparsers.add_parser(
        "codex",
        help="Launch Codex with an explicit CODEX_HOME and optional managed auth.json symlink switching.",
    )
    codex_parser.add_argument(
        "--account",
        default=None,
        help="Managed Codex account id under codex.mux.accounts_root/<account>/auth.json.",
    )
    codex_parser.add_argument(
        "--home",
        default=None,
        help=(
            "Raw CODEX_HOME path override. Defaults to codex.mux.default_home, "
            "codex.mux.default_instance_id, or ~/.codex."
        ),
    )
    codex_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the auth link action and full launched command without mutating or running Codex.",
    )
    codex_parser.add_argument(
        "--just-link",
        action="store_true",
        help="Only switch the managed auth.json symlink for the selected account and exit without launching Codex.",
    )
    codex_parser.add_argument(
        "codex_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to Codex. Use -- before Codex flags.",
    )
    codex_parser.set_defaults(handler=_cmd_codex)
