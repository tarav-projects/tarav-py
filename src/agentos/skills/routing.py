from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import (
    agentos_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    local_storage_paths,
    load_project_config,
    project_config_path,
)
from agentos.utils.skills import (
    DiscoveredSkill,
    SkillsImport,
    SkillsSyncResult,
    discover_imported_skills,
    parse_skill_frontmatter,
)

DEFAULT_ROUTED_SKILLS_DEPOTS = (
    ".agents/skills",
    ".claude/skills",
)
LOCAL_AGENTS_DIRNAME = ".agents"
DEFAULT_ROUTED_PROFILE_NAME = "default"
ROUTED_SKILLS_STATE_FILENAME = "skills-routing-links.json"
ROUTED_SKILLS_STATE_CLASS = "agentos.skills.routing-state"
ROUTED_SKILLS_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SkillsRoutingSource:
    name: str
    path_text: str | None
    package_payload: object | None
    enabled: bool


@dataclass(frozen=True)
class SkillsRoutingProfile:
    name: str
    depots_payload: object | None
    sources_payload: object


@dataclass(frozen=True)
class RoutedSkillsSelection:
    caller_root: Path
    local_context_root: Path | None
    profile_name: str | None
    depot_roots: tuple[Path, ...]
    sources: list[SkillsImport]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutedSkillRecord:
    name: str
    description: str
    source: str
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class RoutedSkillsDepotImportResult:
    depot_root: Path
    sync_result: SkillsSyncResult


@dataclass(frozen=True)
class RoutedSkillsImportResult:
    selection: RoutedSkillsSelection
    skills: list[RoutedSkillRecord]
    depot_results: tuple[RoutedSkillsDepotImportResult, ...]


@dataclass(frozen=True)
class RoutedSkillsStatusEntry:
    name: str
    path: Path
    source: str | None
    expected_source_path: Path | None
    actual_entry_kind: str | None
    actual_link_target: str | None
    actual_resolved_target: Path | None


@dataclass(frozen=True)
class RoutedSkillsDepotStatusResult:
    depot_root: Path
    matching: list[RoutedSkillsStatusEntry]
    missing: list[RoutedSkillsStatusEntry]
    broken: list[RoutedSkillsStatusEntry]
    unsynced: list[RoutedSkillsStatusEntry]
    conflicts: list[RoutedSkillsStatusEntry]
    extra: list[RoutedSkillsStatusEntry]


@dataclass(frozen=True)
class _RoutedSkillsDepotSyncPlan:
    caller_root: Path
    depot_root: Path
    target_key: str
    create_specs: tuple[tuple[Path, str], ...]
    update_specs: tuple[tuple[Path, str], ...]
    remove_specs: tuple[Path, ...]
    matching_links: tuple[Path, ...]
    final_links: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RoutedSkillsStatusResult:
    selection: RoutedSkillsSelection
    skills: list[RoutedSkillRecord]
    depot_statuses: tuple[RoutedSkillsDepotStatusResult, ...]


def _parse_enabled_flag(payload: dict[str, object], *, field_label: str) -> bool:
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise CliError(f"{field_label}.enabled must be a boolean")
    return enabled


def _classify_source_item(
    payload: dict[str, object],
    *,
    field_label: str,
    require_target: bool,
) -> tuple[bool, bool]:
    has_path = "path" in payload
    has_package = "package" in payload
    if require_target:
        if has_path == has_package:
            raise CliError(f"{field_label} must define exactly one of path or package")
    elif has_path and has_package:
        raise CliError(f"{field_label} must define exactly one of path or package")
    return has_path, has_package


def _require_source_name(payload: dict[str, object], *, field_label: str) -> str:
    return validate_string_for_path(
        payload.get("name", ""),
        field_name=f"{field_label}.name",
    )


def _require_source_path_text(
    payload: dict[str, object],
    *,
    field_label: str,
    empty_error_suffix: str = "must not be empty",
) -> str:
    path_text = str(payload.get("path", "")).strip()
    if not path_text:
        raise CliError(f"{field_label}.path {empty_error_suffix}")
    return path_text


def resolve_routed_skills_caller_root(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> Path:
    if project is not None:
        current = Path(project).expanduser().resolve()
    else:
        project_root = find_agentos_project_root(start_path)
        if project_root is not None:
            return project_root.resolve()
        current = Path(start_path).expanduser().resolve()

    if current.is_file():
        return current.parent
    return current


def _resolve_local_agents_context_root(start_path: Path | str = ".") -> Path | None:
    current = Path(start_path).expanduser().resolve()
    if current.is_file():
        current = current.parent

    ignored_global_agents_root = (Path.home().expanduser().resolve() / LOCAL_AGENTS_DIRNAME).resolve()

    while True:
        candidate = current / LOCAL_AGENTS_DIRNAME
        try:
            normalized_candidate = candidate.resolve()
        except OSError:
            normalized_candidate = candidate
        if candidate.is_dir() and normalized_candidate != ignored_global_agents_root:
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _load_routing_section() -> dict[str, object]:
    config_path = global_config_path()
    if not config_path.exists():
        return {}

    payload = load_global_config(config_path)
    skills_section = payload.get("skills")
    if skills_section is None:
        return {}
    if not isinstance(skills_section, dict):
        raise CliError("global config field skills must be a JSON object")

    routing = skills_section.get("routing")
    if routing is None:
        return {}
    if not isinstance(routing, dict):
        raise CliError("global config field skills.routing must be a JSON object")
    return routing


def _parse_default_profile_name(payload: object) -> str | None:
    if payload is None:
        return None
    if not isinstance(payload, str):
        raise CliError("global config field skills.routing.default_profile must be a string")
    normalized_name = payload.strip()
    if not normalized_name:
        raise CliError("global config field skills.routing.default_profile must not be empty")
    return validate_string_for_path(normalized_name, field_name="routing default profile name")


def _parse_routing_sources_registry(payload: object) -> dict[str, SkillsRoutingSource]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise CliError("global config field skills.routing.sources must be an object")

    registry: dict[str, SkillsRoutingSource] = {}
    for raw_name, raw_entry in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise CliError("global config field skills.routing.sources keys must be non-empty strings")
        name = validate_string_for_path(raw_name, field_name="routing source name")
        if not isinstance(raw_entry, dict):
            raise CliError(f"global config field skills.routing.sources.{name} must be an object")

        item_label = f"global config field skills.routing.sources.{name}"
        enabled = _parse_enabled_flag(raw_entry, field_label=item_label)
        has_path, _ = _classify_source_item(
            raw_entry,
            field_label=item_label,
            require_target=True,
        )

        if has_path:
            path_text = _require_source_path_text(
                raw_entry,
                field_label=item_label,
                empty_error_suffix="is required",
            )
            registry[name] = SkillsRoutingSource(
                name=name,
                path_text=path_text,
                package_payload=None,
                enabled=enabled,
            )
            continue

        registry[name] = SkillsRoutingSource(
            name=name,
            path_text=None,
            package_payload=raw_entry.get("package"),
            enabled=enabled,
        )

    return registry


def _parse_routing_profiles(payload: object) -> dict[str, SkillsRoutingProfile]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise CliError("global config field skills.routing.profiles must be an object")

    profiles: dict[str, SkillsRoutingProfile] = {}
    for raw_name, raw_profile in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise CliError("global config field skills.routing.profiles keys must be non-empty strings")
        name = validate_string_for_path(raw_name, field_name="routing profile name")
        if not isinstance(raw_profile, dict):
            raise CliError(f"global config field skills.routing.profiles.{name} must be an object")

        if "skill_depot" in raw_profile:
            raise CliError(
                f"global config field skills.routing.profiles.{name}.skill_depot is no longer supported; use depots"
            )
        if "packages" in raw_profile:
            raise CliError(
                f"global config field skills.routing.profiles.{name}.packages is no longer supported; use sources"
            )
        if "imports" in raw_profile:
            raise CliError(
                f"global config field skills.routing.profiles.{name}.imports is no longer supported; use sources"
            )

        profiles[name] = SkillsRoutingProfile(
            name=name,
            depots_payload=raw_profile.get("depots"),
            sources_payload=raw_profile.get("sources", []),
        )

    return profiles


def _load_routing_configuration() -> tuple[
    dict[str, SkillsRoutingProfile],
    dict[str, SkillsRoutingSource],
    str | None,
]:
    routing = _load_routing_section()
    if "imports_registry" in routing:
        raise CliError("global config field skills.routing.imports_registry is no longer supported; use sources")
    if "packages" in routing:
        raise CliError("global config field skills.routing.packages is no longer supported; use sources")

    profiles = _parse_routing_profiles(routing.get("profiles"))
    sources_registry = _parse_routing_sources_registry(routing.get("sources"))
    default_profile_name = _parse_default_profile_name(routing.get("default_profile"))

    if default_profile_name is not None and default_profile_name not in profiles:
        raise CliError(f"routing default profile references unknown profile: {default_profile_name}")

    return profiles, sources_registry, default_profile_name


def _resolve_source_root(path_text: str, *, base_root: Path, field_name: str) -> Path:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = base_root / candidate
    resolved = candidate.resolve()
    if not resolved.exists():
        raise CliError(f"{field_name} path does not exist: {resolved}")
    if not resolved.is_dir():
        raise CliError(f"{field_name} path is not a directory: {resolved}")
    return resolved


def _append_direct_source(
    name: str,
    path_text: str,
    *,
    base_root: Path,
    field_name: str,
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
) -> None:
    if name in seen_names:
        raise CliError(f"duplicate enabled routing source name: {name}")

    resolved_sources.append(
        SkillsImport(
            name=name,
            root=_resolve_source_root(
                path_text,
                base_root=base_root,
                field_name=field_name,
            ),
            configured_path=path_text,
        )
    )
    seen_names.add(name)


def _append_sources_from_registry_reference(
    source_name: str,
    *,
    sources_registry: dict[str, SkillsRoutingSource],
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    registry_stack: tuple[str, ...],
) -> None:
    registry_entry = sources_registry.get(source_name)
    if registry_entry is None:
        raise CliError(f"routing source references unknown registry source: {source_name}")
    if not registry_entry.enabled:
        return
    if source_name in registry_stack:
        cycle = " -> ".join([*registry_stack, source_name])
        raise CliError(f"routing source cycle detected: {cycle}")

    if registry_entry.path_text is not None:
        _append_direct_source(
            registry_entry.name,
            registry_entry.path_text,
            base_root=agentos_home_dir(),
            field_name=f"global config field skills.routing.sources.{registry_entry.name}",
            seen_names=seen_names,
            resolved_sources=resolved_sources,
        )
        return

    _append_sources_from_payload(
        registry_entry.package_payload,
        payload_label=f"global config field skills.routing.sources.{registry_entry.name}.package",
        inline_base_root=agentos_home_dir(),
        sources_registry=sources_registry,
        seen_names=seen_names,
        resolved_sources=resolved_sources,
        registry_stack=(*registry_stack, source_name),
    )


def _append_sources_from_payload(
    payload: object,
    *,
    payload_label: str,
    inline_base_root: Path,
    sources_registry: dict[str, SkillsRoutingSource],
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    registry_stack: tuple[str, ...] = (),
) -> None:
    if not isinstance(payload, list):
        raise CliError(f"{payload_label} must be an array")

    for index, item in enumerate(payload):
        item_label = f"{payload_label}[{index}]"
        if not isinstance(item, dict):
            raise CliError(f"{item_label} must be an object")

        enabled = _parse_enabled_flag(item, field_label=item_label)
        if not enabled:
            continue

        has_path, has_package = _classify_source_item(
            item,
            field_label=item_label,
            require_target=False,
        )

        if has_path:
            name = _require_source_name(item, field_label=item_label)
            path_text = _require_source_path_text(item, field_label=item_label)
            _append_direct_source(
                name,
                path_text,
                base_root=inline_base_root,
                field_name=item_label,
                seen_names=seen_names,
                resolved_sources=resolved_sources,
            )
            continue

        if has_package:
            _append_sources_from_payload(
                item.get("package"),
                payload_label=f"{item_label}.package",
                inline_base_root=inline_base_root,
                sources_registry=sources_registry,
                seen_names=seen_names,
                resolved_sources=resolved_sources,
                registry_stack=registry_stack,
            )
            continue

        source_name = _require_source_name(item, field_label=item_label)
        _append_sources_from_registry_reference(
            source_name,
            sources_registry=sources_registry,
            seen_names=seen_names,
            resolved_sources=resolved_sources,
            registry_stack=registry_stack,
        )


def _resolve_profile_sources(
    profile: SkillsRoutingProfile,
    *,
    sources_registry: dict[str, SkillsRoutingSource],
    caller_root: Path,
) -> list[SkillsImport]:
    resolved_sources: list[SkillsImport] = []
    seen_names: set[str] = set()

    _append_sources_from_payload(
        profile.sources_payload,
        payload_label=f"global config field skills.routing.profiles.{profile.name}.sources",
        inline_base_root=caller_root,
        sources_registry=sources_registry,
        seen_names=seen_names,
        resolved_sources=resolved_sources,
    )

    return resolved_sources


def _resolve_profile_depots(profile: SkillsRoutingProfile, caller_root: Path) -> tuple[Path, ...]:
    depots_payload = profile.depots_payload
    configured_depots = DEFAULT_ROUTED_SKILLS_DEPOTS if depots_payload is None else depots_payload

    if not isinstance(configured_depots, list | tuple):
        raise CliError(f"global config field skills.routing.profiles.{profile.name}.depots must be an array")
    if not configured_depots:
        raise CliError(
            f"global config field skills.routing.profiles.{profile.name}.depots must not be empty"
        )

    resolved_depots: list[Path] = []
    seen_roots: set[Path] = set()
    for index, item in enumerate(configured_depots):
        item_label = f"global config field skills.routing.profiles.{profile.name}.depots[{index}]"
        if not isinstance(item, str):
            raise CliError(f"{item_label} must be a string")
        depot_text = item.strip()
        if not depot_text:
            raise CliError(f"{item_label} must not be empty")

        candidate = Path(depot_text).expanduser()
        if candidate.is_absolute():
            raise CliError(f"{item_label} must be a relative project path")

        resolved_candidate = (caller_root / candidate).resolve()
        try:
            resolved_candidate.relative_to(caller_root)
        except ValueError as exc:
            raise CliError(f"{item_label} must stay inside the project root: {caller_root}") from exc

        if resolved_candidate in seen_roots:
            raise CliError(f"duplicate resolved routing depot path: {resolved_candidate}")
        seen_roots.add(resolved_candidate)
        resolved_depots.append(resolved_candidate)

    return tuple(resolved_depots)


def _load_local_routing_profile_name(context_root: Path) -> tuple[str | None, tuple[str, ...]]:
    config_path = project_config_path(context_root)
    if not config_path.exists():
        return None, ()
    try:
        if config_path.resolve() == global_config_path().resolve():
            return (
                None,
                (
                    (
                        f"ignoring local project config {config_path} because it resolves to the "
                        f"global config {global_config_path()}"
                    ),
                ),
            )
    except OSError:
        pass

    payload = load_project_config(config_path)
    skills_section = payload.get("skills")
    if skills_section is None:
        return None, ()
    if not isinstance(skills_section, dict):
        raise CliError("project config field skills must be a JSON object")

    routing = skills_section.get("routing")
    if routing is None:
        return None, ()
    if not isinstance(routing, dict):
        raise CliError("project config field skills.routing must be a JSON object")

    profile_value = routing.get("profile")
    if profile_value is None:
        return None, ()
    if not isinstance(profile_value, str):
        raise CliError("project config field skills.routing.profile must be a string")

    normalized_name = profile_value.strip()
    if not normalized_name:
        raise CliError("project config field skills.routing.profile must not be empty")
    return (
        validate_string_for_path(normalized_name, field_name="project routing profile name"),
        (),
    )


def resolve_routed_skills_selection(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> RoutedSkillsSelection:
    raw_start_root = Path(start_path).expanduser().resolve()
    if raw_start_root.is_file():
        raw_start_root = raw_start_root.parent

    resolved_start_root = resolve_routed_skills_caller_root(start_path, project=project)
    if project is not None:
        local_context_root = resolved_start_root
    else:
        local_context_root = _resolve_local_agents_context_root(raw_start_root)
        if local_context_root is None:
            local_context_root = find_agentos_project_root(raw_start_root)
    profiles, sources_registry, default_profile_name = _load_routing_configuration()

    if local_context_root is None:
        return RoutedSkillsSelection(
            caller_root=raw_start_root,
            local_context_root=None,
            profile_name=None,
            depot_roots=(),
            sources=[],
            warnings=(),
        )

    local_profile_name, selection_warnings = _load_local_routing_profile_name(local_context_root)
    selected_profile_name = local_profile_name or default_profile_name or DEFAULT_ROUTED_PROFILE_NAME

    profile = profiles.get(selected_profile_name)
    if profile is None:
        if local_profile_name is not None:
            raise CliError(f"routing profile not found: {selected_profile_name}")
        return RoutedSkillsSelection(
            caller_root=local_context_root,
            local_context_root=local_context_root,
            profile_name=None,
            depot_roots=(),
            sources=[],
            warnings=selection_warnings,
        )

    return RoutedSkillsSelection(
        caller_root=local_context_root,
        local_context_root=local_context_root,
        profile_name=profile.name,
        depot_roots=_resolve_profile_depots(profile, local_context_root),
        sources=_resolve_profile_sources(
            profile,
            sources_registry=sources_registry,
            caller_root=local_context_root,
        ),
        warnings=selection_warnings,
    )


def _routed_skills_state_path(caller_root: Path) -> Path:
    return local_storage_paths(caller_root)["state"] / ROUTED_SKILLS_STATE_FILENAME


def _state_target_key(base_root: Path, target_dir: Path) -> str:
    normalized_base_root = base_root.expanduser().resolve()
    normalized_target_dir = target_dir.expanduser().resolve()
    try:
        relative = normalized_target_dir.relative_to(normalized_base_root)
    except ValueError:
        return str(normalized_target_dir)
    return relative.as_posix() or "."


def _relative_symlink_target(link_path: Path, source_path: Path) -> str:
    return os.path.relpath(source_path, start=link_path.parent)


def _resolved_symlink_target(path: Path) -> Path:
    link_target = Path(os.readlink(path))
    if link_target.is_absolute():
        return link_target.resolve()
    return (path.parent / link_target).resolve()


def _list_visible_depot_entries(depot_root: Path) -> list[Path]:
    normalized_depot_root = depot_root.expanduser().resolve()
    if not normalized_depot_root.exists():
        return []
    if not normalized_depot_root.is_dir():
        raise CliError(f"routed skills depot is not a directory: {normalized_depot_root}")

    return sorted(
        [
            child
            for child in normalized_depot_root.iterdir()
            if not child.name.startswith(".")
        ],
        key=lambda path: path.name,
    )


def _entry_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


def _load_routed_skills_state(caller_root: Path) -> dict[str, dict[str, str]]:
    state_path = _routed_skills_state_path(caller_root)
    if not state_path.exists():
        return {}
    if not state_path.is_file():
        raise CliError(f"routed skills state path is not a file: {state_path}")

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid routed skills state JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise CliError("routed skills state must be a JSON object")
    if payload.get("class") != ROUTED_SKILLS_STATE_CLASS:
        raise CliError(f"routed skills state field class must be '{ROUTED_SKILLS_STATE_CLASS}'")

    targets_payload = payload.get("targets", {})
    if not isinstance(targets_payload, dict):
        raise CliError("routed skills state field targets must be an object")

    state: dict[str, dict[str, str]] = {}
    for target_key, target_payload in targets_payload.items():
        if not isinstance(target_key, str) or not target_key:
            raise CliError("routed skills state target keys must be non-empty strings")
        if not isinstance(target_payload, dict):
            raise CliError(f"routed skills state target payload must be an object: {target_key}")
        links_payload = target_payload.get("links", {})
        if not isinstance(links_payload, dict):
            raise CliError(f"routed skills state target links must be an object: {target_key}")

        links: dict[str, str] = {}
        for skill_name, link_target in links_payload.items():
            if not isinstance(skill_name, str) or not skill_name:
                raise CliError(f"routed skills state skill names must be non-empty strings: {target_key}")
            if not isinstance(link_target, str) or not link_target:
                raise CliError(
                    f"routed skills state link targets must be non-empty strings: {target_key}/{skill_name}"
                )
            links[skill_name] = link_target
        state[target_key] = links

    return state


def _write_routed_skills_state(caller_root: Path, state: dict[str, dict[str, str]]) -> None:
    state_path = _routed_skills_state_path(caller_root)
    normalized_state = {target_key: links for target_key, links in state.items() if links}

    if not normalized_state:
        if state_path.exists():
            state_path.unlink()
        return

    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "class": ROUTED_SKILLS_STATE_CLASS,
        "schema_version": ROUTED_SKILLS_STATE_SCHEMA_VERSION,
        "targets": {
            target_key: {"links": dict(sorted(links.items()))}
            for target_key, links in sorted(normalized_state.items())
        },
    }
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _plan_routed_profile_depot_sync(
    caller_root: Path,
    depot_root: Path,
    discovered: list[DiscoveredSkill],
    *,
    force: bool = False,
) -> _RoutedSkillsDepotSyncPlan:
    normalized_caller_root = caller_root.expanduser().resolve()
    normalized_depot_root = depot_root.expanduser().resolve()
    if normalized_depot_root.exists() and not normalized_depot_root.is_dir():
        raise CliError(f"routed skills depot is not a directory: {normalized_depot_root}")

    state = _load_routed_skills_state(normalized_caller_root)
    target_key = _state_target_key(normalized_caller_root, normalized_depot_root)
    previous_links = state.get(target_key, {})

    create_specs: list[tuple[Path, str]] = []
    update_specs: list[tuple[Path, str]] = []
    remove_specs: list[Path] = []
    matching_links: list[Path] = []
    final_links: dict[str, str] = {}
    desired_names: set[str] = set()
    conflicts: list[tuple[Path, str]] = []

    if force:
        if normalized_depot_root.exists():
            remove_specs = sorted(
                [
                    child
                    for child in normalized_depot_root.iterdir()
                    if child.is_symlink()
                ],
                key=lambda path: path.name,
            )

        for skill in discovered:
            desired_names.add(skill.name)
            link_path = normalized_depot_root / skill.name
            desired_source = skill.source_path.resolve()
            desired_link_target = _relative_symlink_target(link_path, desired_source)

            if link_path.exists() and not link_path.is_symlink():
                conflicts.append((link_path, desired_source.as_posix()))
                continue

            create_specs.append((link_path, desired_link_target))
            final_links[skill.name] = desired_link_target
    else:
        for skill in discovered:
            desired_names.add(skill.name)
            link_path = normalized_depot_root / skill.name
            desired_source = skill.source_path.resolve()
            desired_link_target = _relative_symlink_target(link_path, desired_source)

            if link_path.exists() or link_path.is_symlink():
                if link_path.is_symlink():
                    actual_link_target = os.readlink(link_path)
                    if _resolved_symlink_target(link_path) == desired_source:
                        matching_links.append(link_path)
                        final_links[skill.name] = actual_link_target
                        continue
                    if previous_links.get(skill.name) == actual_link_target:
                        update_specs.append((link_path, desired_link_target))
                        final_links[skill.name] = desired_link_target
                        continue
                conflicts.append((link_path, desired_source.as_posix()))
                continue

            create_specs.append((link_path, desired_link_target))
            final_links[skill.name] = desired_link_target

        for skill_name, previous_link_target in previous_links.items():
            if skill_name in desired_names:
                continue
            link_path = normalized_depot_root / skill_name
            if not link_path.is_symlink():
                continue
            if os.readlink(link_path) == previous_link_target:
                remove_specs.append(link_path)

    if conflicts:
        conflict_entries = ", ".join(
            f"{path} (expected link to {source_path})" for path, source_path in conflicts
        )
        raise CliError(f"routed skills sync found conflicting existing paths: {conflict_entries}")

    return _RoutedSkillsDepotSyncPlan(
        caller_root=normalized_caller_root,
        depot_root=normalized_depot_root,
        target_key=target_key,
        create_specs=tuple(create_specs),
        update_specs=tuple(update_specs),
        remove_specs=tuple(remove_specs),
        matching_links=tuple(matching_links),
        final_links=tuple(sorted(final_links.items())),
    )


def _apply_routed_profile_depot_sync(plan: _RoutedSkillsDepotSyncPlan) -> SkillsSyncResult:
    if plan.create_specs or plan.update_specs:
        plan.depot_root.mkdir(parents=True, exist_ok=True)
    for link_path in plan.remove_specs:
        if link_path.is_symlink():
            link_path.unlink()
    for link_path, _ in plan.update_specs:
        link_path.unlink()
    for link_path, link_target in plan.create_specs + plan.update_specs:
        link_path.symlink_to(link_target, target_is_directory=True)

    state = _load_routed_skills_state(plan.caller_root)
    if plan.final_links:
        state[plan.target_key] = dict(plan.final_links)
    else:
        state.pop(plan.target_key, None)
    _write_routed_skills_state(plan.caller_root, state)

    return SkillsSyncResult(
        created_links=[path for path, _ in plan.create_specs],
        updated_links=[path for path, _ in plan.update_specs],
        removed_links=list(plan.remove_specs),
        matching_links=list(plan.matching_links),
    )


def _routed_records_from_discovered(
    selection: RoutedSkillsSelection,
    discovered: list[DiscoveredSkill],
) -> list[RoutedSkillRecord]:
    routed_skills: list[RoutedSkillRecord] = []
    for skill in discovered:
        frontmatter = parse_skill_frontmatter(skill.source_path)
        routed_skills.append(
            RoutedSkillRecord(
                name=skill.name,
                description=frontmatter.get("description", ""),
                source=skill.import_name,
                paths=tuple(depot_root / skill.name for depot_root in selection.depot_roots),
            )
        )

    routed_skills.sort(key=lambda item: item.name)
    return routed_skills


def _resolve_routed_skills_catalog(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[RoutedSkillsSelection, list[DiscoveredSkill], list[RoutedSkillRecord]]:
    selection = resolve_routed_skills_selection(start_path, project=project)
    discovered = discover_imported_skills(selection.sources)
    routed_skills = _routed_records_from_discovered(selection, discovered)
    return selection, discovered, routed_skills


def list_routed_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[RoutedSkillsSelection, list[RoutedSkillRecord]]:
    selection, _, routed_skills = _resolve_routed_skills_catalog(start_path, project=project)
    return selection, routed_skills


def _routed_skills_status_for_depot(
    depot_root: Path,
    *,
    routed_skills: list[RoutedSkillRecord],
    discovered_by_name: dict[str, DiscoveredSkill],
) -> RoutedSkillsDepotStatusResult:
    matching: list[RoutedSkillsStatusEntry] = []
    missing: list[RoutedSkillsStatusEntry] = []
    broken: list[RoutedSkillsStatusEntry] = []
    unsynced: list[RoutedSkillsStatusEntry] = []
    conflicts: list[RoutedSkillsStatusEntry] = []
    extra: list[RoutedSkillsStatusEntry] = []

    expected_names = {skill.name for skill in routed_skills}

    for skill in routed_skills:
        discovered_skill = discovered_by_name[skill.name]
        path = depot_root / skill.name
        expected_source_path = discovered_skill.source_path.resolve()

        if path.is_symlink():
            actual_link_target = os.readlink(path)
            if not path.exists():
                broken.append(
                    RoutedSkillsStatusEntry(
                        name=skill.name,
                        path=path,
                        source=skill.source,
                        expected_source_path=expected_source_path,
                        actual_entry_kind="symlink",
                        actual_link_target=actual_link_target,
                        actual_resolved_target=None,
                    )
                )
                continue

            actual_resolved_target = _resolved_symlink_target(path)
            if actual_resolved_target == expected_source_path:
                matching.append(
                    RoutedSkillsStatusEntry(
                        name=skill.name,
                        path=path,
                        source=skill.source,
                        expected_source_path=expected_source_path,
                        actual_entry_kind="symlink",
                        actual_link_target=actual_link_target,
                        actual_resolved_target=actual_resolved_target,
                    )
                )
                continue

            unsynced.append(
                RoutedSkillsStatusEntry(
                    name=skill.name,
                    path=path,
                    source=skill.source,
                    expected_source_path=expected_source_path,
                    actual_entry_kind="symlink",
                    actual_link_target=actual_link_target,
                    actual_resolved_target=actual_resolved_target,
                )
            )
            continue

        if path.exists():
            conflicts.append(
                RoutedSkillsStatusEntry(
                    name=skill.name,
                    path=path,
                    source=skill.source,
                    expected_source_path=expected_source_path,
                    actual_entry_kind=_entry_kind(path),
                    actual_link_target=None,
                    actual_resolved_target=None,
                )
            )
            continue

        missing.append(
            RoutedSkillsStatusEntry(
                name=skill.name,
                path=path,
                source=skill.source,
                expected_source_path=expected_source_path,
                actual_entry_kind=None,
                actual_link_target=None,
                actual_resolved_target=None,
            )
        )

    for path in _list_visible_depot_entries(depot_root):
        if path.name in expected_names:
            continue

        if path.is_symlink():
            actual_link_target = os.readlink(path)
            if not path.exists():
                broken.append(
                    RoutedSkillsStatusEntry(
                        name=path.name,
                        path=path,
                        source=None,
                        expected_source_path=None,
                        actual_entry_kind="symlink",
                        actual_link_target=actual_link_target,
                        actual_resolved_target=None,
                    )
                )
                continue

            extra.append(
                RoutedSkillsStatusEntry(
                    name=path.name,
                    path=path,
                    source=None,
                    expected_source_path=None,
                    actual_entry_kind="symlink",
                    actual_link_target=actual_link_target,
                    actual_resolved_target=_resolved_symlink_target(path),
                )
            )
            continue

        extra.append(
            RoutedSkillsStatusEntry(
                name=path.name,
                path=path,
                source=None,
                expected_source_path=None,
                actual_entry_kind=_entry_kind(path),
                actual_link_target=None,
                actual_resolved_target=None,
            )
        )

    return RoutedSkillsDepotStatusResult(
        depot_root=depot_root,
        matching=matching,
        missing=missing,
        broken=broken,
        unsynced=unsynced,
        conflicts=conflicts,
        extra=extra,
    )


def routed_skills_status(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> RoutedSkillsStatusResult:
    selection, discovered, routed_skills = _resolve_routed_skills_catalog(start_path, project=project)
    discovered_by_name = {skill.name: skill for skill in discovered}

    return RoutedSkillsStatusResult(
        selection=selection,
        skills=routed_skills,
        depot_statuses=tuple(
            _routed_skills_status_for_depot(
                depot_root,
                routed_skills=routed_skills,
                discovered_by_name=discovered_by_name,
            )
            for depot_root in selection.depot_roots
        ),
    )


def resolve_routed_skill(
    name: str,
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[RoutedSkillsSelection, RoutedSkillRecord | None]:
    normalized_name = validate_string_for_path(name, field_name="skill name")
    selection, routed_skills = list_routed_skills(start_path, project=project)
    for skill in routed_skills:
        if skill.name == normalized_name:
            return selection, skill
    return selection, None


def import_routed_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
    force: bool = False,
) -> RoutedSkillsImportResult:
    selection, discovered, routed_skills = _resolve_routed_skills_catalog(start_path, project=project)

    if not selection.depot_roots:
        return RoutedSkillsImportResult(
            selection=selection,
            skills=routed_skills,
            depot_results=(),
        )

    sync_plans = tuple(
        _plan_routed_profile_depot_sync(
            selection.caller_root,
            depot_root,
            discovered,
            force=force,
        )
        for depot_root in selection.depot_roots
    )

    return RoutedSkillsImportResult(
        selection=selection,
        skills=routed_skills,
        depot_results=tuple(
            RoutedSkillsDepotImportResult(
                depot_root=plan.depot_root,
                sync_result=_apply_routed_profile_depot_sync(plan),
            )
            for plan in sync_plans
        ),
    )
