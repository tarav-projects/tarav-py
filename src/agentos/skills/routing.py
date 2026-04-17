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
    global_storage_paths,
    load_global_config,
)
from agentos.utils.skills import (
    SKILL_MARKER_FILENAME,
    DiscoveredSkill,
    SkillsImport,
    _parse_skills_imports,
    discover_imported_skills,
    list_target_skill_dirs,
    parse_skill_frontmatter,
)

ROUTED_SKILLS_DEPOT_DIRNAME = "skills-depot"
ROUTED_SKILLS_STATE_FILENAME = "skills-routing-links.json"
ROUTED_SKILLS_STATE_CLASS = "agentos.skills.routing-state"
ROUTED_SKILLS_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SkillsRoutingBinding:
    root: Path
    profile: str


@dataclass(frozen=True)
class SkillsRoutingProfile:
    name: str
    imports_payload: object


@dataclass(frozen=True)
class RoutedSkillsSelection:
    caller_root: Path
    matched_binding_root: Path | None
    profile_name: str
    depot_root: Path
    imports: list[SkillsImport]


@dataclass(frozen=True)
class RoutedSkillRecord:
    name: str
    description: str
    source: str
    path: Path


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
        profiles[name] = SkillsRoutingProfile(
            name=name,
            imports_payload=raw_profile.get("imports", []),
        )
    return profiles


def _parse_routing_imports_registry(payload: object) -> dict[str, dict[str, object]]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise CliError("global config field skills.routing.imports_registry must be an object")

    registry: dict[str, dict[str, object]] = {}
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

        registry_entry: dict[str, object] = {
            "name": name,
            "path": path_text,
        }
        if "enabled" in raw_entry:
            enabled = raw_entry["enabled"]
            if not isinstance(enabled, bool):
                raise CliError(
                    f"global config field skills.routing.imports_registry.{name}.enabled must be a boolean"
                )
            registry_entry["enabled"] = enabled

        registry[name] = registry_entry

    return registry


def _parse_routing_bindings(payload: object) -> list[SkillsRoutingBinding]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise CliError("global config field skills.routing.bindings must be an array")

    bindings: list[SkillsRoutingBinding] = []
    seen_roots: set[Path] = set()

    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise CliError(f"global config field skills.routing.bindings[{index}] must be an object")

        raw_root = str(item.get("root", "")).strip()
        if not raw_root:
            raise CliError(f"global config field skills.routing.bindings[{index}].root is required")
        root = Path(raw_root).expanduser()
        if not root.is_absolute():
            root = agentos_home_dir() / root
        normalized_root = root.resolve()

        profile = validate_string_for_path(
            item.get("profile", ""),
            field_name=f"global config field skills.routing.bindings[{index}].profile",
        )

        if normalized_root in seen_roots:
            raise CliError(f"duplicate routing binding root: {normalized_root}")
        seen_roots.add(normalized_root)
        bindings.append(SkillsRoutingBinding(root=normalized_root, profile=profile))

    return bindings


def _load_routing_profiles_and_bindings() -> tuple[
    dict[str, SkillsRoutingProfile],
    dict[str, dict[str, object]],
    list[SkillsRoutingBinding],
]:
    routing = _load_routing_section()
    profiles = _parse_routing_profiles(routing.get("profiles"))
    imports_registry = _parse_routing_imports_registry(routing.get("imports_registry"))
    bindings = _parse_routing_bindings(routing.get("bindings"))

    for binding in bindings:
        if binding.profile == "base":
            continue
        if binding.profile not in profiles:
            raise CliError(f"routing binding references unknown profile: {binding.profile}")

    return profiles, imports_registry, bindings


def _resolve_profile_imports_payload(
    profile: SkillsRoutingProfile,
    imports_registry: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    payload = profile.imports_payload
    if not isinstance(payload, list):
        raise CliError(
            f"global config field skills.routing.profiles.{profile.name}.imports must be an array"
        )

    resolved: list[dict[str, object]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise CliError(
                f"global config field skills.routing.profiles.{profile.name}.imports[{index}] must be an object"
            )

        name = validate_string_for_path(
            item.get("name", ""),
            field_name=(
                f"global config field skills.routing.profiles.{profile.name}.imports[{index}].name"
            ),
        )

        if "enabled" in item and not isinstance(item["enabled"], bool):
            raise CliError(
                f"global config field skills.routing.profiles.{profile.name}.imports[{index}].enabled must be a boolean"
            )

        if "path" in item:
            path_text = str(item["path"]).strip()
            if not path_text:
                raise CliError(
                    f"global config field skills.routing.profiles.{profile.name}.imports[{index}].path must not be empty"
                )
            resolved_item: dict[str, object] = {
                "name": name,
                "path": path_text,
            }
            if "enabled" in item:
                resolved_item["enabled"] = item["enabled"]
            resolved.append(resolved_item)
            continue

        registry_entry = imports_registry.get(name)
        if registry_entry is None:
            raise CliError(
                f"routing profile import references unknown registry entry: {profile.name}/{name}"
            )

        resolved_item = dict(registry_entry)
        if "enabled" in item:
            resolved_item["enabled"] = item["enabled"]
        resolved.append(resolved_item)

    return resolved


def _select_closest_binding(
    caller_root: Path,
    bindings: list[SkillsRoutingBinding],
) -> SkillsRoutingBinding | None:
    matches: list[SkillsRoutingBinding] = []
    for binding in bindings:
        try:
            caller_root.relative_to(binding.root)
        except ValueError:
            continue
        matches.append(binding)

    if not matches:
        return None

    matches.sort(key=lambda binding: len(binding.root.parts), reverse=True)
    return matches[0]


def routed_skills_depot(profile_name: str) -> Path:
    normalized_name = validate_string_for_path(profile_name, field_name="routing profile name")
    return agentos_home_dir() / ROUTED_SKILLS_DEPOT_DIRNAME / normalized_name


def _routed_skills_state_path() -> Path:
    return global_storage_paths()["cache"] / ROUTED_SKILLS_STATE_FILENAME


def resolve_routed_skills_selection(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> RoutedSkillsSelection:
    caller_root = resolve_routed_skills_caller_root(start_path, project=project)
    profiles, imports_registry, bindings = _load_routing_profiles_and_bindings()
    matched_binding = _select_closest_binding(caller_root, bindings)

    profile_name = matched_binding.profile if matched_binding is not None else "base"
    profile = profiles.get(profile_name)

    if profile is None:
        if profile_name != "base":
            raise CliError(f"routing profile not found: {profile_name}")
        imports: list[SkillsImport] = []
    else:
        resolved_imports_payload = _resolve_profile_imports_payload(profile, imports_registry)
        imports = _parse_skills_imports(
            resolved_imports_payload,
            config_label=f"global config field skills.routing.profiles.{profile_name}",
            base_root=matched_binding.root if matched_binding is not None else caller_root,
        )

    return RoutedSkillsSelection(
        caller_root=caller_root,
        matched_binding_root=matched_binding.root if matched_binding is not None else None,
        profile_name=profile_name,
        depot_root=routed_skills_depot(profile_name),
        imports=imports,
    )


def _relative_symlink_target(link_path: Path, source_path: Path) -> str:
    return os.path.relpath(source_path, start=link_path.parent)


def _resolved_symlink_target(path: Path) -> Path:
    link_target = Path(os.readlink(path))
    if link_target.is_absolute():
        return link_target.resolve()
    return (path.parent / link_target).resolve()


def _load_routed_skills_state() -> dict[str, dict[str, str]]:
    state_path = _routed_skills_state_path()
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


def _write_routed_skills_state(state: dict[str, dict[str, str]]) -> None:
    state_path = _routed_skills_state_path()
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
    profile_name: str,
    depot_root: Path,
    discovered: list[DiscoveredSkill],
) -> None:
    normalized_depot_root = depot_root.expanduser().resolve()
    if normalized_depot_root.exists() and not normalized_depot_root.is_dir():
        raise CliError(f"routed skills depot is not a directory: {normalized_depot_root}")

    state = _load_routed_skills_state()
    previous_links = state.get(profile_name, {})

    create_specs: list[tuple[Path, str]] = []
    update_specs: list[tuple[Path, str]] = []
    remove_specs: list[Path] = []
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
        state[profile_name] = dict(sorted(final_links.items()))
    else:
        state.pop(profile_name, None)
    _write_routed_skills_state(state)


def _ensure_routed_profile_materialized(
    selection: RoutedSkillsSelection,
) -> dict[str, DiscoveredSkill]:
    discovered = discover_imported_skills(selection.imports)
    _sync_routed_profile_depot(selection.profile_name, selection.depot_root, discovered)
    return {skill.name: skill for skill in discovered}


def list_routed_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[RoutedSkillsSelection, list[RoutedSkillRecord]]:
    selection = resolve_routed_skills_selection(start_path, project=project)
    discovered_by_name = _ensure_routed_profile_materialized(selection)

    routed_skills: list[RoutedSkillRecord] = []
    for skill_dir in list_target_skill_dirs(selection.depot_root):
        frontmatter = parse_skill_frontmatter(skill_dir)
        discovered = discovered_by_name.get(skill_dir.name)
        routed_skills.append(
            RoutedSkillRecord(
                name=skill_dir.name,
                description=frontmatter.get("description", ""),
                source=discovered.import_name if discovered is not None else selection.profile_name,
                path=skill_dir,
            )
        )

    return selection, routed_skills


def resolve_routed_skill(
    name: str,
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[RoutedSkillsSelection, RoutedSkillRecord | None]:
    normalized_name = validate_string_for_path(name, field_name="skill name")
    selection = resolve_routed_skills_selection(start_path, project=project)
    discovered_by_name = _ensure_routed_profile_materialized(selection)

    skill_path = selection.depot_root / normalized_name
    if not skill_path.exists() or not skill_path.is_dir() or not (skill_path / SKILL_MARKER_FILENAME).is_file():
        return (selection, None)

    frontmatter = parse_skill_frontmatter(skill_path)
    discovered = discovered_by_name.get(normalized_name)
    return (
        selection,
        RoutedSkillRecord(
            name=normalized_name,
            description=frontmatter.get("description", ""),
            source=discovered.import_name if discovered is not None else selection.profile_name,
            path=skill_path,
        ),
    )
