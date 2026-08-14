# $kw: --from Selected.Skills --from Skill.Depot
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.path_validation import validate_string_for_path
from tarav._core.project import (
    tarav_home_dir,
    global_config_path,
    load_project_marker,
    load_global_config,
    local_storage_paths,
    load_project_config,
    project_config_path,
    project_marker_path,
    require_agentos_project_root,
)
from tarav.skills.catalog import (
    DiscoveredSkill,
    SkillsImport,
    SkillsImportFilter,
    SkillsSyncResult,
    discover_imported_skills,
    parse_skill_frontmatter,
)

DEFAULT_SKILLS_DEPOTS = (
    ".agents/skills",
    ".claude/skills",
)
DEFAULT_SKILLS_PROFILE_NAME = "default"
SKILLS_SOURCE_KIND_PATH = "path"
SKILLS_SOURCE_KIND_PROJECT = "project"
SKILLS_SOURCE_KIND_PACKAGE = "package"
DEFAULT_PROJECT_SKILLS_DIRNAME = "skills"
SKILLS_GLOBAL_DEPOTS_DIR = ("skills", "depots")


@dataclass(frozen=True)
class SkillsRoutingSource:
    name: str
    kind: str
    path_text: str | None
    project_path_text: str | None
    package_payload: object | None
    enabled: bool
    filter_context: SkillsImportFilter | None


@dataclass(frozen=True)
class SkillsSourceReference:
    source_name: str
    export_package_name: str | None


@dataclass(frozen=True)
class SkillsRoutingProfile:
    name: str
    depots_payload: object | None
    sources_payload: object


@dataclass(frozen=True)
class SkillsSelection:
    caller_root: Path
    local_context_root: Path | None
    profile_name: str | None
    depot_roots: tuple[Path, ...]
    sources: list[SkillsImport]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectedSkillRecord:
    name: str
    description: str
    source: str
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class SelectedSkillMatch:
    skill: SelectedSkillRecord
    frontmatter: dict[str, str]


@dataclass(frozen=True)
class SkillsDepotImportResult:
    depot_root: Path
    sync_result: SkillsSyncResult


@dataclass(frozen=True)
class SkillsImportResult:
    selection: SkillsSelection
    skills: list[SelectedSkillRecord]
    depot_results: tuple[SkillsDepotImportResult, ...]
    global_depot_root: Path | None = None
    global_sync_result: SkillsSyncResult | None = None


@dataclass(frozen=True)
class SkillsStatusEntry:
    name: str
    path: Path
    source: str | None
    expected_source_path: Path | None
    actual_entry_kind: str | None
    actual_link_target: str | None
    actual_resolved_target: Path | None


@dataclass(frozen=True)
class SkillsDepotStatusResult:
    depot_root: Path
    matching: list[SkillsStatusEntry]
    missing: list[SkillsStatusEntry]
    broken: list[SkillsStatusEntry]
    unsynced: list[SkillsStatusEntry]
    conflicts: list[SkillsStatusEntry]
    extra: list[SkillsStatusEntry]


@dataclass(frozen=True)
class SkillsStatusResult:
    selection: SkillsSelection
    skills: list[SelectedSkillRecord]
    depot_statuses: tuple[SkillsDepotStatusResult, ...]


def _registry_source_field_label(source_name: str) -> str:
    return f"global config field skills.routing.sources.{source_name}"


def _parse_enabled_flag(payload: dict[str, object], *, field_label: str) -> bool:
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise CliError(f"{field_label}.enabled must be a boolean")
    return enabled


def _source_target_kind(
    payload: dict[str, object],
    *,
    field_label: str,
    require_target: bool,
) -> str | None:
    target_fields = [
        field_name
        for field_name in (
            SKILLS_SOURCE_KIND_PATH,
            SKILLS_SOURCE_KIND_PROJECT,
            SKILLS_SOURCE_KIND_PACKAGE,
        )
        if field_name in payload
    ]
    if require_target:
        if len(target_fields) != 1:
            raise CliError(f"{field_label} must define exactly one of path, project, or package")
    elif len(target_fields) > 1:
        raise CliError(f"{field_label} must define exactly one of path, project, or package")
    if not target_fields:
        return None
    return target_fields[0]


def _validate_routing_ref_part(value: str, *, field_name: str) -> str:
    name = validate_string_for_path(value, field_name=field_name)
    if ":" in name:
        raise CliError(f"{field_name} must not contain ':'")
    return name


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


def _require_source_project_path_text(
    payload: dict[str, object],
    *,
    field_label: str,
    empty_error_suffix: str = "must not be empty",
) -> str:
    path_text = str(payload.get("project", "")).strip()
    if not path_text:
        raise CliError(f"{field_label}.project {empty_error_suffix}")
    return path_text


def _parse_source_reference(raw_name: str, *, field_name: str) -> SkillsSourceReference:
    if raw_name.count(":") > 1:
        raise CliError(f"{field_name} must contain at most one ':' package separator")
    if ":" not in raw_name:
        return SkillsSourceReference(
            source_name=_validate_routing_ref_part(raw_name, field_name=field_name),
            export_package_name=None,
        )

    raw_source_name, raw_package_name = raw_name.split(":", 1)
    return SkillsSourceReference(
        source_name=_validate_routing_ref_part(
            raw_source_name,
            field_name=f"{field_name} source",
        ),
        export_package_name=_validate_routing_ref_part(
            raw_package_name,
            field_name=f"{field_name} package",
        ),
    )


def _require_source_reference(
    payload: dict[str, object],
    *,
    field_label: str,
    default_source_name: str | None = None,
) -> SkillsSourceReference:
    raw_name = payload.get("name")
    if raw_name is None and default_source_name is not None:
        raw_name = default_source_name
    if not isinstance(raw_name, str):
        raise CliError(f"{field_label}.name must be a string")
    return _parse_source_reference(raw_name, field_name=f"{field_label}.name")


def _require_local_export_source_reference(
    payload: dict[str, object],
    *,
    field_label: str,
    default_source_name: str | None,
) -> SkillsSourceReference:
    source_ref = _require_source_reference(
        payload,
        field_label=field_label,
        default_source_name=default_source_name,
    )
    if default_source_name is not None and source_ref.source_name != default_source_name:
        raise CliError(
            f"{field_label}.name must reference local export source: {default_source_name}"
        )
    return source_ref


def _require_local_source_ref_without_export_package(
    payload: dict[str, object],
    *,
    field_label: str,
    default_source_name: str | None,
    source_kind: str,
) -> SkillsSourceReference:
    source_ref = _require_local_export_source_reference(
        payload,
        field_label=field_label,
        default_source_name=default_source_name,
    )
    if source_ref.export_package_name is not None:
        raise CliError(
            f"{field_label}.name must not include an export package for {source_kind} sources"
        )
    return source_ref


def _parse_skill_filter_names(
    payload: dict[str, object],
    *,
    field_label: str,
    field_name: str,
) -> tuple[str, ...] | None:
    if field_name not in payload:
        return None

    names_payload = payload.get(field_name)
    if not isinstance(names_payload, list | tuple):
        raise CliError(f"{field_label}.{field_name} must be an array")

    names: list[str] = []
    seen_names: set[str] = set()
    for index, item in enumerate(names_payload):
        item_label = f"{field_label}.{field_name}[{index}]"
        if not isinstance(item, str):
            raise CliError(f"{item_label} must be a string")
        name = validate_string_for_path(item, field_name=item_label)
        if name in seen_names:
            raise CliError(f"{field_label}.{field_name} contains duplicate skill name: {name}")
        names.append(name)
        seen_names.add(name)

    return tuple(names)


def _parse_source_filter(
    payload: dict[str, object],
    *,
    field_label: str,
) -> SkillsImportFilter | None:
    include = _parse_skill_filter_names(
        payload,
        field_label=field_label,
        field_name="include",
    )
    exclude = _parse_skill_filter_names(
        payload,
        field_label=field_label,
        field_name="exclude",
    )
    if include is None and exclude is None:
        return None
    return SkillsImportFilter(
        include=include,
        exclude=() if exclude is None else exclude,
        field_label=field_label,
    )


def _append_filter_context(
    filters: tuple[SkillsImportFilter, ...],
    filter_context: SkillsImportFilter | None,
) -> tuple[SkillsImportFilter, ...]:
    if filter_context is None:
        return filters
    return (*filters, filter_context)


def resolve_skills_caller_root(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> Path:
    return require_agentos_project_root(
        start_path,
        project=project,
        include_init_hint=True,
    )


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
        name = _validate_routing_ref_part(raw_name, field_name="routing source name")
        if not isinstance(raw_entry, dict):
            raise CliError(f"{_registry_source_field_label(name)} must be an object")

        item_label = _registry_source_field_label(name)
        enabled = _parse_enabled_flag(raw_entry, field_label=item_label)
        filter_context = _parse_source_filter(raw_entry, field_label=item_label)
        target_kind = _source_target_kind(
            raw_entry,
            field_label=item_label,
            require_target=True,
        )

        if target_kind == SKILLS_SOURCE_KIND_PATH:
            path_text = _require_source_path_text(
                raw_entry,
                field_label=item_label,
                empty_error_suffix="is required",
            )
            registry[name] = SkillsRoutingSource(
                name=name,
                kind=SKILLS_SOURCE_KIND_PATH,
                path_text=path_text,
                project_path_text=None,
                package_payload=None,
                enabled=enabled,
                filter_context=filter_context,
            )
            continue

        if target_kind == SKILLS_SOURCE_KIND_PROJECT:
            registry[name] = SkillsRoutingSource(
                name=name,
                kind=SKILLS_SOURCE_KIND_PROJECT,
                path_text=None,
                project_path_text=_require_source_project_path_text(
                    raw_entry,
                    field_label=item_label,
                    empty_error_suffix="is required",
                ),
                package_payload=None,
                enabled=enabled,
                filter_context=filter_context,
            )
            continue

        registry[name] = SkillsRoutingSource(
            name=name,
            kind=SKILLS_SOURCE_KIND_PACKAGE,
            path_text=None,
            project_path_text=None,
            package_payload=raw_entry.get("package"),
            enabled=enabled,
            filter_context=filter_context,
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


def _resolve_project_root(path_text: str, *, base_root: Path, field_name: str) -> Path:
    project_root = _resolve_source_root(path_text, base_root=base_root, field_name=field_name)
    marker_path = project_marker_path(project_root)
    if not marker_path.is_file():
        raise CliError(f"{field_name} is not a tarav project (missing {marker_path})")
    load_project_marker(marker_path)
    return project_root


def _project_skills_root(project_root: Path, *, field_name: str) -> Path:
    skills_root = project_root / DEFAULT_PROJECT_SKILLS_DIRNAME
    if not skills_root.exists():
        raise CliError(f"{field_name} skills path does not exist: {skills_root}")
    if not skills_root.is_dir():
        raise CliError(f"{field_name} skills path is not a directory: {skills_root}")
    return skills_root


def _append_resolved_source(
    name: str,
    *,
    root: Path,
    configured_path: str,
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    filters: tuple[SkillsImportFilter, ...],
) -> None:
    if name in seen_names:
        raise CliError(f"duplicate enabled routing source name: {name}")

    resolved_sources.append(
        SkillsImport(
            name=name,
            root=root,
            configured_path=configured_path,
            filters=filters,
        )
    )
    seen_names.add(name)


def _append_direct_source(
    name: str,
    path_text: str,
    *,
    base_root: Path,
    field_name: str,
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    filters: tuple[SkillsImportFilter, ...],
) -> None:
    _append_resolved_source(
        name,
        root=_resolve_source_root(path_text, base_root=base_root, field_name=field_name),
        configured_path=path_text,
        seen_names=seen_names,
        resolved_sources=resolved_sources,
        filters=filters,
    )


def _append_project_source(
    name: str,
    project_path_text: str,
    *,
    base_root: Path,
    field_name: str,
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    filters: tuple[SkillsImportFilter, ...],
) -> None:
    project_root = _resolve_project_root(
        project_path_text,
        base_root=base_root,
        field_name=field_name,
    )
    _append_resolved_source(
        name,
        root=_project_skills_root(project_root, field_name=field_name),
        configured_path=project_path_text,
        seen_names=seen_names,
        resolved_sources=resolved_sources,
        filters=filters,
    )


def _load_project_export_packages(project_root: Path, *, field_label: str) -> dict[str, object]:
    config_path = project_config_path(project_root)
    if not config_path.exists():
        return {}

    payload = load_project_config(config_path)
    skills_section = payload.get("skills")
    if skills_section is None:
        return {}
    if not isinstance(skills_section, dict):
        raise CliError(f"{field_label} project config field skills must be an object")

    exports_section = skills_section.get("exports")
    if exports_section is None:
        return {}
    if not isinstance(exports_section, dict):
        raise CliError(f"{field_label} project config field skills.exports must be an object")

    packages_section = exports_section.get("packages")
    if packages_section is None:
        return {}
    if not isinstance(packages_section, dict):
        raise CliError(
            f"{field_label} project config field skills.exports.packages must be an object"
        )

    packages: dict[str, object] = {}
    for raw_package_name, package_payload in packages_section.items():
        if not isinstance(raw_package_name, str):
            raise CliError(
                f"{field_label} project config field skills.exports.packages keys must be strings"
            )
        package_name = _validate_routing_ref_part(
            raw_package_name,
            field_name=f"{field_label} export package name",
        )
        if not isinstance(package_payload, list):
            raise CliError(
                f"{field_label} project config field "
                f"skills.exports.packages.{package_name} must be an array"
            )
        packages[package_name] = package_payload

    return packages


def _append_project_export_package(
    source_ref: SkillsSourceReference,
    *,
    sources_registry: dict[str, SkillsRoutingSource],
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    registry_stack: tuple[str, ...],
    filters: tuple[SkillsImportFilter, ...],
) -> None:
    assert source_ref.export_package_name is not None
    registry_entry = sources_registry.get(source_ref.source_name)
    if registry_entry is None:
        raise CliError(f"routing source references unknown registry source: {source_ref.source_name}")
    if not registry_entry.enabled:
        return
    if registry_entry.kind != SKILLS_SOURCE_KIND_PROJECT:
        raise CliError(
            "routing source export package requires project-backed source: "
            f"{source_ref.source_name}:{source_ref.export_package_name}"
        )

    source_key = f"{source_ref.source_name}:{source_ref.export_package_name}"
    if source_key in registry_stack:
        cycle = " -> ".join([*registry_stack, source_key])
        raise CliError(f"routing source cycle detected: {cycle}")

    assert registry_entry.project_path_text is not None
    field_name = _registry_source_field_label(registry_entry.name)
    project_root = _resolve_project_root(
        registry_entry.project_path_text,
        base_root=tarav_home_dir(),
        field_name=field_name,
    )
    packages = _load_project_export_packages(project_root, field_label=field_name)
    package_payload = packages.get(source_ref.export_package_name)
    if package_payload is None:
        raise CliError(f"routing source export package not found: {source_key}")

    _append_sources_from_payload(
        package_payload,
        payload_label=f"{field_name}.exports.{source_ref.export_package_name}",
        inline_base_root=project_root,
        sources_registry=sources_registry,
        seen_names=seen_names,
        resolved_sources=resolved_sources,
        registry_stack=(*registry_stack, source_key),
        filters=filters,
        default_source_name=source_ref.source_name,
    )


def _append_sources_from_registry_reference(
    source_ref: SkillsSourceReference,
    *,
    sources_registry: dict[str, SkillsRoutingSource],
    seen_names: set[str],
    resolved_sources: list[SkillsImport],
    registry_stack: tuple[str, ...],
    filters: tuple[SkillsImportFilter, ...],
) -> None:
    if source_ref.export_package_name is not None:
        _append_project_export_package(
            source_ref,
            sources_registry=sources_registry,
            seen_names=seen_names,
            resolved_sources=resolved_sources,
            registry_stack=registry_stack,
            filters=filters,
        )
        return

    source_name = source_ref.source_name
    registry_entry = sources_registry.get(source_name)
    if registry_entry is None:
        raise CliError(f"routing source references unknown registry source: {source_name}")
    if not registry_entry.enabled:
        return
    if source_name in registry_stack:
        cycle = " -> ".join([*registry_stack, source_name])
        raise CliError(f"routing source cycle detected: {cycle}")

    source_filters = _append_filter_context(filters, registry_entry.filter_context)
    if registry_entry.kind == SKILLS_SOURCE_KIND_PATH:
        assert registry_entry.path_text is not None
        _append_direct_source(
            registry_entry.name,
            registry_entry.path_text,
            base_root=tarav_home_dir(),
            field_name=_registry_source_field_label(registry_entry.name),
            seen_names=seen_names,
            resolved_sources=resolved_sources,
            filters=source_filters,
        )
        return

    if registry_entry.kind == SKILLS_SOURCE_KIND_PROJECT:
        assert registry_entry.project_path_text is not None
        _append_project_source(
            registry_entry.name,
            registry_entry.project_path_text,
            base_root=tarav_home_dir(),
            field_name=_registry_source_field_label(registry_entry.name),
            seen_names=seen_names,
            resolved_sources=resolved_sources,
            filters=source_filters,
        )
        return

    _append_sources_from_payload(
        registry_entry.package_payload,
        payload_label=f"{_registry_source_field_label(registry_entry.name)}.package",
        inline_base_root=tarav_home_dir(),
        sources_registry=sources_registry,
        seen_names=seen_names,
        resolved_sources=resolved_sources,
        registry_stack=(*registry_stack, source_name),
        filters=source_filters,
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
    filters: tuple[SkillsImportFilter, ...] = (),
    default_source_name: str | None = None,
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
        item_filters = _append_filter_context(
            filters,
            _parse_source_filter(item, field_label=item_label),
        )

        target_kind = _source_target_kind(
            item,
            field_label=item_label,
            require_target=False,
        )

        if target_kind == SKILLS_SOURCE_KIND_PATH:
            source_ref = _require_local_source_ref_without_export_package(
                item,
                field_label=item_label,
                default_source_name=default_source_name,
                source_kind=SKILLS_SOURCE_KIND_PATH,
            )
            path_text = _require_source_path_text(item, field_label=item_label)
            _append_direct_source(
                source_ref.source_name,
                path_text,
                base_root=inline_base_root,
                field_name=item_label,
                seen_names=seen_names,
                resolved_sources=resolved_sources,
                filters=item_filters,
            )
            continue

        if target_kind == SKILLS_SOURCE_KIND_PROJECT:
            source_ref = _require_local_source_ref_without_export_package(
                item,
                field_label=item_label,
                default_source_name=default_source_name,
                source_kind=SKILLS_SOURCE_KIND_PROJECT,
            )
            _append_project_source(
                source_ref.source_name,
                _require_source_project_path_text(item, field_label=item_label),
                base_root=inline_base_root,
                field_name=item_label,
                seen_names=seen_names,
                resolved_sources=resolved_sources,
                filters=item_filters,
            )
            continue

        if target_kind == SKILLS_SOURCE_KIND_PACKAGE:
            _append_sources_from_payload(
                item.get("package"),
                payload_label=f"{item_label}.package",
                inline_base_root=inline_base_root,
                sources_registry=sources_registry,
                seen_names=seen_names,
                resolved_sources=resolved_sources,
                registry_stack=registry_stack,
                filters=item_filters,
                default_source_name=default_source_name,
            )
            continue

        source_ref = _require_local_export_source_reference(
            item,
            field_label=item_label,
            default_source_name=default_source_name,
        )
        _append_sources_from_registry_reference(
            source_ref,
            sources_registry=sources_registry,
            seen_names=seen_names,
            resolved_sources=resolved_sources,
            registry_stack=registry_stack,
            filters=item_filters,
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
    configured_depots = DEFAULT_SKILLS_DEPOTS if depots_payload is None else depots_payload

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

        unresolved_candidate = caller_root / candidate
        resolved_candidate = unresolved_candidate.parent.resolve() / unresolved_candidate.name
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


def resolve_skills_selection(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> SkillsSelection:
    resolved_start_root = resolve_skills_caller_root(start_path, project=project)
    profiles, sources_registry, default_profile_name = _load_routing_configuration()
    local_context_root = resolved_start_root
    local_profile_name, selection_warnings = _load_local_routing_profile_name(local_context_root)
    selected_profile_name = local_profile_name or default_profile_name or DEFAULT_SKILLS_PROFILE_NAME

    profile = profiles.get(selected_profile_name)
    if profile is None:
        if local_profile_name is not None:
            raise CliError(f"routing profile not found: {selected_profile_name}")
        return SkillsSelection(
            caller_root=local_context_root,
            local_context_root=local_context_root,
            profile_name=None,
            depot_roots=(),
            sources=[],
            warnings=selection_warnings,
        )

    return SkillsSelection(
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
        raise CliError(f"skills depot is not a directory: {normalized_depot_root}")

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


def _skills_global_depot_hash(selection: SkillsSelection) -> str:
    payload = {
        "profile": selection.profile_name,
        "sources": [
            {
                "name": source.name,
                "root": str(source.root.expanduser().resolve()),
                "configured_path": source.configured_path,
                "filters": [
                    {
                        "include": None if item.include is None else list(item.include),
                        "exclude": list(item.exclude),
                    }
                    for item in source.filters
                ],
            }
            for source in selection.sources
        ],
    }
    payload_text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()[:16]


def _skills_global_depot_root(selection: SkillsSelection) -> Path:
    return tarav_home_dir().joinpath(
        *SKILLS_GLOBAL_DEPOTS_DIR,
        _skills_global_depot_hash(selection),
    )


def _depot_directory_is_replaceable(depot_root: Path) -> bool:
    """Whether a directory sitting at a project depot path is ours to replace.

    A project depot is a symlink to the shared global depot. A *directory* there
    is either a depot generated before that shape existed - all entries symlinks,
    nothing else - or something a person put there. The structural test is the
    whole test: no ownership ledger is kept, because the global depot is derived
    state that is rebuilt rather than reconciled.
    """

    if not depot_root.exists() or depot_root.is_symlink() or not depot_root.is_dir():
        return False
    return all(entry.is_symlink() for entry in depot_root.iterdir())


def _replace_project_depot_with_global_link(
    depot_root: Path,
    global_depot_root: Path,
    *,
    force: bool = False,
) -> SkillsSyncResult:
    normalized_depot_root = (
        depot_root.expanduser().resolve()
        if not depot_root.is_symlink()
        else depot_root.expanduser()
    )
    normalized_global_depot_root = global_depot_root.expanduser().resolve()

    if normalized_depot_root.is_symlink():
        if _resolved_symlink_target(normalized_depot_root) == normalized_global_depot_root:
            return SkillsSyncResult(
                created_links=[],
                updated_links=[],
                removed_links=[],
                matching_links=[normalized_depot_root],
            )
        normalized_depot_root.unlink()
        normalized_depot_root.parent.mkdir(parents=True, exist_ok=True)
        normalized_depot_root.symlink_to(
            _relative_symlink_target(normalized_depot_root, normalized_global_depot_root),
            target_is_directory=True,
        )
        return SkillsSyncResult(
            created_links=[],
            updated_links=[normalized_depot_root],
            removed_links=[],
            matching_links=[],
        )

    if normalized_depot_root.exists():
        if not force and not _depot_directory_is_replaceable(normalized_depot_root):
            raise CliError(f"skills depot path cannot be replaced safely: {normalized_depot_root}")
        shutil.rmtree(normalized_depot_root)
        action = "updated"
    else:
        action = "created"

    normalized_depot_root.parent.mkdir(parents=True, exist_ok=True)
    normalized_depot_root.symlink_to(
        _relative_symlink_target(normalized_depot_root, normalized_global_depot_root),
        target_is_directory=True,
    )

    if action == "created":
        return SkillsSyncResult(
            created_links=[normalized_depot_root],
            updated_links=[],
            removed_links=[],
            matching_links=[],
        )
    return SkillsSyncResult(
        created_links=[],
        updated_links=[normalized_depot_root],
        removed_links=[],
        matching_links=[],
    )


def _preflight_project_depot_global_link(
    depot_root: Path,
    *,
    force: bool = False,
) -> None:
    normalized_depot_root = (
        depot_root.expanduser().resolve()
        if not depot_root.is_symlink()
        else depot_root.expanduser()
    )
    if force or normalized_depot_root.is_symlink() or not normalized_depot_root.exists():
        return
    if _depot_directory_is_replaceable(normalized_depot_root):
        return
    raise CliError(f"skills depot path cannot be replaced safely: {normalized_depot_root}")


def _read_depot_links(depot_root: Path) -> dict[str, str]:
    if not depot_root.exists():
        return {}
    return {
        entry.name: os.readlink(entry)
        for entry in depot_root.iterdir()
        if entry.is_symlink()
    }


def _rebuild_global_depot(
    depot_root: Path,
    discovered: list[DiscoveredSkill],
) -> SkillsSyncResult:
    """Rebuild the shared depot from the selected catalog.

    The depot is derived: its path is a hash of the profile and every source, so
    its contents are a pure function of its name. That makes rebuilding it the
    honest operation - clear it, write one symlink per selected skill - and makes
    a reconciliation ledger unnecessary. Two projects rebuilding concurrently
    produce identical content, so the race is benign.

    What changed is reported by diffing the listing taken before the rebuild
    against the one written after, which is the same information a delta would
    have carried without keeping any of it on disk.
    """

    normalized_depot_root = depot_root.expanduser().resolve()
    if normalized_depot_root.exists() and not normalized_depot_root.is_dir():
        raise CliError(f"skills depot is not a directory: {normalized_depot_root}")

    previous_links = _read_depot_links(normalized_depot_root)

    if normalized_depot_root.exists():
        for entry in sorted(normalized_depot_root.iterdir(), key=lambda path: path.name):
            if not entry.is_symlink():
                raise CliError(
                    f"skills depot holds an entry that is not a generated link: {entry}"
                )
            entry.unlink()
    normalized_depot_root.mkdir(parents=True, exist_ok=True)

    final_links: dict[str, str] = {}
    for skill in discovered:
        link_path = normalized_depot_root / skill.name
        link_target = _relative_symlink_target(link_path, skill.source_path.resolve())
        link_path.symlink_to(link_target, target_is_directory=True)
        final_links[skill.name] = link_target

    created = sorted(name for name in final_links if name not in previous_links)
    removed = sorted(name for name in previous_links if name not in final_links)
    updated = sorted(
        name
        for name, link_target in final_links.items()
        if name in previous_links and previous_links[name] != link_target
    )
    matching = sorted(
        name
        for name, link_target in final_links.items()
        if previous_links.get(name) == link_target
    )

    return SkillsSyncResult(
        created_links=[normalized_depot_root / name for name in created],
        updated_links=[normalized_depot_root / name for name in updated],
        removed_links=[normalized_depot_root / name for name in removed],
        matching_links=[normalized_depot_root / name for name in matching],
    )


def _selected_records_from_discovered(
    selection: SkillsSelection,
    discovered: list[DiscoveredSkill],
) -> list[SelectedSkillRecord]:
    selected_skills: list[SelectedSkillRecord] = []
    for skill in discovered:
        frontmatter = parse_skill_frontmatter(skill.source_path)
        selected_skills.append(
            SelectedSkillRecord(
                name=skill.name,
                description=frontmatter.get("description", ""),
                source=skill.import_name,
                paths=tuple(depot_root / skill.name for depot_root in selection.depot_roots),
            )
        )

    selected_skills.sort(key=lambda item: item.name)
    return selected_skills


def _resolve_selected_skills_catalog(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[SkillsSelection, list[DiscoveredSkill], list[SelectedSkillRecord]]:
    selection = resolve_skills_selection(start_path, project=project)
    discovered = discover_imported_skills(selection.sources)
    selected_skills = _selected_records_from_discovered(selection, discovered)
    return selection, discovered, selected_skills


def list_selected_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[SkillsSelection, list[SelectedSkillRecord]]:
    selection, _, selected_skills = _resolve_selected_skills_catalog(start_path, project=project)
    return selection, selected_skills


def query_selected_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
    filters: dict[str, str] | None = None,
) -> tuple[SkillsSelection, list[SelectedSkillMatch]]:
    selection, discovered, selected_skills = _resolve_selected_skills_catalog(start_path, project=project)
    discovered_by_name = {skill.name: skill for skill in discovered}
    results: list[SelectedSkillMatch] = []

    for skill in selected_skills:
        frontmatter = parse_skill_frontmatter(discovered_by_name[skill.name].source_path)
        if filters and not all(frontmatter.get(key) == value for key, value in filters.items()):
            continue
        results.append(SelectedSkillMatch(skill=skill, frontmatter=frontmatter))

    return selection, results


def _selected_skills_status_for_depot(
    depot_root: Path,
    *,
    selected_skills: list[SelectedSkillRecord],
    discovered_by_name: dict[str, DiscoveredSkill],
) -> SkillsDepotStatusResult:
    matching: list[SkillsStatusEntry] = []
    missing: list[SkillsStatusEntry] = []
    broken: list[SkillsStatusEntry] = []
    unsynced: list[SkillsStatusEntry] = []
    conflicts: list[SkillsStatusEntry] = []
    extra: list[SkillsStatusEntry] = []

    expected_names = {skill.name for skill in selected_skills}

    for skill in selected_skills:
        discovered_skill = discovered_by_name[skill.name]
        path = depot_root / skill.name
        expected_source_path = discovered_skill.source_path.resolve()

        if path.is_symlink():
            actual_link_target = os.readlink(path)
            if not path.exists():
                broken.append(
                    SkillsStatusEntry(
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
                    SkillsStatusEntry(
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
                SkillsStatusEntry(
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
                SkillsStatusEntry(
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
            SkillsStatusEntry(
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
                    SkillsStatusEntry(
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
                SkillsStatusEntry(
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
            SkillsStatusEntry(
                name=path.name,
                path=path,
                source=None,
                expected_source_path=None,
                actual_entry_kind=_entry_kind(path),
                actual_link_target=None,
                actual_resolved_target=None,
            )
        )

    return SkillsDepotStatusResult(
        depot_root=depot_root,
        matching=matching,
        missing=missing,
        broken=broken,
        unsynced=unsynced,
        conflicts=conflicts,
        extra=extra,
    )


def selected_skills_status(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> SkillsStatusResult:
    selection, discovered, selected_skills = _resolve_selected_skills_catalog(start_path, project=project)
    discovered_by_name = {skill.name: skill for skill in discovered}

    return SkillsStatusResult(
        selection=selection,
        skills=selected_skills,
        depot_statuses=tuple(
            _selected_skills_status_for_depot(
                depot_root,
                selected_skills=selected_skills,
                discovered_by_name=discovered_by_name,
            )
            for depot_root in selection.depot_roots
        ),
    )


def resolve_selected_skill(
    name: str,
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
) -> tuple[SkillsSelection, SelectedSkillRecord | None]:
    normalized_name = validate_string_for_path(name, field_name="skill name")
    selection, selected_skills = list_selected_skills(start_path, project=project)
    for skill in selected_skills:
        if skill.name == normalized_name:
            return selection, skill
    return selection, None


def import_selected_skills(
    start_path: Path | str = ".",
    *,
    project: Path | str | None = None,
    force: bool = False,
) -> SkillsImportResult:
    selection, discovered, selected_skills = _resolve_selected_skills_catalog(start_path, project=project)

    if not selection.depot_roots:
        return SkillsImportResult(
            selection=selection,
            skills=selected_skills,
            depot_results=(),
        )

    global_depot_root = _skills_global_depot_root(selection)
    for depot_root in selection.depot_roots:
        _preflight_project_depot_global_link(depot_root, force=force)

    global_sync_result = _rebuild_global_depot(global_depot_root, discovered)

    return SkillsImportResult(
        selection=selection,
        skills=selected_skills,
        depot_results=tuple(
            SkillsDepotImportResult(
                depot_root=depot_root,
                sync_result=_replace_project_depot_with_global_link(
                    depot_root,
                    global_depot_root,
                    force=force,
                ),
            )
            for depot_root in selection.depot_roots
        ),
        global_depot_root=global_depot_root,
        global_sync_result=global_sync_result,
    )
