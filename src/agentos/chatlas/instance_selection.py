# $kw: --from Provider.Instance
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from agentos._core.errors import CliError
from agentos._core.project import agentos_home_dir
from agentos.agent.config import load_chat_config_documents
from agentos.agent.primitives import AgentConfig
from agentos.agent.providers.registry import agent_from_config
from agentos.chatlas.provider_home_adapter import ChatlasProviderInstance
from agentos.chatlas.path_hygiene import is_relative_to, path_has_symlink_component
from agentos.chatlas.providers import supported_chatlas_provider_families
from agentos.chatlas.raw_archive import (
    RAW_PARTITION_MANIFEST_FILENAME,
    _load_raw_partition_manifest,
    _raw_partition_manifest_string,
)


@dataclass(frozen=True)
class ChatlasSource:
    provider: str
    home: Path
    fingerprint: str
    scannable: bool = True


def selected_provider_instances(
    *,
    providers: tuple[str, ...] | None,
    start_path: Path | str,
) -> tuple[ChatlasProviderInstance, ...]:
    sources = tuple(
        source
        for source in _load_chatlas_sources(start_path=start_path)
        if source.scannable
    )
    if providers is not None:
        provider_filter = set(providers)
        sources = tuple(source for source in sources if source.provider in provider_filter)

    deduped: dict[tuple[str, str], ChatlasProviderInstance] = {}
    for source in sources:
        agent = agent_from_config(
            AgentConfig(
                provider=source.provider,
                home=source.home,
                homes=(source.home,),
                fingerprint_override=source.fingerprint,
            )
        )
        instance = ChatlasProviderInstance(
            agent=agent,
            fingerprint=source.fingerprint,
            source_home=str(source.home),
        )
        deduped[(instance.provider, instance.fingerprint)] = instance
    return tuple(sorted(deduped.values(), key=lambda instance: (instance.provider, instance.instance)))


def _load_chatlas_sources(*, start_path: Path | str) -> tuple[ChatlasSource, ...]:
    result: tuple[ChatlasSource, ...] = ()
    for config in load_chat_config_documents(start_path=start_path):
        chatlas_config = config.get("chatlas")
        if not isinstance(chatlas_config, dict) or "sources" not in chatlas_config:
            continue
        result = _load_chatlas_sources_value(chatlas_config["sources"])
    return result


def _load_chatlas_sources_value(value: object) -> tuple[ChatlasSource, ...]:
    if not isinstance(value, list):
        raise CliError("chatlas.sources must be a JSON array")
    supported = {
        provider_family.family
        for provider_family in supported_chatlas_provider_families()
    }
    sources: list[ChatlasSource] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise CliError(f"chatlas.sources[{index}] must be an object")
        provider = _required_source_string(item, "provider", index=index)
        if provider not in supported:
            raise CliError(f"unsupported Chatlas source provider: {provider}")
        raw_home = Path(_required_source_string(item, "home", index=index)).expanduser()
        scannable = item.get("scannable", True)
        if type(scannable) is not bool:
            raise CliError(f"chatlas.sources[{index}].scannable must be a boolean")
        _validate_source_home(raw_home, index=index)
        home = raw_home.resolve()
        key = (provider, str(home))
        if key in seen:
            raise CliError(f"chatlas.sources must be unique; duplicate source provider={provider} home={home}")
        seen.add(key)
        sources.append(
            ChatlasSource(
                provider=provider,
                home=home,
                fingerprint=_source_fingerprint(provider=provider, home=home),
                scannable=scannable,
            )
        )
    return tuple(sources)


def _required_source_string(item: dict[str, object], field: str, *, index: int) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"chatlas.sources[{index}].{field} is required")
    return value.strip()


def _validate_source_home(home: Path, *, index: int) -> None:
    system_homes_root = agentos_home_dir() / "agent" / "homes"
    if is_relative_to(home.resolve(), system_homes_root.resolve()):
        raise CliError(
            f"chatlas.sources[{index}].home must not use Agentos-managed system homes"
        )
    if path_has_symlink_component(home):
        raise CliError(
            f"chatlas.sources[{index}].home must not contain symlink components"
        )


def _source_fingerprint(*, provider: str, home: Path) -> str:
    digest = hashlib.sha256()
    digest.update(provider.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(home).encode("utf-8"))
    return digest.hexdigest()


def archived_provider_instances(
    *,
    raw_root: Path,
    providers: tuple[str, ...] | None,
) -> tuple[ChatlasProviderInstance, ...]:
    if not raw_root.is_dir():
        return ()
    provider_filter = set(providers) if providers is not None else None
    instances: list[ChatlasProviderInstance] = []
    for provider_dir in sorted(path for path in raw_root.iterdir() if path.is_dir()):
        provider = unquote(provider_dir.name)
        if provider_filter is not None and provider not in provider_filter:
            continue
        for partition_dir in sorted(path for path in provider_dir.iterdir() if path.is_dir()):
            fingerprint = unquote(partition_dir.name)
            manifest = _load_raw_partition_manifest(partition_dir / RAW_PARTITION_MANIFEST_FILENAME)
            agent = _agent_from_raw_partition(
                provider=provider,
                fingerprint=fingerprint,
                partition_dir=partition_dir,
                manifest=manifest,
            )
            if agent is None:
                continue
            instances.append(
                ChatlasProviderInstance(
                    agent=agent,
                    fingerprint=fingerprint,
                    source_home=_raw_partition_manifest_string(manifest, "home"),
                )
            )
    return tuple(sorted(instances, key=lambda instance: (instance.provider, instance.instance)))


def _agent_from_raw_partition(
    *,
    provider: str,
    fingerprint: str,
    partition_dir: Path,
    manifest: dict[str, Any] | None,
) -> AgentConfig | None:
    raw_home = partition_dir / "home"
    raw_paths = partition_dir / "paths"
    home = raw_home if raw_home.is_dir() else None
    instance_id = _raw_partition_manifest_string(manifest, "instance")
    direct_targets: tuple[Path, ...] = ()
    if home is None and raw_paths.is_dir():
        direct_targets = tuple(sorted(path for path in raw_paths.rglob("*") if path.is_file()))
    if home is None and not direct_targets:
        return None
    return agent_from_config(
        AgentConfig(
            provider=provider,
            profile_id=instance_id,
            label=None,
            home=home,
            direct_targets=direct_targets,
            sqlite_db_paths=(),
            is_default=False,
            fingerprint_override=fingerprint,
        )
    )
