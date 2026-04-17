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

DEFAULT_ROUTED_SKILLS_DEPOT = Path(".agents/skills")
LOCAL_AGENTS_DIRNAME = ".agents"
DEFAULT_ROUTED_PROFILE_NAME = "default"
ROUTED_SKILLS_STATE_FILENAME = "skills-routing-links.json"
ROUTED_SKILLS_STATE_CLASS = "agentos.skills.routing-state"
ROUTED_SKILLS_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SkillsRoutingRegistryImport:
    name: str
    path_text: str
    enabled: bool


@dataclass(frozen=True)
class SkillsRoutingPackage:
    name: str
    imports_payload: object


@dataclass(frozen=True)
class SkillsRoutingProfile:
    name: str
    skill_depot_text: str | None
    packages_payload: object
    imports_payload: object


@dataclass(frozen=True)
class RoutedSkillsSelection:
    caller_root: Path
    local_context_root: Path | None
    profile_name: str | None
    depot_root: Path | None
    imports: list[SkillsImport]


@dataclass(frozen=True)
class RoutedSkillRecord:
    name: str
    description: str
    source: str
    path: Path


@dataclass(frozen=True)
class RoutedSkillsImportResult:
    selection: RoutedSkillsSelection
    skills: list[RoutedSkillRecord]
    sync_result: SkillsSyncResult


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


def _parse_routing_imports_registry(payload: object) -> dict[str, SkillsRoutingRegistryImport]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise CliError("global config field skills.routing.imports_registry must be an object")

    registry: dict[str, SkillsRoutingRegistryImport] = {}
    for raw_name, raw_entry in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise CliError("global config field skills.routing.imports_registry keys must be non-empty strings")
        name = validate_string_for_path(raw_name, field_name="routing import registry name")
        if not isinstance(raw_entry, dict):
            raise CliError(f"global config field skills.routing.imports_registry.{name} must be an object")

        path_value = raw_entry.get("path")
        path_text = str(path_value).strip()
        if not path_text:
            raise CliError(
                f"global config field skills.routing.imports_registry.{name}.path is required"
            )

        enabled = raw_entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise CliError(
                f"global config field skills.routing.imports_registry.{name}.enabled must be a boolean"
            )

        registry[name] = SkillsRoutingRegistryImport(
            name=name,
            path_text=path_text,
            enabled=enabled,
        )

    return registry


def _parse_routing_packages(payload: object) -> dict[str, SkillsRoutingPackage]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise CliError("global config field skills.routing.packages must be an object")

    packages: dict[str, SkillsRoutingPackage] = {}
    for raw_name, raw_package in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise CliError("global config field skills.routing.packages keys must be non-empty strings")
        name = validate_string_for_path(raw_name, field_name="routing package name")
        if not isinstance(raw_package, dict):
            raise CliError(f"global config field skills.routing.packages.{name} must be an object")
        packages[name] = SkillsRoutingPackage(
            name=name,
            imports_payload=raw_package.get("imports", []),
        )

    return packages


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

        skill_depot_text: str | None = None
        if "skill_depot" in raw_profile:
            raw_skill_depot = raw_profile["skill_depot"]
            if not isinstance(raw_skill_depot, str):
                raise CliError(
                    f"global config field skills.routing.profiles.{name}.skill_depot must be a string"
                )
            normalized_skill_depot = raw_skill_depot.strip()
            if not normalized_skill_depot:
                raise CliError(
                    f"global config field skills.routing.profiles.{name}.skill_depot must not be empty"
                )
            skill_depot_text = normalized_skill_depot

        profiles[name] = SkillsRoutingProfile(
            name=name,
            skill_depot_text=skill_depot_text,
            packages_payload=raw_profile.get("packages", []),
            imports_payload=raw_profile.get("imports", []),
        )

    return profiles


def _load_routing_configuration() -> tuple[
    dict[str, SkillsRoutingProfile],
    dict[str, SkillsRoutingPackage],
    dict[str, SkillsRoutingRegistryImport],
    str | None,
]:
    routing = _load_routing_section()
    profiles = _parse_routing_profiles(routing.get("profiles"))
    packages = _parse_routing_packages(routing.get("packages"))
    imports_registry = _parse_routing_imports_registry(routing.get("imports_registry"))
    default_profile_name = _parse_default_profile_name(routing.get("default_profile"))

    if default_profile_name is not None and default_profile_name not in profiles:
        raise CliError(f"routing default profile references unknown profile: {default_profile_name}")

    return profiles, packages, imports_registry, default_profile_name


def _resolve_import_root(path_text: str, *, base_root: Path, field_name: str) -> Path:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = base_root / candidate
    resolved = candidate.resolve()
    if not resolved.exists():
        raise CliError(f"{field_name} path does not exist: {resolved}")
    if not resolved.is_dir():
        raise CliError(f"{field_name} path is not a directory: {resolved}")
    return resolved


def _append_imports_from_payload(
    payload: object,
    *,
    config_label: str,
    inline_base_root: Path,
    imports_registry: dict[str, SkillsRoutingRegistryImport],
    seen_names: set[str],
    resolved_imports: list[SkillsImport],
) -> None:
    if not isinstance(payload, list):
        raise CliError(f"{config_label}.imports must be an array")

    for index, item in enumerate(payload):
        item_label = f"{config_label}.imports[{index}]"
        if not isinstance(item, dict):
            raise CliError(f"{item_label} must be an object")

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise CliError(f"{item_label}.enabled must be a boolean")
        if not enabled:
            continue

        name = validate_string_for_path(
            item.get("name", ""),
            field_name=f"{item_label}.name",
        )

        if name in seen_names:
            raise CliError(f"duplicate enabled routing import name: {name}")

        if "path" in item:
            path_text = str(item["path"]).strip()
            if not path_text:
                raise CliError(f"{item_label}.path must not be empty")
            resolved_imports.append(
                SkillsImport(
                    name=name,
                    root=_resolve_import_root(
                        path_text,
                        base_root=inline_base_root,
                        field_name=item_label,
                    ),
                    configured_path=path_text,
                )
            )
            seen_names.add(name)
            continue

        registry_entry = imports_registry.get(name)
        if registry_entry is None:
            raise CliError(f"routing import references unknown registry entry: {name}")
        if not registry_entry.enabled:
            continue

        resolved_imports.append(
            SkillsImport(
                name=name,
                root=_resolve_import_root(
                    registry_entry.path_text,
                    base_root=agentos_home_dir(),
                    field_name=f"global config field skills.routing.imports_registry.{name}",
                ),
                configured_path=registry_entry.path_text,
            )
        )
        seen_names.add(name)


def _resolve_profile_imports(
    profile: SkillsRoutingProfile,
    *,
    packages: dict[str, SkillsRoutingPackage],
    imports_registry: dict[str, SkillsRoutingRegistryImport],
    caller_root: Path,
) -> list[SkillsImport]:
    resolved_imports: list[SkillsImport] = []
    seen_names: set[str] = set()

    packages_payload = profile.packages_payload
    if not isinstance(packages_payload, list):
        raise CliError(
            f"global config field skills.routing.profiles.{profile.name}.packages must be an array"
        )

    for index, item in enumerate(packages_payload):
        item_label = f"global config field skills.routing.profiles.{profile.name}.packages[{index}]"
        if not isinstance(item, dict):
            raise CliError(f"{item_label} must be an object")

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise CliError(f"{item_label}.enabled must be a boolean")
        if not enabled:
            continue

        package_name = validate_string_for_path(
            item.get("name", ""),
            field_name=f"{item_label}.name",
        )
        package = packages.get(package_name)
        if package is None:
            raise CliError(f"routing profile references unknown package: {package_name}")

        _append_imports_from_payload(
            package.imports_payload,
            config_label=f"global config field skills.routing.packages.{package_name}",
            inline_base_root=caller_root,
            imports_registry=imports_registry,
            seen_names=seen_names,
            resolved_imports=resolved_imports,
        )

    _append_imports_from_payload(
        profile.imports_payload,
        config_label=f"global config field skills.routing.profiles.{profile.name}",
        inline_base_root=caller_root,
        imports_registry=imports_registry,
        seen_names=seen_names,
        resolved_imports=resolved_imports,
    )

    return resolved_imports


def _resolve_profile_skill_depot(profile: SkillsRoutingProfile, caller_root: Path) -> Path:
    configured = profile.skill_depot_text or str(DEFAULT_ROUTED_SKILLS_DEPOT)
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = caller_root / candidate
    return candidate.resolve()


def _load_local_routing_profile_name(context_root: Path) -> str | None:
    config_path = project_config_path(context_root)
    if not config_path.exists():
        return None

    payload = load_project_config(config_path)
    skills_section = payload.get("skills")
    if skills_section is None:
        return None
    if not isinstance(skills_section, dict):
        raise CliError("project config field skills must be a JSON object")

    routing = skills_section.get("routing")
    if routing is None:
        return None
    if not isinstance(routing, dict):
        raise CliError("project config field skills.routing must be a JSON object")

    profile_value = routing.get("profile")
    if profile_value is None:
        return None
    if not isinstance(profile_value, str):
        raise CliError("project config field skills.routing.profile must be a string")

    normalized_name = profile_value.strip()
    if not normalized_name:
        raise CliError("project config field skills.routing.profile must not be empty")
    return validate_string_for_path(normalized_name, field_name="project routing profile name")


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
    profiles, packages, imports_registry, default_profile_name = _load_routing_configuration()

    if local_context_root is None:
        return RoutedSkillsSelection(
            caller_root=raw_start_root,
            local_context_root=None,
            profile_name=None,
            depot_root=None,
            imports=[],
        )

    local_profile_name = _load_local_routing_profile_name(local_context_root)
    selected_profile_name = local_profile_name or default_profile_name or DEFAULT_ROUTED_PROFILE_NAME

    profile = profiles.get(selected_profile_name)
    if profile is None:
        if local_profile_name is not None:
            raise CliError(f"routing profile not found: {selected_profile_name}")
        return RoutedSkillsSelection(
            caller_root=local_context_root,
            local_context_root=local_context_root,
            profile_name=None,
            depot_root=None,
            imports=[],
        )

    return RoutedSkillsSelection(
        caller_root=local_context_root,
        local_context_root=local_context_root,
        profile_name=profile.name,
        depot_root=_resolve_profile_skill_depot(profile, local_context_root),
        imports=_resolve_profile_imports(
            profile,
            packages=packages,
            imports_registry=imports_registry,
            caller_root=local_context_root,
        ),
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


def _sync_routed_profile_depot(
    caller_root: Path,
    depot_root: Path,
    discovered: list[DiscoveredSkill],
) -> SkillsSyncResult:
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

    if create_specs or update_specs:
        normalized_depot_root.mkdir(parents=True, exist_ok=True)
    for link_path in remove_specs:
        if link_path.is_symlink():
            link_path.unlink()
    for link_path, _ in update_specs:
        link_path.unlink()
    for link_path, link_target in create_specs + update_specs:
        link_path.symlink_to(link_target, target_is_directory=True)

    if final_links:
        state[target_key] = dict(sorted(final_links.items()))
    else:
        state.pop(target_key, None)
    _write_routed_skills_state(normalized_caller_root, state)

    return SkillsSyncResult(
        created_links=[path for path, _ in create_specs],
        updated_links=[path for path, _ in update_specs],
        removed_links=remove_specs,
        matching_links=matching_links,
    )


def _routed_records_from_discovered(
    selection: RoutedSkillsSelection,
    discovered: list[DiscoveredSkill],
) -> list[RoutedSkillRecord]:
    if selection.depot_root is None:
        return []

    routed_skills: list[RoutedSkillRecord] = []
    for skill in discovered:
        frontmatter = parse_skill_frontmatter(skill.source_path)
        routed_skills.append(
            RoutedSkillRecord(
                name=skill.name,
                description=frontmatter.get("description", ""),
                source=skill.import_name,
                path=selection.depot_root / skill.name,
            )
        )

    routed_skills.sort(key=lambda item: item.name)
    return routed_skills


def list_routed_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[RoutedSkillsSelection, list[RoutedSkillRecord]]:
    selection = resolve_routed_skills_selection(start_path, project=project)
    discovered = discover_imported_skills(selection.imports)
    return selection, _routed_records_from_discovered(selection, discovered)


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
) -> RoutedSkillsImportResult:
    selection = resolve_routed_skills_selection(start_path, project=project)
    discovered = discover_imported_skills(selection.imports)
    routed_skills = _routed_records_from_discovered(selection, discovered)

    if selection.depot_root is None:
        return RoutedSkillsImportResult(
            selection=selection,
            skills=routed_skills,
            sync_result=SkillsSyncResult(
                created_links=[],
                updated_links=[],
                removed_links=[],
                matching_links=[],
            ),
        )

    sync_result = _sync_routed_profile_depot(selection.caller_root, selection.depot_root, discovered)
    return RoutedSkillsImportResult(
        selection=selection,
        skills=routed_skills,
        sync_result=sync_result,
    )
