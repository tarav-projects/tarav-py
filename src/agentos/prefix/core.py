from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.scan import iter_target_files


@dataclass(frozen=True)
class PrefixScanConfig:
    root: Path
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    width: int


@dataclass(frozen=True)
class PrefixRoute:
    name: str
    minimum: int
    maximum: int


@dataclass(frozen=True)
class PrefixPolicy:
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    routes: tuple[PrefixRoute, ...]
    reserved: dict[str, int]
    source: str


@dataclass(frozen=True)
class ProjectPrefixAllocation:
    value: int
    prefix: str
    route: PrefixRoute
    prefixes: set[int]
    reserved_count: int


DEFAULT_PREFIX_WIDTH = 3


def default_prefix_policy() -> PrefixPolicy:
    return PrefixPolicy(
        includes=("notes", "dev/live"),
        excludes=(),
        routes=(
            PrefixRoute(name="notes/index", minimum=100, maximum=499),
            PrefixRoute(name="notes/appendix", minimum=100, maximum=499),
            PrefixRoute(name="*", minimum=500, maximum=999),
        ),
        reserved={
            "notes/index/000-index.md": 0,
            "notes/live/010.TODOS.md": 10,
        },
        source="default",
    )


def _candidate_roots(config: PrefixScanConfig) -> list[Path]:
    if not config.includes:
        return [config.root]

    candidates: list[Path] = []
    for include in config.includes:
        target = (config.root / include).resolve()
        if target.exists():
            candidates.append(target)
    return candidates


def collect_prefixes(config: PrefixScanConfig) -> set[int]:
    pattern = re.compile(rf"^(\d{{{config.width}}})-")
    prefixes: set[int] = set()

    for candidate in _candidate_roots(config):
        for file_path in iter_target_files(
            root=config.root,
            target=candidate,
            excludes=config.excludes,
            recursive=True,
        ):
            match = pattern.match(file_path.name)
            if match:
                prefixes.add(int(match.group(1)))
    return prefixes


def collect_reserved_prefixes(config: PrefixScanConfig, reserved: dict[str, int]) -> set[int]:
    values: set[int] = set()
    for rel_path, value in reserved.items():
        path = (config.root / rel_path).resolve()
        if not path.is_file():
            continue
        try:
            path.relative_to(config.root)
        except ValueError:
            continue
        values.add(value)
    return values


def next_prefix_value(prefixes: set[int], minimum: int) -> int:
    eligible = [value for value in prefixes if value >= minimum]
    if not eligible:
        return minimum
    return max(eligible) + 1


def format_prefix(value: int, width: int) -> str:
    return f"{value:0{width}d}"


def resolve_prefix_route(policy: PrefixPolicy, target: str) -> PrefixRoute:
    normalized_target = target.strip().strip("/")
    matches = [
        route
        for route in policy.routes
        if route.name != "*"
        and (normalized_target == route.name or normalized_target.startswith(f"{route.name}/"))
    ]
    if matches:
        return max(matches, key=lambda route: len(route.name))
    for route in policy.routes:
        if route.name == "*":
            return route
    raise CliError("prefix policy does not define a fallback '*' route")


def next_project_prefix(
    *,
    root: Path,
    target: str,
    policy: PrefixPolicy,
    includes: tuple[str, ...] | None = None,
    excludes: tuple[str, ...] = (),
) -> ProjectPrefixAllocation:
    route = resolve_prefix_route(policy, target)
    scan_config = PrefixScanConfig(
        root=root,
        includes=policy.includes if includes is None else includes,
        excludes=excludes,
        width=DEFAULT_PREFIX_WIDTH,
    )
    prefixes = collect_prefixes(scan_config)
    eligible = {value for value in prefixes if route.minimum <= value <= route.maximum}
    value = next_prefix_value(eligible, route.minimum)
    if value > route.maximum:
        raise CliError(
            f"prefix range exhausted for route {route.name!r}: "
            f"next value {value} exceeds {route.maximum}"
        )
    reserved = collect_reserved_prefixes(scan_config, policy.reserved)
    return ProjectPrefixAllocation(
        value=value,
        prefix=format_prefix(value, DEFAULT_PREFIX_WIDTH),
        route=route,
        prefixes=eligible,
        reserved_count=len(reserved),
    )
