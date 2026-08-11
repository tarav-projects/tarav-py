# $kw: --from Skill.Package.Builder --from Skw.Network
"""Skillware configuration, source loading, and deterministic expansion."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from agentos.index.model import BlockHeading, KernelLine, MetaLine, parse_depot
from agentos.skillware.model import (
    SkwFinding,
    SkwRouterRow,
    SkwRoutingView,
    SkwSource,
    parse_skw_source,
    recipe_key,
)

SRC_SUFFIX = ".skw.md"
BUILD_DIR = ".skw"
LEGACY_BUILD_DIR = ".skillware"
SETTINGS_NAME = "skw.json"
LEGACY_SETTINGS_NAME = "skillware.json"


def resolve_build_root(skill_root: Path) -> Path:
    """The `.skw/` build home for a package, preferring the current `.skw/`
    layout and falling back to the legacy `.skillware/` during the rename
    deprecation window. Defaults to `.skw/` when neither exists yet."""
    current = skill_root / BUILD_DIR
    if (current / "src").is_dir():
        return current
    legacy = skill_root / LEGACY_BUILD_DIR
    if (legacy / "src").is_dir():
        return legacy
    return current


def _settings_path(build_root: Path) -> Path | None:
    for name in (SETTINGS_NAME, LEGACY_SETTINGS_NAME):
        candidate = build_root / name
        if candidate.is_file():
            return candidate
    return None


class SkillwareError(Exception):
    pass


@dataclass
class Skillware:
    skill_root: Path
    build_root: Path
    src_root: Path
    depots: tuple[Path, ...]
    package_id: str | None = None
    pkg_deps: dict[str, Path] = field(default_factory=dict)
    _depot_cache: dict = field(default_factory=dict, repr=False)

    def src_files(self) -> list[Path]:
        return sorted(
            path.relative_to(self.src_root)
            for path in self.src_root.rglob(f"*{SRC_SUFFIX}")
            if path.is_file()
        )

    def target_rel(self, src_rel: Path) -> Path:
        name = src_rel.name[: -len(SRC_SUFFIX)] + ".md"
        return src_rel.parent / name


@dataclass(frozen=True)
class Expansion:
    src_rel: Path
    target_rel: Path
    fresh_lines: tuple[str, ...]
    src_refresh_lines: tuple[str, ...]
    dep_hashes: dict[str, dict[str, str | None]]
    findings: tuple[SkwFinding, ...]


@dataclass(frozen=True)
class _DepotNameEntry:
    canonical: str
    body: tuple[str, ...]


PROJECT_MARKER = Path(".agentos") / "project.json"
_SKW_CONFIG_KEYS = (
    "id",
    "depots",
    "deps",
    "edition_history",
    "surfaces",
    "exclude",
    "projects",
    "unlock_registries",
    "code_surfaces",
)
_PACKAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_UNLOCK_TOKEN_RE = re.compile(r"^skw-unlock:[0-9a-f]{12,64}$")


@dataclass(frozen=True)
class EditionHistoryConfig:
    """Project-level file selectors for the edition-history linter."""

    targets: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    depot: str | None = None


@dataclass(frozen=True)
class CodeSurfaceConfig:
    """One language-typed, project-relative code-surface selector."""

    language: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkwConfig:
    """A `skw.json` — the same schema at project and package scope.

    All keys optional: `id` (stable package identity), `depots` (resolution
    roots), `deps` (the named
    `Skw.Pkg.Dependency` registry — `id → package-root`, serving both the
    concept domain, folded into the depot search, and the file domain,
    addressed as `@<id>/…`), `surfaces` (managed set; empty → discover),
    `exclude` (trim), `code_surfaces` (language-typed project file selectors),
    `projects` (sibling project roots whose project-level
    depots extend cross-repo resolution), and `unlock_registries` (explicit
    Poi.Unlock.Token registry files)."""

    id: str | None = None
    depots: tuple[str, ...] = ()
    deps: dict[str, str] = field(default_factory=dict)
    surfaces: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    unlock_registries: tuple[str, ...] = ()
    code_surfaces: tuple[CodeSurfaceConfig, ...] = ()
    edition_history: EditionHistoryConfig | None = None
    warnings: tuple[str, ...] = ()


def parse_skw_config(config_path: Path) -> SkwConfig:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SkillwareError(f"skw config is not a JSON object: {config_path}")
    warnings = tuple(
        f"unknown skw.json key `{key}` in {config_path}"
        for key in raw
        if key not in _SKW_CONFIG_KEYS
    )

    def _list(key: str) -> tuple[str, ...]:
        value = raw.get(key, [])
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise SkillwareError(
                f"skw.json `{key}` must be a list of strings: {config_path}"
            )
        return tuple(value)

    def _map(key: str) -> dict[str, str]:
        value = raw.get(key, {})
        if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            raise SkillwareError(
                f"skw.json `{key}` must be an object of string→string: {config_path}"
            )
        return dict(value)

    package_id = raw.get("id")
    if package_id is not None and (
        not isinstance(package_id, str) or _PACKAGE_ID_RE.fullmatch(package_id) is None
    ):
        raise SkillwareError(
            f"skw.json `id` must be a canonical package id: {config_path}"
        )

    def _edition_history() -> EditionHistoryConfig | None:
        value = raw.get("edition_history")
        if value is None:
            return None
        if not isinstance(value, dict):
            raise SkillwareError(
                f"skw.json `edition_history` must be an object: {config_path}"
            )
        unknown = set(value) - {"targets", "exclude", "depot"}
        if unknown:
            raise SkillwareError(
                "unknown skw.json `edition_history` key(s) "
                f"{', '.join(sorted(unknown))}: {config_path}"
            )

        def _patterns(key: str, *, required: bool = False) -> tuple[str, ...]:
            patterns = value.get(key)
            if patterns is None and not required:
                return ()
            if (
                not isinstance(patterns, list)
                or (required and not patterns)
                or not all(isinstance(pattern, str) and pattern for pattern in patterns)
            ):
                qualifier = "non-empty " if required else ""
                raise SkillwareError(
                    f"skw.json `edition_history.{key}` must be a "
                    f"{qualifier}list of strings: {config_path}"
                )
            for pattern in patterns:
                path = Path(pattern)
                if path.is_absolute() or ".." in path.parts:
                    raise SkillwareError(
                        f"skw.json `edition_history.{key}` patterns must be "
                        f"project-relative: {config_path}"
                    )
            return tuple(patterns)

        depot = value.get("depot")
        if depot is not None and (
            not isinstance(depot, str)
            or not depot
            or Path(depot).is_absolute()
            or ".." in Path(depot).parts
        ):
            raise SkillwareError(
                "skw.json `edition_history.depot` must be a non-empty "
                f"project-relative string: {config_path}"
            )
        return EditionHistoryConfig(
            targets=_patterns("targets", required=True),
            exclude=_patterns("exclude"),
            depot=depot,
        )

    def _code_surfaces() -> tuple[CodeSurfaceConfig, ...]:
        value = raw.get("code_surfaces", [])
        if not isinstance(value, list):
            raise SkillwareError(
                f"skw.json `code_surfaces` must be a list: {config_path}"
            )
        result = []
        for index, item in enumerate(value):
            label = f"code_surfaces[{index}]"
            if not isinstance(item, dict):
                raise SkillwareError(
                    f"skw.json `{label}` must be an object: {config_path}"
                )
            unknown = set(item) - {"language", "include", "exclude"}
            if unknown:
                raise SkillwareError(
                    f"unknown skw.json `{label}` key(s) "
                    f"{', '.join(sorted(unknown))}: {config_path}"
                )
            language = item.get("language")
            if not isinstance(language, str) or not re.fullmatch(
                r"[a-z][a-z0-9-]*", language
            ):
                raise SkillwareError(
                    f"skw.json `{label}.language` must be a canonical name: "
                    f"{config_path}"
                )

            def _patterns(key: str, *, required: bool) -> tuple[str, ...]:
                patterns = item.get(key)
                if patterns is None and not required:
                    return ()
                if (
                    not isinstance(patterns, list)
                    or (required and not patterns)
                    or not all(isinstance(pattern, str) and pattern for pattern in patterns)
                ):
                    qualifier = "non-empty " if required else ""
                    raise SkillwareError(
                        f"skw.json `{label}.{key}` must be a {qualifier}list "
                        f"of strings: {config_path}"
                    )
                for pattern in patterns:
                    path = Path(pattern)
                    if path.is_absolute() or ".." in path.parts:
                        raise SkillwareError(
                            f"skw.json `{label}.{key}` patterns must be "
                            f"project-relative: {config_path}"
                        )
                return tuple(patterns)

            result.append(
                CodeSurfaceConfig(
                    language=language,
                    include=_patterns("include", required=True),
                    exclude=_patterns("exclude", required=False),
                )
            )
        return tuple(result)

    return SkwConfig(
        id=package_id,
        depots=_list("depots"),
        deps=_map("deps"),
        surfaces=_list("surfaces"),
        exclude=_list("exclude"),
        projects=_list("projects"),
        unlock_registries=_list("unlock_registries"),
        code_surfaces=_code_surfaces(),
        edition_history=_edition_history(),
        warnings=warnings,
    )


@dataclass(frozen=True)
class UnlockRequirement:
    token: str
    surface: str
    registry: Path


@dataclass(frozen=True)
class _UnlockKindRequirement(UnlockRequirement):
    kind: str


def _parse_unlock_registry(
    registry_path: Path,
) -> tuple[_UnlockKindRequirement, ...]:
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillwareError(
            f"cannot read unlock registry {registry_path}: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise SkillwareError(f"unlock registry is not a JSON object: {registry_path}")
    if set(raw) != {"schema_version", "tokens"}:
        raise SkillwareError(
            f"unlock registry must contain exactly schema_version and tokens: {registry_path}"
        )
    if raw["schema_version"] != 1:
        raise SkillwareError(
            f"unsupported unlock registry schema_version in {registry_path}: "
            f"{raw['schema_version']!r}"
        )
    entries = raw["tokens"]
    if not isinstance(entries, list):
        raise SkillwareError(f"unlock registry tokens must be a list: {registry_path}")

    requirements: list[_UnlockKindRequirement] = []
    seen_tokens: set[str] = set()
    seen_surfaces: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"{registry_path} tokens[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"token", "surface", "unlocks"}:
            raise SkillwareError(
                f"{where} must contain exactly token, surface, and unlocks"
            )
        token = entry["token"]
        surface = entry["surface"]
        unlocks = entry["unlocks"]
        if not isinstance(token, str) or _UNLOCK_TOKEN_RE.fullmatch(token) is None:
            raise SkillwareError(
                f"{where} token must match skw-unlock:<12-64 lowercase hex>"
            )
        if not isinstance(surface, str) or not surface.strip():
            raise SkillwareError(f"{where} surface must be a non-empty string")
        if token in seen_tokens:
            raise SkillwareError(f"duplicate unlock token: {token}")
        if surface in seen_surfaces:
            raise SkillwareError(
                f"duplicate unlock surface: {surface} ({registry_path})"
            )
        seen_tokens.add(token)
        seen_surfaces.add(surface)
        if (
            not isinstance(unlocks, list)
            or not unlocks
            or not all(isinstance(kind, str) and kind for kind in unlocks)
            or len(unlocks) != len(set(unlocks))
        ):
            raise SkillwareError(
                f"{where} unlocks must be a non-empty list of unique POI kinds"
            )
        requirements.extend(
            _UnlockKindRequirement(
                token=token,
                surface=surface,
                registry=registry_path,
                kind=kind,
            )
            for kind in unlocks
        )
    return tuple(requirements)


def _split_unlock_surface(surface: str, registry_path: Path) -> tuple[Path, str]:
    separators = [separator for separator in ("^", "#") if separator in surface]
    if len(separators) != 1:
        raise SkillwareError(
            f"unlock surface must be one addressed source locator: "
            f"{surface} ({registry_path})"
        )
    separator = separators[0]
    path_part, address_part = surface.split(separator, 1)
    if not path_part or not address_part:
        raise SkillwareError(
            f"unlock surface must include a source path and address: "
            f"{surface} ({registry_path})"
        )
    return Path(path_part), f"{separator}{address_part}"


def _validate_unlock_surface(requirement: UnlockRequirement) -> None:
    registry_path = requirement.registry
    if registry_path.parent.name != BUILD_DIR:
        raise SkillwareError(
            f"unlock registry must live at <package>/{BUILD_DIR}/: {registry_path}"
        )
    owner = registry_path.parent.parent
    source_rel, address = _split_unlock_surface(requirement.surface, registry_path)
    source_path = owner / BUILD_DIR / "src" / source_rel
    if not source_path.is_file():
        raise SkillwareError(
            f"unlock surface source not found: {requirement.surface} "
            f"(registry: {registry_path})"
        )
    source = parse_skw_source(source_path.read_text(encoding="utf-8"))
    if source.findings:
        first = source.findings[0]
        raise SkillwareError(
            f"unlock surface does not parse: {requirement.surface}:{first.line}: "
            f"{first.message}"
        )
    matches = [
        dependency
        for dependency in source.dependencies
        if dependency.address == address and dependency.unlock_surface
    ]
    if not matches:
        raise SkillwareError(
            f"unlock surface is not marked --unlock-surface: "
            f"{requirement.surface} (registry: {registry_path})"
        )
    dependency = matches[0]
    back_references = []
    for raw in dependency.froms:
        for base in (owner / BUILD_DIR / "src", owner):
            candidate = (base / raw).resolve()
            if candidate.is_file():
                back_references.append(candidate)
                break
    if registry_path.resolve() not in back_references:
        raise SkillwareError(
            f"unlock surface does not --from its registry: "
            f"{requirement.surface} (registry: {registry_path})"
        )


def _all_unlock_requirements(skill_root: Path) -> tuple[_UnlockKindRequirement, ...]:
    skill_root = Path(skill_root)
    build_root = resolve_build_root(skill_root)
    settings_path = _settings_path(build_root)
    if settings_path is None:
        return ()
    config = parse_skw_config(settings_path)
    requirements: list[_UnlockKindRequirement] = []
    for raw_registry in config.unlock_registries:
        registry_path = (skill_root / raw_registry).resolve()
        if not registry_path.is_file():
            raise SkillwareError(
                f"configured unlock registry is not a file: {raw_registry}"
            )
        requirements.extend(_parse_unlock_registry(registry_path))

    token_surfaces: dict[str, tuple[Path, str]] = {}
    surface_tokens: dict[tuple[Path, str], str] = {}
    validated: set[tuple[Path, str]] = set()
    for requirement in requirements:
        surface_key = (requirement.registry, requirement.surface)
        prior_surface = token_surfaces.setdefault(requirement.token, surface_key)
        if prior_surface != surface_key:
            raise SkillwareError(f"duplicate unlock token: {requirement.token}")
        prior_token = surface_tokens.setdefault(surface_key, requirement.token)
        if prior_token != requirement.token:
            raise SkillwareError(
                f"duplicate unlock surface: {requirement.surface} "
                f"({requirement.registry})"
            )
        if surface_key not in validated:
            _validate_unlock_surface(requirement)
            validated.add(surface_key)
    return tuple(requirements)


def unlock_requirements(
    skill_root: Path, poi_kind: str
) -> tuple[UnlockRequirement, ...]:
    return tuple(
        UnlockRequirement(
            token=requirement.token,
            surface=requirement.surface,
            registry=requirement.registry,
        )
        for requirement in _all_unlock_requirements(skill_root)
        if requirement.kind == poi_kind
    )


def find_project_root(start: Path) -> Path | None:
    """Walk up from `start` to the nearest `.agentos/project.json` marker."""
    start = Path(start).resolve()
    for candidate in (start, *start.parents):
        if (candidate / PROJECT_MARKER).is_file():
            return candidate
    return None


def _config_path(root: Path) -> Path | None:
    build_root = resolve_build_root(root)
    return _settings_path(build_root)


def load_project_skw_config(project_root: Path) -> SkwConfig:
    """Load the project-level Skillware configuration, if present."""
    config_path = _config_path(Path(project_root).resolve())
    return parse_skw_config(config_path) if config_path is not None else SkwConfig()


def expand_edition_history_targets(
    project_root: Path,
    config: EditionHistoryConfig,
) -> tuple[Path, ...]:
    """Expand a project's edition-history include set, then subtract excludes."""
    project_root = Path(project_root).resolve()

    def _files(patterns: tuple[str, ...]) -> set[Path]:
        matches: set[Path] = set()
        for pattern in patterns:
            for candidate in project_root.glob(pattern):
                resolved = candidate.resolve()
                if resolved.is_file() and resolved.is_relative_to(project_root):
                    matches.add(resolved)
        return matches

    targets = _files(config.targets) - _files(config.exclude)
    if not targets:
        raise SkillwareError(
            "skw.json `edition_history.targets` matched no files after exclusions"
        )
    return tuple(sorted(targets))


def resolve_project_depots(project_root: Path) -> list[Path]:
    """Project-scope default depots: the project config's own `depots` plus,
    one level deep, each sibling `projects` root's project-level `depots`."""
    depots: list[Path] = []
    config_path = _config_path(project_root)
    if config_path is None:
        return depots
    config = parse_skw_config(config_path)
    for raw in config.depots:
        depot = (project_root / raw).resolve()
        if depot.is_dir():
            depots.append(depot)
    for raw_project in config.projects:
        sibling = (project_root / raw_project).resolve()
        sibling_config = _config_path(sibling)
        if sibling_config is None:
            continue
        for raw in parse_skw_config(sibling_config).depots:
            depot = (sibling / raw).resolve()
            if depot.is_dir():
                depots.append(depot)
    return depots


def load_skillware(skill_root: Path, extra_depots: tuple[Path, ...] = ()) -> Skillware:
    skill_root = Path(skill_root)
    build_root = resolve_build_root(skill_root)
    src_root = build_root / "src"
    if not src_root.is_dir():
        raise SkillwareError(f"not a skw package (no {BUILD_DIR}/src): {skill_root}")
    depots: list[Path] = []
    pkg_deps: dict[str, Path] = {}
    package_id: str | None = None
    settings_path = _settings_path(build_root)
    if settings_path is not None:
        config = parse_skw_config(settings_path)
        package_id = config.id
        for raw_depot in config.depots:
            depot = (skill_root / raw_depot).resolve()
            if not depot.is_dir():
                raise SkillwareError(
                    f"configured depot is not a directory: {raw_depot}"
                )
            depots.append(depot)



        for dep_id, raw_root in config.deps.items():
            dep_root = (skill_root / raw_root).resolve()
            if not dep_root.is_dir():
                raise SkillwareError(
                    f"configured dep `{dep_id}` is not a directory: {raw_root}"
                )
            pkg_deps[dep_id] = dep_root
            if dep_root not in depots:
                depots.append(dep_root)
    for depot in extra_depots:
        if depot not in depots:
            depots.append(depot)
    return Skillware(
        skill_root=skill_root,
        build_root=build_root,
        src_root=src_root,
        depots=tuple(depots),
        package_id=package_id,
        pkg_deps=pkg_deps,
    )


def content_hash(lines: list[str] | tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _role_edges(block) -> tuple[tuple[str, str], ...]:
    edges: list[tuple[str, str]] = []
    edges.extend(("from", locator) for locator in block.froms)
    edges.extend(("dev-from", locator) for locator in block.dev_froms)
    edges.extend(("cite", locator) for locator in block.cites)
    return tuple(edges)


def _edge_hash_key(role: str, locator: str) -> str:
    return locator if role == "from" else f"{role}:{locator}"


def _routing_load_exists(skillware: Skillware, raw: str) -> bool:
    package_match = _PKG_DEP_RE.fullmatch(raw)
    if package_match is not None:
        dep_id, raw = package_match.groups()
        package_root = skillware.pkg_deps.get(dep_id)
        if package_root is None:
            return False
        root = package_root
    elif raw.startswith("@<"):
        return False
    else:
        root = skillware.skill_root
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return False
    target = root / path
    if target.exists():
        return True
    if root != skillware.skill_root:
        try:
            dependency = load_skillware(root)
        except SkillwareError:
            return False
        if path.suffix != ".md":
            return (dependency.src_root / path).exists()
        source_name = path.name[: -len(".md")] + SRC_SUFFIX
        return (dependency.src_root / path.with_name(source_name)).exists()
    if path.suffix != ".md":
        return (skillware.src_root / path).exists()
    source_name = path.name[: -len(".md")] + SRC_SUFFIX
    return (skillware.src_root / path.with_name(source_name)).exists()


def expand_file(skillware: Skillware, src_rel: Path) -> Expansion:
    src_rel = Path(src_rel)
    text = (skillware.src_root / src_rel).read_text(encoding="utf-8")
    source = parse_skw_source(text)
    findings: list[SkwFinding] = list(source.findings)
    dep_hashes: dict[str, dict[str, str | None]] = {}

    resolved_copies: dict[tuple[int, int], list[str]] = {}
    for recipe in source.recipes:
        recipe_deps: dict[str, str | None] = {}
        for role, locator in _role_edges(recipe):
            lines, detail = _resolve_locator(skillware, locator, stack=(src_rel,))
            key = _edge_hash_key(role, locator)
            if lines is None:
                findings.append(
                    SkwFinding(
                        recipe.line, f"unresolvable {role}: {locator} ({detail})"
                    )
                )
                recipe_deps[key] = None
                continue
            recipe_deps[key] = content_hash(lines)
            if role == "from" and recipe.verb == "copy" and locator == recipe.froms[0]:
                resolved_copies[recipe.body_span] = lines
        dep_hashes[recipe_key(recipe)] = recipe_deps




    for block in (*source.dependencies, *source.constructs):
        edges = list(("dev-from", locator) for locator in block.dev_froms)
        edges.extend(("cite", locator) for locator in block.cites)
        if getattr(block, "context_assembly", False):
            edges.extend(("from", locator) for locator in block.froms)
        for role, locator in edges:
            lines, detail = _resolve_locator(skillware, locator, stack=(src_rel,))
            if lines is None:
                findings.append(
                    SkwFinding(block.line, f"unresolvable {role}: {locator} ({detail})")
                )

    for row in source.router_rows:
        for load in row.loads:
            if not _routing_load_exists(skillware, load):
                findings.append(
                    SkwFinding(row.line, f"unresolvable router load: {load}")
                )

    fresh = _emit(source, resolved_copies, keep_machinery=False)
    refreshed = _emit(source, resolved_copies, keep_machinery=True)
    return Expansion(
        src_rel=src_rel,
        target_rel=skillware.target_rel(src_rel),
        fresh_lines=tuple(fresh),
        src_refresh_lines=tuple(refreshed),
        dep_hashes=dep_hashes,
        findings=tuple(findings),
    )


def _expand_lines(
    skillware: Skillware, src_rel: Path, stack: tuple[Path, ...]
) -> tuple[list[str], list[SkwFinding]]:
    if src_rel in stack:
        chain = " -> ".join(str(entry) for entry in (*stack, src_rel))
        return [], [SkwFinding(0, f"import cycle: {chain}")]
    path = skillware.src_root / src_rel
    if not path.is_file():
        return [], [SkwFinding(0, f"src file not found: {src_rel}")]
    source = parse_skw_source(path.read_text(encoding="utf-8"))
    findings = [SkwFinding(f.line, f"{src_rel}: {f.message}") for f in source.findings]
    resolved_copies: dict[tuple[int, int], list[str]] = {}
    for recipe in source.recipes:
        if recipe.verb != "copy":
            continue
        lines, detail = (
            _resolve_locator(skillware, recipe.froms[0], stack=(*stack, src_rel))
            if recipe.froms
            else (None, "no from")
        )
        if lines is None:
            findings.append(
                SkwFinding(
                    recipe.line,
                    f"{src_rel}: unresolvable from: {recipe.froms[0] if recipe.froms else '?'} ({detail})",
                )
            )
            continue
        resolved_copies[recipe.body_span] = lines
    return _emit(source, resolved_copies, keep_machinery=False), findings


_PKG_DEP_RE = re.compile(r"^@<([^<>/]+)>/(.+)$")

_ESCAPE_DETAIL = (
    "cross-package --from must go through a registered dependency id "
    "(@<id>/…), not a path leaving the package"
)


def _escapes(path_part: str) -> bool:
    """A file locator whose path leaves the package — absolute, or climbing out
    with `..`. The only sanctioned way across the boundary is `@<id>/…`."""
    parts = Path(path_part)
    return parts.is_absolute() or ".." in parts.parts


def _target_skillware(skillware: Skillware, pkg_root: Path) -> Skillware | None:
    key = ("pkgskw", pkg_root)
    cached = skillware._depot_cache.get(key)
    if cached is not None:
        return cached
    try:
        target = load_skillware(pkg_root)
    except SkillwareError:
        return None
    skillware._depot_cache[key] = target
    return target


def _resolve_locator(
    skillware: Skillware, locator: str, *, stack: tuple[Path, ...]
) -> tuple[list[str] | None, str | None]:
    locator = locator.strip()




    pkg_match = _PKG_DEP_RE.match(locator)
    if pkg_match:
        dep_id, tail = pkg_match.group(1), pkg_match.group(2)
        pkg_root = skillware.pkg_deps.get(dep_id)
        if pkg_root is None:
            return (
                None,
                f"unknown dependency id <{dep_id}>: declare it in skw.json `deps`",
            )
        target = _target_skillware(skillware, pkg_root)
        if target is None:
            return None, f"dependency id <{dep_id}> is not a skw package: {pkg_root}"
        return _resolve_locator(target, tail, stack=(Path("."),))

    if "^" in locator and "#" not in locator:
        path_part, label = locator.split("^", 1)
        path_part = path_part.strip()
        label = label.strip()
        if path_part and _escapes(path_part):
            return None, _ESCAPE_DETAIL
        src_rel = Path(path_part) if path_part else stack[-1]
        path = skillware.src_root / src_rel
        if not path.is_file():
            return None, f"src file not found: {path_part or src_rel}"
        return _labeled_span(skillware, src_rel, label, stack=(*stack, src_rel))

    if "#" in locator:
        path_part, region = locator.split("#", 1)
        region = region.strip()
    else:
        path_part, region = locator, None
    path_part = path_part.strip()

    if "/" in path_part or path_part.endswith(".md"):
        if _escapes(path_part):
            return None, _ESCAPE_DETAIL
        if path_part.endswith(SRC_SUFFIX):
            src_rel = Path(path_part)
            if not (skillware.src_root / src_rel).is_file():
                return None, f"src file not found: {path_part}"
            lines, child_findings = _expand_lines(skillware, src_rel, stack)
            if child_findings:
                return None, "; ".join(f.message for f in child_findings)
        else:
            file_path = None
            for base in (skillware.src_root, skillware.skill_root):
                candidate = base / path_part
                if candidate.is_file():
                    file_path = candidate
                    break
            if file_path is None:
                return None, f"file not found: {path_part}"
            lines = file_path.read_text(encoding="utf-8").splitlines()
        if region is None:
            return _trim(lines), None
        body = _region_body(lines, region)
        if body is None:
            return None, f"region not found: #{region}"
        return body, None


    if not skillware.depots:
        return None, "Dotted.Name target needs a depot in skillware.json"
    for depot in skillware.depots:
        entry = _depot_name_index(skillware, depot).get(locator)
        if entry is not None:
            return list(entry.body), None
    return None, "block not found in the configured depots"


def _depot_model(skillware: Skillware, depot: Path):
    key = ("model", depot)
    model = skillware._depot_cache.get(key)
    if model is None:
        model = parse_depot(depot)
        skillware._depot_cache[key] = model
    return model


def _depot_name_index(skillware: Skillware, depot: Path) -> dict[str, _DepotNameEntry]:
    key = ("names", depot)
    index = skillware._depot_cache.get(key)
    if index is None:
        index = _build_depot_name_index(_depot_model(skillware, depot))
        skillware._depot_cache[key] = index
    return index


def _build_depot_name_index(model) -> dict[str, _DepotNameEntry]:
    blocks: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for document in model.documents:
        name: str | None = None
        body: list[str] = []
        aliases: list[str] = []

        def flush() -> None:
            if name is not None:
                blocks.append((name, tuple(body), tuple(aliases)))

        for node in document.nodes:
            if isinstance(node, BlockHeading):
                flush()
                name = str(node.parsed.get("path", "")).strip()
                body = []
                aliases = []
            elif name is not None:
                if isinstance(node, KernelLine):
                    body.append(node.src)
                elif isinstance(node, MetaLine):
                    aliases.extend(_meta_aliases(node))
        flush()

    index: dict[str, _DepotNameEntry] = {}
    canonical_names = {name for name, _body, _aliases in blocks}
    for name, body, _aliases in blocks:
        index[name] = _DepotNameEntry(canonical=name, body=body)
    for name, body, aliases in blocks:
        entry = _DepotNameEntry(canonical=name, body=body)
        for alias in aliases:
            if alias in canonical_names or alias in index:
                continue
            index[alias] = entry
    return index


def _meta_aliases(node: MetaLine) -> list[str]:
    if not node.src.strip().startswith("- aliases:"):
        return []
    return [
        match
        for match in re.findall(r"`([^`]+)`", node.src)
        if _is_dotted_name_locator(match)
    ]


def _depot_block_body(model, name: str) -> list[str] | None:
    entry = _build_depot_name_index(model).get(name)
    return list(entry.body) if entry is not None else None


_DOTTED_NAME_RE = re.compile(
    r"^[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+(?:::[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+)?$"
)


def _is_dotted_name_locator(locator: str) -> bool:
    return bool(_DOTTED_NAME_RE.match(locator.strip()))


def _resolved_dotted_names(skillware: Skillware, names: set[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for name in sorted(names):
        lines, detail = _resolve_locator(skillware, name, stack=(Path("."),))
        if lines is not None:
            resolved[name] = content_hash(lines)
        elif detail is not None:
            resolved[name] = f"unresolved:{detail}"
    return resolved


def resolve_mentions(skillware: Skillware, names: set[str]) -> set[str]:
    return {
        name
        for name, resolution in _resolved_dotted_names(skillware, names).items()
        if not resolution.startswith("unresolved:")
    }


def resolve_dotted_name_canonical(skillware: Skillware, name: str) -> str | None:
    for depot in skillware.depots:
        entry = _depot_name_index(skillware, depot).get(name)
        if entry is not None:
            return entry.canonical
    return None


def _labeled_span(
    skillware: Skillware, src_rel: Path, label: str, *, stack: tuple[Path, ...]
) -> tuple[list[str] | None, str | None]:
    text = (skillware.src_root / src_rel).read_text(encoding="utf-8")
    source = parse_skw_source(text)
    address = f"^{label}"
    for table in source.routing_tables:
        if table.address == address:
            return _routing_table_dependency_lines(table.address, table.selection), None
    for row in source.router_rows:
        if row.address == address:
            return _routing_row_dependency_lines(row), None
    for view in source.routing_views:
        if view.address == address:
            return _routing_view_dependency_lines(view), None
    for recipe in source.recipes:
        if recipe.label == label and recipe.verb == "copy" and recipe.froms:

            return _resolve_locator(skillware, recipe.froms[0], stack=stack)
    spans = [(r.label, r.body) for r in source.recipes] + [
        (c.label, c.body) for c in source.constructs
    ]
    for span_label, body in spans:
        if span_label != label:
            continue
        inner = parse_skw_source("\n".join(body))
        resolved: dict[tuple[int, int], list[str]] = {}
        for rec in inner.recipes:
            if rec.verb != "copy" or not rec.froms:
                continue
            lines, _detail = _resolve_locator(skillware, rec.froms[0], stack=stack)
            if lines is None:


                continue
            resolved[rec.body_span] = lines
        return _emit(inner, resolved, keep_machinery=False), None
    return None, f"label not found: ^{label}"


def _region_body(lines: list[str], region: str) -> list[str] | None:
    start: int | None = None
    level = 0
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or not line.startswith("#"):
            continue
        heading_level = len(line) - len(line.lstrip("#"))
        title = line.lstrip("#").strip()
        if start is None:
            if title == region:
                start = index + 1
                level = heading_level
        elif heading_level <= level:
            return _trim(lines[start:index])
    if start is None:
        return None
    return _trim(lines[start:])


def _trim(lines: list[str]) -> list[str]:
    result = list(lines)
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return result


def _code(value: str) -> str:
    escaped = value.replace("`", r"\`").replace("|", r"\|")
    return f"`{escaped}`"


def _row_resolution(row: SkwRouterRow) -> str:
    parts = [row.match]
    if row.defaults:
        parts.append("default: " + "; ".join(row.defaults))
    return "; ".join(parts)


def _row_route(row: SkwRouterRow) -> str:
    configured = [*row.flags, *row.aliases]
    route = ", ".join(_code(value) for value in configured) or "semantic"
    if row.defaults:
        route += "; default: " + "; ".join(row.defaults)
    return route


def _row_effect(row: SkwRouterRow) -> str:
    if row.then:
        return row.then
    parts: list[str] = []
    if row.destinations:
        parts.append("route to " + ", ".join(_code(value) for value in row.destinations))
    if row.loads:
        parts.append("load " + ", ".join(_code(value) for value in row.loads))
    return "; ".join(parts)


def _routing_table_dependency_lines(address: str, selection: str) -> list[str]:
    return [f"Routing.Table {address}", f"selection: {selection}"]


def _routing_row_dependency_lines(row: SkwRouterRow) -> list[str]:
    lines = [f"Batchy.Router.Row {row.address}", f"table: {row.table}"]
    lines.append(f"match: {row.match}")
    for value in row.flags:
        lines.append(f"flag: {value}")
    for value in row.aliases:
        lines.append(f"alias: {value}")
    for value in row.defaults:
        lines.append(f"default: {value}")
    for value in row.destinations:
        lines.append(f"destination: {value}")
    for value in row.loads:
        lines.append(f"load: {value}")
    if row.when:
        lines.append(f"when: {row.when}")
    if row.then:
        lines.append(f"then: {row.then}")
    return lines


def _routing_view_dependency_lines(view: SkwRoutingView) -> list[str]:
    return [
        f"Routing.View {view.address}",
        f"table: {view.table}",
        f"kind: {view.kind}",
    ]


def _render_calls(rows: list[SkwRouterRow]) -> list[str]:
    explicit = [row for row in rows if row.flags]
    lines = [
        "| Canonical configuration | Aliases | Resolution | Routed effect |",
        "|---|---|---|---|",
    ]
    for row in explicit:
        lines.append(
            "| "
            + "<br>".join(_code(value) for value in row.flags)
            + " | "
            + ("<br>".join(_code(value) for value in row.aliases) or "-")
            + " | "
            + _row_resolution(row).replace("|", r"\|")
            + " | "
            + _row_effect(row).replace("|", r"\|")
            + " |"
        )
    return lines


_MODULE_GROUPS = (
    ("Router Modules", ".Router.Module"),
    ("Workflow Modules", ".Workflow.Module"),
    ("Knowledge Modules", ".Knowledge.Module"),
    ("Operation Modules", ".Operation.Module"),
    ("Context Assembly Modules", ".Assembly.Module"),
)


def _module_loads(row: SkwRouterRow, position: int) -> tuple[str, ...]:
    if len(row.destinations) == len(row.loads):
        return (row.loads[position],)
    return row.loads


def _render_modules(rows: list[SkwRouterRow]) -> list[str]:
    modules: dict[str, dict[str, list[str]]] = {}
    order: list[str] = []
    for row in rows:
        for position, destination in enumerate(row.destinations):
            if not destination.endswith(".Module"):
                continue
            if destination not in modules:
                modules[destination] = {"loads": [], "routes": []}
                order.append(destination)
            entry = modules[destination]
            for load in _module_loads(row, position):
                if load not in entry["loads"]:
                    entry["loads"].append(load)
            route = _row_route(row)
            if route not in entry["routes"]:
                entry["routes"].append(route)

    lines: list[str] = []
    grouped: set[str] = set()
    for heading, suffix in _MODULE_GROUPS:
        names = [name for name in order if name.endswith(suffix)]
        if not names:
            continue
        if lines:
            lines.append("")
        lines.extend(
            [
                f"### {heading}",
                "",
                "| Canonical module | Load target | Routing |",
                "|---|---|---|",
            ]
        )
        for name in names:
            grouped.add(name)
            entry = modules[name]
            loads = "<br>".join(_code(value) for value in entry["loads"]) or "-"
            routes = "<br>".join(entry["routes"]).replace("|", r"\|")
            lines.append(f"| {_code(name)} | {loads} | {routes} |")

    other = [name for name in order if name not in grouped]
    if other:
        if lines:
            lines.append("")
        lines.extend(
            [
                "### Other Modules",
                "",
                "| Canonical module | Load target | Routing |",
                "|---|---|---|",
            ]
        )
        for name in other:
            entry = modules[name]
            loads = "<br>".join(_code(value) for value in entry["loads"]) or "-"
            routes = "<br>".join(entry["routes"]).replace("|", r"\|")
            lines.append(f"| {_code(name)} | {loads} | {routes} |")
    return lines


def _render_full(table_selection: str, rows: list[SkwRouterRow]) -> list[str]:
    lines = [f"Selection cardinality: `{table_selection}`."]
    for row in rows:
        lines.extend(["", f"### {_code(row.address)}", ""])
        lines.append(f"- match: `{row.match}`")
        if row.flags:
            lines.append("- flags: " + ", ".join(_code(value) for value in row.flags))
        if row.aliases:
            lines.append(
                "- aliases: " + ", ".join(_code(value) for value in row.aliases)
            )
        if row.defaults:
            lines.append("- defaults: " + "; ".join(row.defaults))
        if row.destinations:
            lines.append(
                "- destinations: "
                + ", ".join(_code(value) for value in row.destinations)
            )
        if row.loads:
            lines.append("- loads: " + ", ".join(_code(value) for value in row.loads))
        if row.when:
            lines.append(f"- when: {row.when}")
        if row.then:
            lines.append(f"- then: {row.then}")
    return lines


def _render_routing_view(source: SkwSource, view: SkwRoutingView) -> list[str]:
    table = next(
        (candidate for candidate in source.routing_tables if candidate.address == view.table),
        None,
    )
    if table is None:
        return []
    rows = [row for row in source.router_rows if row.table == table.address]
    if view.kind == "calls":
        return _render_calls(rows)
    if view.kind == "modules":
        return _render_modules(rows)
    return _render_full(table.selection, rows)


def _emit(
    source: SkwSource,
    resolved_copies: dict[tuple[int, int], list[str]],
    *,
    keep_machinery: bool,
) -> list[str]:
    masked: set[int] = set()
    replacements: dict[int, list[str]] = {}
    skip_ranges: list[tuple[int, int]] = []

    if not keep_machinery:
        skip_ranges.extend(source.machinery_spans)
        for view in source.routing_views:
            replacements[view.decl_span[0]] = [
                "",
                *_render_routing_view(source, view),
                "",
            ]
    for span, lines in resolved_copies.items():
        replacements[span[0]] = ["", *lines, ""]
        skip_ranges.append((span[0], span[1]))

    for start, end in skip_ranges:
        masked.update(range(start, end))

    output: list[str] = []
    index = 0
    while index < len(source.lines):
        if index in replacements:
            output.extend(replacements[index])
        if index not in masked:
            output.append(source.lines[index])
        index += 1

    if keep_machinery:
        return output
    collapsed: list[str] = []
    for line in output:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line)
    return _trim(collapsed)
