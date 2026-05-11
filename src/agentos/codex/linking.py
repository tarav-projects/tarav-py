from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir, global_config_path, load_global_config
from agentos.agent.config import (
    AGENT_INSTANCE_CONFIG_SOURCE,
    agent_config_entries_from_config,
    agent_config_from_config_entry,
)
from agentos.agent.link_runtime import AgentLinkDryResult, AgentLinkRequest, AgentLinkResult
from agentos.agent.primitives import AgentConfig

CODEX_AUTH_FILENAME = "auth.json"
CODEX_DEFAULT_EXECUTABLE = "/opt/homebrew/bin/codex"
CODEX_DEFAULT_HOME_DIRNAME = ".codex"
CODEX_DEFAULT_BASE_ARGS = ("--dangerously-bypass-approvals-and-sandbox",)
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


def normalize_codex_path_value(value: object, *, field_name: str) -> Path:
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


def resolve_codex_mux_default_instance(
    raw_default_instance_id: object,
    *,
    config: dict[str, object],
):
    from agentos.codex.agent import CodexAgent

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


def _resolve_codex_mux_instance_home(instance) -> Path:
    if instance.home is None:
        raise CliError(
            f"agent.instances entry {instance.instance_id!r} for provider codex "
            "must define home for codex.mux.default_instance_id"
        )
    return instance.home


def _resolve_codex_mux_instance_executable(instance) -> str:
    if not instance.cli_command:
        raise CliError(
            f"agent.instances entry {instance.instance_id!r} for provider codex "
            "must define cli_command for codex.mux.default_instance_id"
        )
    return instance.cli_command[0]


def _resolve_codex_mux_instance_base_args(instance) -> tuple[str, ...]:
    cli_tail = instance.cli_command[1:] if len(instance.cli_command) > 1 else ()
    return (*cli_tail, *instance.run_args)


def load_codex_mux_config() -> CodexMuxConfig:
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
    default_instance = None
    if raw_default_instance_id is not None:
        default_instance = resolve_codex_mux_default_instance(
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
        default_home = normalize_codex_path_value(raw_default_home, field_name="codex.mux.default_home")

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
        accounts_root=normalize_codex_path_value(raw_accounts_root, field_name="codex.mux.accounts_root"),
        executable=executable,
        base_args=base_args,
    )


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


def link_codex_auth_for_account(
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


def link_codex_account(request: AgentLinkRequest) -> AgentLinkResult:
    link_codex_auth_for_account(
        request.account,
        codex_home=request.home,
        config=load_codex_mux_config(),
        mutate=True,
    )
    return AgentLinkResult()


def link_codex_account_dry(request: AgentLinkRequest) -> AgentLinkDryResult:
    source_auth, destination_auth = link_codex_auth_for_account(
        request.account,
        codex_home=request.home,
        config=load_codex_mux_config(),
        mutate=False,
    )
    return AgentLinkDryResult(lines=(f"link {destination_auth} -> {source_auth}",))


__all__ = [
    "CODEX_AUTH_FILENAME",
    "CODEX_DEFAULT_BASE_ARGS",
    "CODEX_DEFAULT_EXECUTABLE",
    "CODEX_DEFAULT_HOME_DIRNAME",
    "CODEX_MANAGED_ACCOUNTS_DIR",
    "CODEX_MUX_CONFIG_PATH",
    "CodexMuxConfig",
    "link_codex_account",
    "link_codex_account_dry",
    "link_codex_auth_for_account",
    "load_codex_mux_config",
    "normalize_codex_path_value",
    "resolve_codex_mux_default_instance",
]
