# $kw: ^context-loading-model --supp Context.Loading.Model local projection implementation authorized ^c20260802-1u
"""Path-specific runtime context projection for Skillware-managed skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .build import SRC_SUFFIX, SkillwareError, _resolve_locator, load_skillware
from .model import (
    SkwContextLoadingDependency,
    SkwContextLoadingPath,
    parse_skw_source,
)


@dataclass(frozen=True)
class ContextLoadingEdge:
    kind: str
    provenance: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "provenance": list(self.provenance)}


@dataclass(frozen=True)
class ProjectedContextStep:
    path: str
    edge: ContextLoadingEdge
    content: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "edge": self.edge.as_dict(),
            "content": self.content,
        }


@dataclass(frozen=True)
class ProjectedContextDependency:
    locator: str
    provider: str
    satisfied_at: int
    status: str = "satisfied"

    def as_dict(self) -> dict[str, object]:
        return {
            "locator": self.locator,
            "provider": self.provider,
            "satisfied_at": self.satisfied_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class ProjectedContextPath:
    address: str
    target: str
    steps: tuple[ProjectedContextStep, ...]
    dependencies: tuple[ProjectedContextDependency, ...]
    projected_context: str

    def as_dict(self) -> dict[str, object]:
        return {
            "address": self.address,
            "target": self.target,
            "steps": [step.as_dict() for step in self.steps],
            "dependencies": [dependency.as_dict() for dependency in self.dependencies],
            "projected_context": self.projected_context,
        }


@dataclass(frozen=True)
class ProjectedContextReport:
    skill: str
    target: str
    paths: tuple[ProjectedContextPath, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "command": "agentos skw context",
            "skill": self.skill,
            "target": self.target,
            "paths": [path.as_dict() for path in self.paths],
        }


def _relative_runtime_path(raw: str, *, field: str) -> Path:
    normalized = raw.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or ".." in pure.parts
        or pure == PurePosixPath(".")
    ):
        raise SkillwareError(f"{field} must be a skill-root-relative file: {raw!r}")
    path = Path(*pure.parts)
    if path.parts and path.parts[0] in {".skw", ".skillware"}:
        raise SkillwareError(f"{field} cannot load the .skw build surface: {raw!r}")
    return path


def _load_sources(skillware):
    sources = {}
    src_by_target = {}
    for src_rel in skillware.src_files():
        source = parse_skw_source(
            (skillware.src_root / src_rel).read_text(encoding="utf-8")
        )
        if source.findings:
            first = source.findings[0]
            raise SkillwareError(
                f"cannot project context through {src_rel}:{first.line}: "
                f"{first.message}"
            )
        sources[src_rel] = source
        src_by_target[skillware.target_rel(src_rel)] = src_rel
    return sources, src_by_target


def _routing_edges(skillware, sources) -> dict[tuple[Path, Path], tuple[str, ...]]:
    edges: dict[tuple[Path, Path], list[str]] = {}
    for src_rel, source in sources.items():
        loader = skillware.target_rel(src_rel)
        for row in source.router_rows:
            for raw_load in row.loads:
                loaded = _relative_runtime_path(raw_load, field="Routing.Table --load")
                edges.setdefault((loader, loaded), []).append(
                    f"{loader.as_posix()}{row.address}"
                )
    return {key: tuple(values) for key, values in edges.items()}


def _root_edge(step: Path) -> ContextLoadingEdge:
    if step.name == "AGENTS.md":
        return ContextLoadingEdge("local-agents-root", ("declared path root",))
    if step == Path("SKILL.md"):
        return ContextLoadingEdge("skill-loading-root", ("required SKILL.md",))
    raise SkillwareError(
        "Context.Loading.Path must begin with skill-local AGENTS.md or SKILL.md"
    )


def _edge_for_step(
    prior: Path,
    step: Path,
    *,
    skill_index: int,
    step_index: int,
    routing_edges: dict[tuple[Path, Path], tuple[str, ...]],
) -> ContextLoadingEdge:
    if step_index <= skill_index:
        if step == Path("SKILL.md"):
            return ContextLoadingEdge(
                "skill-loading", ("declared SKILL.md transition",)
            )
        if prior.name == "AGENTS.md" and step.name == "AGENTS.md":
            return ContextLoadingEdge("local-agents", ("declared local scope",))
    provenance = routing_edges.get((prior, step))
    if provenance is None:
        raise SkillwareError(
            f"loading step {prior.as_posix()} -> {step.as_posix()} has no "
            "Routing.Table --load edge"
        )
    return ContextLoadingEdge("routing-table", provenance)


def _loading_dependency_provider(
    skillware,
    dependency: SkwContextLoadingDependency,
    *,
    consumer_src: Path,
) -> tuple[Path, tuple[str, ...]]:
    locator = dependency.locator
    if "^" not in locator or "#" in locator or locator.startswith("@<"):
        raise SkillwareError(
            f"loading dependency must be a local addressed source locator: {locator}"
        )
    path_part, address = locator.split("^", 1)
    if not path_part.endswith(SRC_SUFFIX) or not address:
        raise SkillwareError(
            f"loading dependency must use <file>.skw.md^<address>: {locator}"
        )
    provider_src = _relative_runtime_path(path_part, field="--loading-dep")
    if not (skillware.src_root / provider_src).is_file():
        raise SkillwareError(f"loading dependency source not found: {locator}")
    resolved, detail = _resolve_locator(
        skillware,
        locator,
        stack=(consumer_src,),
    )
    if resolved is None:
        raise SkillwareError(f"unresolvable loading dependency {locator}: {detail}")
    return skillware.target_rel(provider_src), tuple(resolved)


def _trimmed_lines(lines: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = [line.rstrip() for line in lines]
    while normalized and not normalized[0]:
        normalized.pop(0)
    while normalized and not normalized[-1]:
        normalized.pop()
    return tuple(normalized)


def _contains_lines(content: str, expected: tuple[str, ...]) -> bool:
    needle = _trimmed_lines(expected)
    if not needle:
        return False
    haystack = tuple(line.rstrip() for line in content.splitlines())
    width = len(needle)
    return any(
        haystack[index : index + width] == needle for index in range(len(haystack))
    )


def _project_dependencies(
    skillware,
    *,
    consumer_src: Path,
    declaration: SkwContextLoadingPath,
    dependencies: tuple[SkwContextLoadingDependency, ...],
    steps: tuple[Path, ...],
) -> tuple[ProjectedContextDependency, ...]:
    projected: list[ProjectedContextDependency] = []
    seen: set[str] = set()
    for dependency in dependencies:
        if dependency.locator in seen:
            continue
        seen.add(dependency.locator)
        provider, expected = _loading_dependency_provider(
            skillware,
            dependency,
            consumer_src=consumer_src,
        )
        if provider not in steps or steps.index(provider) >= len(steps) - 1:
            raise SkillwareError(
                f"{declaration.address} loading dependency provider must occur earlier "
                f"than the target: {dependency.locator} -> {provider.as_posix()}"
            )
        provider_content = (skillware.skill_root / provider).read_text(encoding="utf-8")
        if not _contains_lines(provider_content, expected):
            raise SkillwareError(
                f"{declaration.address} loading dependency is not materialized in "
                f"{provider.as_posix()}: {dependency.locator}"
            )
        projected.append(
            ProjectedContextDependency(
                locator=dependency.locator,
                provider=provider.as_posix(),
                satisfied_at=steps.index(provider) + 1,
            )
        )
    return tuple(projected)


def _project_path(
    skillware,
    target: Path,
    consumer_src: Path,
    declaration: SkwContextLoadingPath,
    dependencies: tuple[SkwContextLoadingDependency, ...],
    routing_edges: dict[tuple[Path, Path], tuple[str, ...]],
) -> ProjectedContextPath:
    declared_steps = tuple(
        _relative_runtime_path(step, field=f"{declaration.address} --step")
        for step in declaration.steps
    )
    if target in declared_steps:
        raise SkillwareError(
            f"{declaration.address} repeats its implicit target {target.as_posix()}"
        )
    steps = (*declared_steps, target)
    if len(steps) != len(set(steps)):
        raise SkillwareError(f"{declaration.address} contains a repeated loading step")
    skill_index = steps.index(Path("SKILL.md"))

    for step in steps:
        if not (skillware.skill_root / step).is_file():
            raise SkillwareError(
                f"{declaration.address} loading step does not exist: {step.as_posix()}"
            )
    for step in steps[:skill_index]:
        if step.name != "AGENTS.md":
            raise SkillwareError(
                f"{declaration.address} pre-SKILL step must be AGENTS.md: "
                f"{step.as_posix()}"
            )

    projected_steps: list[ProjectedContextStep] = []
    for index, step in enumerate(steps):
        edge = (
            _root_edge(step)
            if index == 0
            else _edge_for_step(
                steps[index - 1],
                step,
                skill_index=skill_index,
                step_index=index,
                routing_edges=routing_edges,
            )
        )
        projected_steps.append(
            ProjectedContextStep(
                path=step.as_posix(),
                edge=edge,
                content=(skillware.skill_root / step).read_text(encoding="utf-8"),
            )
        )
    projected_dependencies = _project_dependencies(
        skillware,
        consumer_src=consumer_src,
        declaration=declaration,
        dependencies=dependencies,
        steps=steps,
    )
    context = "\n\n".join(step.content.rstrip() for step in projected_steps).strip()
    return ProjectedContextPath(
        address=declaration.address,
        target=target.as_posix(),
        steps=tuple(projected_steps),
        dependencies=projected_dependencies,
        projected_context=context,
    )


def project_context(
    skill_root: Path | str,
    target: Path | str,
) -> ProjectedContextReport:
    """Resolve every declared local loading path for one runnable target file."""
    skillware = load_skillware(Path(skill_root))
    target_rel = _relative_runtime_path(str(target), field="--target")
    sources, src_by_target = _load_sources(skillware)
    src_rel = src_by_target.get(target_rel)
    if src_rel is None:
        raise SkillwareError(
            f"context target is not a Skillware-managed file: {target_rel.as_posix()}"
        )
    declarations = sources[src_rel].context_loading_paths
    if not declarations:
        raise SkillwareError(
            f"{target_rel.as_posix()} declares no Context.Loading.Path"
        )
    edges = _routing_edges(skillware, sources)
    paths = tuple(
        _project_path(
            skillware,
            target_rel,
            src_rel,
            declaration,
            sources[src_rel].context_loading_dependencies,
            edges,
        )
        for declaration in declarations
    )
    return ProjectedContextReport(
        skill=str(skillware.skill_root),
        target=target_rel.as_posix(),
        paths=paths,
    )


__all__ = [
    "ContextLoadingEdge",
    "ProjectedContextDependency",
    "ProjectedContextPath",
    "ProjectedContextReport",
    "ProjectedContextStep",
    "project_context",
]
