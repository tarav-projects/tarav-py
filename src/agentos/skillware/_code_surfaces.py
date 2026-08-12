# $kw: ^skw-code-surfaces --from Skw.Backend --from Annotation.Point --from Non.Skw.Annotation --from POI.Linter --note [DF] shared selector and strict policy engine for configured code surfaces ^c20260811-66u
"""Configured code-surface selection and language-neutral strict linting."""

from __future__ import annotations

import json
from pathlib import Path

from agentos._core.persistence import atomic_write_json

from ._build_core import (
    CodeSurfaceConfig,
    SkillwareError,
    load_project_skw_config,
    resolve_project_depots,
    unlock_requirements,
)
from ._code_index import index_code_dependency_resolver
from ._code_model import (
    CodeBackendRegistry,
    CodeBlessRecord,
    CodeCheckReport,
    CodeDependencyResolver,
    CodeSurfaceTarget,
)
from ._code_python import PythonCodeBackend
from .model import SkwSource
from .poi import skillware_poi, suppress_blessed


DEFAULT_CODE_BACKENDS = CodeBackendRegistry((PythonCodeBackend(),))


def expand_code_surfaces(
    project_root: Path,
    configs: tuple[CodeSurfaceConfig, ...],
    *,
    backends: CodeBackendRegistry = DEFAULT_CODE_BACKENDS,
) -> tuple[CodeSurfaceTarget, ...]:
    project_root = Path(project_root).resolve()
    targets: dict[Path, CodeSurfaceTarget] = {}
    for config in configs:
        backend = backends.get(config.language)
        if backend is None:
            raise SkillwareError(
                f"unsupported skw code-surface language `{config.language}`"
            )

        def _matches(pattern: str) -> tuple[Path, ...]:
            resolved = tuple(
                sorted(
                    path.resolve()
                    for path in project_root.glob(pattern)
                    if path.is_file()
                )
            )
            escaped = next(
                (path for path in resolved if not path.is_relative_to(project_root)),
                None,
            )
            if escaped is not None:
                raise SkillwareError(
                    f"skw code-surface pattern escapes the project: {pattern}"
                )
            return resolved

        excluded = {path for pattern in config.exclude for path in _matches(pattern)}
        selected_for_config = 0
        local_targets: set[Path] = set()
        for pattern in config.include:
            matches = _matches(pattern)
            if not matches:
                raise SkillwareError(
                    f"skw code-surface include pattern matched no files: {pattern}"
                )
            for path in matches:
                if path in excluded:
                    continue
                if path in local_targets:
                    continue
                if path.suffix not in backend.suffixes:
                    raise SkillwareError(
                        f"skw `{config.language}` code surface has unsupported suffix: "
                        f"{path.relative_to(project_root)}"
                    )
                prior = targets.get(path)
                if prior is not None:
                    raise SkillwareError(
                        "skw code surface selected more than once: "
                        f"{path.relative_to(project_root)}"
                    )
                targets[path] = CodeSurfaceTarget(config.language, path)
                local_targets.add(path)
                selected_for_config += 1
        if not selected_for_config:
            raise SkillwareError(
                f"skw `{config.language}` code surface contains no files after exclusions"
            )
    return tuple(targets[path] for path in sorted(targets))


def _block_open_lines(source: SkwSource) -> list[int]:
    blocks = (*source.recipes, *source.constructs, *source.dependencies)
    return sorted({block.line for block in blocks})


def _file_dependencies(source: SkwSource) -> tuple[str, ...]:
    blocks = (*source.recipes, *source.constructs, *source.dependencies)
    return tuple(
        locator for block in blocks if block.line == 1 for locator in block.froms
    )


def _project_lock(project_root: Path) -> dict:
    path = project_root / ".skw" / "lock.json"
    if not path.is_file():
        return {"schema_version": 1, "files": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillwareError(f"cannot read project Skw lock {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillwareError(f"project Skw lock is not a JSON object: {path}")
    return value


def check_code_surfaces(
    project_root: Path,
    configs: tuple[CodeSurfaceConfig, ...],
    *,
    backends: CodeBackendRegistry = DEFAULT_CODE_BACKENDS,
    dependency_resolver: CodeDependencyResolver | None = None,
) -> CodeCheckReport:
    project_root = Path(project_root).resolve()
    targets = (
        expand_code_surfaces(project_root, configs, backends=backends)
        if configs
        else ()
    )
    pois = []
    resolver = dependency_resolver or index_code_dependency_resolver(())
    for target in targets:
        relative = target.path.relative_to(project_root)
        text = target.path.read_text(encoding="utf-8", errors="replace")
        backend = backends.get(target.language)
        if backend is None:
            raise SkillwareError(
                f"unsupported skw code-surface language `{target.language}`"
            )
        model = backend.model(text)
        if model.surface.diagnostics:
            scanner_error = model.surface.diagnostics[0].message
            pois.append(
                skillware_poi(
                    "parse-error",
                    relative,
                    None,
                    scanner_error,
                    f"{target.language} scanner failed: {scanner_error}",
                )
            )
            continue
        if model.annotations.findings:
            pois.extend(
                skillware_poi(
                    "parse-error",
                    relative,
                    None,
                    f"{finding.line}|{finding.message}",
                    f"line {finding.line}: {finding.message}",
                )
                for finding in model.annotations.findings
            )
            continue

        block_lines = _block_open_lines(model.annotations)
        if 1 not in block_lines:
            pois.append(
                skillware_poi(
                    "missing-header",
                    relative,
                    "file",
                    "missing-header",
                    "configured code file has no line-1 Skw annotation",
                )
            )
        else:
            dependencies = _file_dependencies(model.annotations)
            if not dependencies:
                pois.append(
                    skillware_poi(
                        "undeclared-dependency",
                        relative,
                        "file",
                        "missing-design-dependency",
                        "file annotation declares no Index design dependency",
                    )
                )
            else:
                names = set(dependencies)
                collisions = resolver.collisions(names)
                resolutions = resolver.resolve(names)
                for locator in dependencies:
                    collision = collisions.get(locator, [])
                    if collision:
                        joined = ", ".join(str(path) for path in collision)
                        pois.append(
                            skillware_poi(
                                "dangling-dependency",
                                relative,
                                locator,
                                f"collision:{locator}:{joined}",
                                f"design dependency `{locator}` resolves in multiple depots: {joined}",
                            )
                        )
                        continue
                    resolution = resolutions.get(locator, "unresolved:not found")
                    if resolution.startswith("unresolved:"):
                        pois.append(
                            skillware_poi(
                                "dangling-dependency",
                                relative,
                                locator,
                                f"unresolved:{locator}",
                                f"design dependency `{locator}` does not resolve in the engaged Index depots",
                            )
                        )
        pois.extend(
            skillware_poi(
                "illegal-attachment",
                relative,
                f"line {line}",
                f"line {line}",
                f"line {line}: Skw block attaches off the required file point",
            )
            for line in block_lines
            if line != 1
        )

        machinery_lines = {
            line
            for start, end in model.annotations.machinery_spans
            for line in range(start + 1, end + 1)
        }
        for annotation in model.surface.annotations:
            if annotation.classification != "unclassified":
                continue
            if annotation.span.start_line in machinery_lines:
                continue
            key = (
                f"line {annotation.span.start_line}:{annotation.span.start_column + 1}"
            )
            pois.append(
                skillware_poi(
                    "non-skw-annotation",
                    relative,
                    key,
                    annotation.text,
                    f"{key}: comment is not a Skw.Annotation — {annotation.text!r}",
                )
            )

    visible = tuple(suppress_blessed(_project_lock(project_root), pois))
    return CodeCheckReport(targets=targets, pois=visible)


def bless_code_poi(
    project_root: Path,
    poi_hash: str,
    *,
    unlocks: tuple[str, ...] = (),
) -> CodeBlessRecord:
    project_root = Path(project_root).resolve()
    config = load_project_skw_config(project_root)
    report = check_code_surfaces(
        project_root,
        config.code_surfaces,
        dependency_resolver=index_code_dependency_resolver(
            tuple(resolve_project_depots(project_root))
        ),
    )
    match = next((poi for poi in report.pois if poi.poi_hash == poi_hash), None)
    if match is None:
        raise SkillwareError(
            f"no code-surface POI with hash {poi_hash} in the current project check"
        )
    if match.kind != "non-skw-annotation":
        raise SkillwareError(
            f"POI {poi_hash} ({match.kind}) is not blessable; fix the surface instead"
        )
    provided = set(unlocks)
    missing = [
        requirement
        for requirement in unlock_requirements(project_root, match.kind)
        if requirement.token not in provided
    ]
    if missing:
        surfaces = "\n".join(
            f"- {requirement.surface} (registry: {requirement.registry})"
            for requirement in missing
        )
        raise SkillwareError(
            f"POI {poi_hash} ({match.kind}) requires unlock token(s) from "
            f"these context surfaces:\n{surfaces}"
        )

    lock = _project_lock(project_root)
    blessings = lock.setdefault("blessings", [])
    if not any(record.get("hash") == match.poi_hash for record in blessings):
        blessings.append(
            {
                "hash": match.poi_hash,
                "kind": match.kind,
                "target": str(match.target_path),
                "key": match.key,
            }
        )
    atomic_write_json(project_root / ".skw" / "lock.json", lock)
    return CodeBlessRecord(match.target_path, match.key, match.poi_hash)
