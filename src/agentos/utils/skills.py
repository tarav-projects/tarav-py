from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.project import (
    agentos_home_dir,
    build_not_inside_project_message,
    find_agentos_project_root,
    load_project_config,
    local_storage_paths,
    project_config_path,
)

SKILL_MARKER_FILENAME = "SKILL.md"
DEFAULT_PROJECT_SKILLS_DIRNAME = "skills"
SKILLS_STATE_FILENAME = "skills-links.json"
SKILLS_STATE_CLASS = "agentos.skills.sync-state"
SKILLS_STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SkillsImport:
    name: str
    root: Path
    configured_path: str


@dataclass(frozen=True)
class DiscoveredSkill:
    name: str
    source_path: Path
    import_name: str


@dataclass(frozen=True)
class SkillsPathEntry:
    root: Path
    source_kind: str
    resolved_from_index: int


@dataclass(frozen=True)
class ResolvedSkill:
    name: str
    root: Path
    path: Path
    source_kind: str
    resolved_from_index: int


@dataclass(frozen=True)
class SkillsSyncResult:
    created_links: list[Path]
    updated_links: list[Path]
    removed_links: list[Path]
    matching_links: list[Path]


def resolve_project_root() -> Path:
    env_root = os.getenv("AGENTOS_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def skills_dir() -> Path:
    return resolve_project_root() / "skills"


def list_skill_names() -> list[str]:
    root = skills_dir()
    if not root.exists():
        return []

    names: list[str] = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            names.append(child.name)
    return sorted(names)


def find_skills_project_root(start_path: Path | str = ".") -> Path | None:
    return find_agentos_project_root(start_path)


def global_skills_dir() -> Path:
    return agentos_home_dir() / DEFAULT_PROJECT_SKILLS_DIRNAME


def require_skills_project_root(start_path: Path | str = ".") -> Path:
    project_root = find_skills_project_root(start_path)
    if project_root is None:
        raise CliError(build_not_inside_project_message())
    return project_root


def resolve_project_skills_dir(
    project_root: Path,
    *,
    skills_folder: Path | None = None,
) -> Path:
    root = project_root.expanduser().resolve()
    if skills_folder is None:
        return (root / DEFAULT_PROJECT_SKILLS_DIRNAME).resolve()

    candidate = skills_folder.expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def _load_skills_section(project_root: Path) -> dict[str, object]:
    config_path = project_config_path(project_root)
    payload = load_project_config(config_path)
    section = payload.get("skills")
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise CliError("project config field skills must be a JSON object")
    return section


def load_skills_imports(project_root: Path) -> list[SkillsImport]:
    section = _load_skills_section(project_root)
    imports_payload = section.get("imports", [])
    if not isinstance(imports_payload, list):
        raise CliError("project config field skills.imports must be an array")

    imports: list[SkillsImport] = []
    seen_names: set[str] = set()

    for index, item in enumerate(imports_payload):
        if not isinstance(item, dict):
            raise CliError(f"project config field skills.imports[{index}] must be an object")

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise CliError(f"project config field skills.imports[{index}].enabled must be a boolean")
        if not enabled:
            continue

        name = str(item.get("name", "")).strip()
        if not name:
            raise CliError(f"project config field skills.imports[{index}].name is required")
        if name in seen_names:
            raise CliError(f"duplicate enabled skills import name in project config: {name}")
        seen_names.add(name)

        configured_path = str(item.get("path", "")).strip()
        if not configured_path:
            raise CliError(f"project config field skills.imports[{index}].path is required")

        root = Path(configured_path).expanduser()
        if not root.is_absolute():
            root = (project_root / root)
        root = root.resolve()
        if not root.exists():
            raise CliError(f"skills import '{name}' path does not exist: {root}")
        if not root.is_dir():
            raise CliError(f"skills import '{name}' path is not a directory: {root}")

        imports.append(
            SkillsImport(
                name=name,
                root=root,
                configured_path=configured_path,
            )
        )

    return imports


def discover_skill_dirs(root: Path) -> list[Path]:
    normalized_root = root.expanduser().resolve()
    if not normalized_root.exists():
        raise CliError(f"skills import root does not exist: {normalized_root}")
    if not normalized_root.is_dir():
        raise CliError(f"skills import root is not a directory: {normalized_root}")

    discovered: list[Path] = []

    def walk(current_path: Path, ancestor_dirs: set[Path]) -> None:
        try:
            entries = sorted(current_path.iterdir(), key=lambda entry: entry.name)
        except OSError as exc:
            raise CliError(f"unable to read skills import directory {current_path}: {exc}") from exc

        marker_present = False
        for entry in entries:
            try:
                if entry.is_file() and entry.name == SKILL_MARKER_FILENAME:
                    marker_present = True
                    break
            except OSError:
                continue

        if marker_present:
            discovered.append(current_path)
            return

        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue

            resolved_entry = entry.resolve()
            if resolved_entry in ancestor_dirs:
                continue
            walk(entry, ancestor_dirs | {resolved_entry})

    walk(normalized_root, {normalized_root})
    discovered.sort(key=lambda path: path.relative_to(normalized_root).as_posix())
    return discovered


def discover_imported_skills(imports: list[SkillsImport]) -> list[DiscoveredSkill]:
    discovered: list[DiscoveredSkill] = []
    by_name: dict[str, list[DiscoveredSkill]] = {}

    for item in imports:
        for skill_dir in discover_skill_dirs(item.root):
            skill = DiscoveredSkill(
                name=skill_dir.name,
                source_path=skill_dir.resolve(),
                import_name=item.name,
            )
            discovered.append(skill)
            by_name.setdefault(skill.name, []).append(skill)

    duplicate_names = {name: entries for name, entries in by_name.items() if len(entries) > 1}
    if duplicate_names:
        duplicate_entries = ", ".join(
            f"{name} ({'; '.join(f'{entry.import_name}: {entry.source_path}' for entry in entries)})"
            for name, entries in sorted(duplicate_names.items())
        )
        raise CliError(f"duplicate imported skill names: {duplicate_entries}")

    discovered.sort(key=lambda item: item.name)
    return discovered


def list_target_skill_dirs(target_dir: Path) -> list[Path]:
    root = target_dir.expanduser().resolve()
    if not root.exists():
        return []
    if not root.is_dir():
        raise CliError(f"skills target is not a directory: {root}")

    skill_dirs: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if child.name.startswith("."):
            continue
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        if (child / SKILL_MARKER_FILENAME).is_file():
            skill_dirs.append(child)
    return skill_dirs


def list_target_skill_names(target_dir: Path) -> list[str]:
    return [path.name for path in list_target_skill_dirs(target_dir)]


def resolve_skills_path(
    start_path: Path | str = ".",
    *,
    skills_folder: Path | None = None,
) -> list[SkillsPathEntry]:
    project_root = find_skills_project_root(start_path)
    path_entries: list[SkillsPathEntry] = []

    if project_root is not None:
        path_entries.append(
            SkillsPathEntry(
                root=resolve_project_skills_dir(project_root, skills_folder=skills_folder),
                source_kind="project",
                resolved_from_index=len(path_entries),
            )
        )
    elif skills_folder is not None:
        raise CliError(build_not_inside_project_message())

    path_entries.append(
        SkillsPathEntry(
            root=global_skills_dir().resolve(),
            source_kind="global",
            resolved_from_index=len(path_entries),
        )
    )
    return path_entries


def list_resolved_skills(
    start_path: Path | str = ".",
    *,
    skills_folder: Path | None = None,
) -> list[ResolvedSkill]:
    resolved_by_name: dict[str, ResolvedSkill] = {}

    for entry in resolve_skills_path(start_path, skills_folder=skills_folder):
        for skill_dir in list_target_skill_dirs(entry.root):
            name = skill_dir.name
            if name in resolved_by_name:
                continue
            resolved_by_name[name] = ResolvedSkill(
                name=name,
                root=entry.root,
                path=skill_dir,
                source_kind=entry.source_kind,
                resolved_from_index=entry.resolved_from_index,
            )

    return [resolved_by_name[name] for name in sorted(resolved_by_name)]


def resolve_skill(
    name: str,
    start_path: Path | str = ".",
    *,
    skills_folder: Path | None = None,
) -> ResolvedSkill | None:
    normalized_name = str(name).strip()
    if not normalized_name:
        raise CliError("skill name is required")

    for entry in resolve_skills_path(start_path, skills_folder=skills_folder):
        skill_path = entry.root / normalized_name
        if not skill_path.exists():
            continue
        if not skill_path.is_dir():
            continue
        if not (skill_path / SKILL_MARKER_FILENAME).is_file():
            continue
        return ResolvedSkill(
            name=normalized_name,
            root=entry.root,
            path=skill_path,
            source_kind=entry.source_kind,
            resolved_from_index=entry.resolved_from_index,
        )
    return None


def _resolved_symlink_target(path: Path) -> Path:
    link_target = Path(os.readlink(path))
    if link_target.is_absolute():
        return link_target.resolve()
    return (path.parent / link_target).resolve()


def _relative_symlink_target(link_path: Path, source_path: Path) -> str:
    return os.path.relpath(source_path, start=link_path.parent)


def _skills_state_path(project_root: Path) -> Path:
    return local_storage_paths(project_root)["state"] / SKILLS_STATE_FILENAME


def _state_target_key(project_root: Path, target_dir: Path) -> str:
    normalized_project_root = project_root.expanduser().resolve()
    normalized_target_dir = target_dir.expanduser().resolve()
    try:
        relative = normalized_target_dir.relative_to(normalized_project_root)
    except ValueError:
        return str(normalized_target_dir)
    return relative.as_posix() or "."


def load_skills_sync_state(project_root: Path) -> dict[str, dict[str, str]]:
    state_path = _skills_state_path(project_root)
    if not state_path.exists():
        return {}
    if not state_path.is_file():
        raise CliError(f"skills sync state path is not a file: {state_path}")

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid skills sync state JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise CliError("skills sync state must be a JSON object")
    if payload.get("class") != SKILLS_STATE_CLASS:
        raise CliError(f"skills sync state field class must be '{SKILLS_STATE_CLASS}'")

    targets_payload = payload.get("targets", {})
    if not isinstance(targets_payload, dict):
        raise CliError("skills sync state field targets must be an object")

    state: dict[str, dict[str, str]] = {}
    for target_key, target_payload in targets_payload.items():
        if not isinstance(target_key, str) or not target_key:
            raise CliError("skills sync state target keys must be non-empty strings")
        if not isinstance(target_payload, dict):
            raise CliError(f"skills sync state target payload must be an object: {target_key}")
        links_payload = target_payload.get("links", {})
        if not isinstance(links_payload, dict):
            raise CliError(f"skills sync state target links must be an object: {target_key}")

        links: dict[str, str] = {}
        for skill_name, link_target in links_payload.items():
            if not isinstance(skill_name, str) or not skill_name:
                raise CliError(f"skills sync state skill names must be non-empty strings: {target_key}")
            if not isinstance(link_target, str) or not link_target:
                raise CliError(
                    f"skills sync state link targets must be non-empty strings: {target_key}/{skill_name}"
                )
            links[skill_name] = link_target
        state[target_key] = links

    return state


def write_skills_sync_state(project_root: Path, state: dict[str, dict[str, str]]) -> None:
    state_path = _skills_state_path(project_root)
    normalized_state = {target_key: links for target_key, links in state.items() if links}

    if not normalized_state:
        if state_path.exists():
            state_path.unlink()
        return

    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "class": SKILLS_STATE_CLASS,
        "schema_version": SKILLS_STATE_SCHEMA_VERSION,
        "targets": {
            target_key: {"links": dict(sorted(links.items()))}
            for target_key, links in sorted(normalized_state.items())
        },
    }
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def sync_skills_target(
    project_root: Path,
    target_dir: Path,
    *,
    dry_run: bool = False,
) -> SkillsSyncResult:
    normalized_project_root = project_root.expanduser().resolve()
    normalized_target_dir = target_dir.expanduser().resolve()
    if normalized_target_dir.exists() and not normalized_target_dir.is_dir():
        raise CliError(f"skills target is not a directory: {normalized_target_dir}")

    imports = load_skills_imports(normalized_project_root)
    discovered = discover_imported_skills(imports)
    state = load_skills_sync_state(normalized_project_root)
    target_key = _state_target_key(normalized_project_root, normalized_target_dir)
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
        link_path = normalized_target_dir / skill.name
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
        link_path = normalized_target_dir / skill_name
        if not link_path.is_symlink():
            continue
        if os.readlink(link_path) == previous_link_target:
            remove_specs.append(link_path)

    if conflicts:
        conflict_entries = ", ".join(
            f"{path} (expected link to {source_path})" for path, source_path in conflicts
        )
        raise CliError(f"skills sync found conflicting existing paths: {conflict_entries}")

    if not dry_run:
        if create_specs or update_specs:
            normalized_target_dir.mkdir(parents=True, exist_ok=True)
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
        write_skills_sync_state(normalized_project_root, state)

    return SkillsSyncResult(
        created_links=[path for path, _ in create_specs],
        updated_links=[path for path, _ in update_specs],
        removed_links=remove_specs,
        matching_links=matching_links,
    )


def prune_skills_target(
    project_root: Path,
    target_dir: Path,
    *,
    dry_run: bool = False,
) -> list[Path]:
    normalized_project_root = project_root.expanduser().resolve()
    normalized_target_dir = target_dir.expanduser().resolve()
    state = load_skills_sync_state(normalized_project_root)
    target_key = _state_target_key(normalized_project_root, normalized_target_dir)
    previous_links = state.get(target_key, {})

    pruned_links: list[Path] = []
    remaining_links: dict[str, str] = {}

    for skill_name, previous_link_target in previous_links.items():
        link_path = normalized_target_dir / skill_name
        if link_path.is_symlink() and os.readlink(link_path) == previous_link_target and not link_path.exists():
            pruned_links.append(link_path)
            continue
        if link_path.is_symlink() or link_path.exists():
            remaining_links[skill_name] = previous_link_target

    if not dry_run:
        for link_path in pruned_links:
            if link_path.is_symlink():
                link_path.unlink()

        if remaining_links:
            state[target_key] = dict(sorted(remaining_links.items()))
        else:
            state.pop(target_key, None)
        write_skills_sync_state(normalized_project_root, state)

    return pruned_links
