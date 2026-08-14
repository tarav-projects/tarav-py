# $kw: --from Agentos.Skills
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarav._core.errors import CliError

SKILL_MARKER_FILENAME = "SKILL.md"
_FRONTMATTER_DELIMITER = "---"


@dataclass(frozen=True)
class SkillsImportFilter:
    include: tuple[str, ...] | None
    exclude: tuple[str, ...]
    field_label: str


@dataclass(frozen=True)
class SkillsImport:
    name: str
    root: Path
    configured_path: str
    filters: tuple[SkillsImportFilter, ...] = ()


@dataclass(frozen=True)
class DiscoveredSkill:
    name: str
    source_path: Path
    import_name: str


@dataclass(frozen=True)
class SkillsSyncResult:
    created_links: list[Path]
    updated_links: list[Path]
    removed_links: list[Path]
    matching_links: list[Path]


@dataclass(frozen=True)
class _DiscoveredSkillCandidate:
    skill: DiscoveredSkill
    match_names: frozenset[str]
    filters: tuple[SkillsImportFilter, ...]


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


def _validate_skill_filter_references(candidates: list[_DiscoveredSkillCandidate]) -> None:
    filter_candidates: dict[SkillsImportFilter, list[_DiscoveredSkillCandidate]] = {}
    filter_order: list[SkillsImportFilter] = []
    for candidate in candidates:
        for skill_filter in candidate.filters:
            if skill_filter not in filter_candidates:
                filter_order.append(skill_filter)
                filter_candidates[skill_filter] = []
            filter_candidates[skill_filter].append(candidate)

    for skill_filter in filter_order:
        known_names = {
            name
            for candidate in filter_candidates[skill_filter]
            for name in candidate.match_names
        }
        filter_fields = (
            ("include", skill_filter.include),
            ("exclude", skill_filter.exclude),
        )
        for field_name, configured_names in filter_fields:
            if configured_names is None:
                continue
            unknown_names = sorted(
                name for name in configured_names if name not in known_names
            )
            if not unknown_names:
                continue
            formatted_names = ", ".join(unknown_names)
            plural = "s" if len(unknown_names) != 1 else ""
            raise CliError(
                f"{skill_filter.field_label}.{field_name} references unknown skill{plural}: "
                f"{formatted_names}"
            )


def _candidate_matches_filter(
    candidate: _DiscoveredSkillCandidate,
    skill_filter: SkillsImportFilter,
) -> bool:
    if skill_filter.include is not None and not any(
        name in skill_filter.include for name in candidate.match_names
    ):
        return False
    if any(name in skill_filter.exclude for name in candidate.match_names):
        return False
    return True


def _candidate_is_selected(candidate: _DiscoveredSkillCandidate) -> bool:
    return all(
        _candidate_matches_filter(candidate, skill_filter)
        for skill_filter in candidate.filters
    )


def discover_imported_skills(imports: list[SkillsImport]) -> list[DiscoveredSkill]:
    candidates: list[_DiscoveredSkillCandidate] = []
    discovered: list[DiscoveredSkill] = []
    by_name: dict[str, list[DiscoveredSkill]] = {}

    for item in imports:
        for skill_dir in discover_skill_dirs(item.root):
            mapped_name = skill_dir.name
            if mapped_name != item.name and not mapped_name.startswith(f"{item.name}-"):
                mapped_name = f"{item.name}-{mapped_name}"
            skill = DiscoveredSkill(
                name=mapped_name,
                source_path=skill_dir.resolve(),
                import_name=item.name,
            )
            candidates.append(
                _DiscoveredSkillCandidate(
                    skill=skill,
                    match_names=frozenset({skill_dir.name, mapped_name}),
                    filters=item.filters,
                )
            )

    _validate_skill_filter_references(candidates)

    for candidate in candidates:
        if not _candidate_is_selected(candidate):
            continue
        skill = candidate.skill
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


def parse_skill_frontmatter(skill_dir: Path) -> dict[str, str]:
    marker = skill_dir / SKILL_MARKER_FILENAME
    if not marker.is_file():
        return {}
    try:
        text = marker.read_text(encoding="utf-8")
    except OSError:
        return {}

    lines = text.split("\n")
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        return {}

    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == _FRONTMATTER_DELIMITER:
            break
        colon_pos = stripped.find(":")
        if colon_pos < 1:
            continue
        key = stripped[:colon_pos].strip()
        value = stripped[colon_pos + 1:].strip()
        if key:
            frontmatter[key] = value
    return frontmatter
