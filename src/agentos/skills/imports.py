"""Module.Import manifests: discovery, parsing, and the CPU-checkable bindings.

An `Import.Manifest` lives flat on the build surface as
``build/<expanded-relative-path>-<file-name>-imports.md`` and holds one block
per import: heading = target (any legal block name), field lines ``binding:``,
``lands:``, ``context:``. The `pointer` and `copy` bindings are deterministic
checks; `derived` is agentic and only inventoried here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.index.model import BlockHeading, KernelLine, parse_depot, parse_index_file

_MANIFEST_SUFFIX = "-imports.md"
_BINDINGS = ("pointer", "copy", "derived")


@dataclass(frozen=True)
class ImportDeclaration:
    target: str
    binding: str | None
    lands: str | None
    context_lines: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ImportManifest:
    path: Path
    consumer: Path | None
    declarations: tuple[ImportDeclaration, ...] = ()
    problem: str | None = None


@dataclass(frozen=True)
class ImportCheckResult:
    manifest: str
    consumer: str | None
    target: str
    binding: str | None
    status: str
    detail: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class ImportCheckReport:
    results: tuple[ImportCheckResult, ...] = ()
    manifest_problems: tuple[tuple[str, str], ...] = ()

    @property
    def finding_count(self) -> int:
        ok = {"resolved", "equal", "skipped-agentic"}
        return len(self.manifest_problems) + sum(
            1 for result in self.results if result.status not in ok
        )


def discover_import_manifests(package_root: Path) -> list[ImportManifest]:
    build_dir = Path(package_root) / "build"
    if not build_dir.is_dir():
        return []
    flattened = _flattened_module_names(Path(package_root))
    manifests: list[ImportManifest] = []
    for path in sorted(build_dir.glob(f"*{_MANIFEST_SUFFIX}")):
        key = path.name[: -len(_MANIFEST_SUFFIX)]
        candidates = flattened.get(key, [])
        if len(candidates) == 1:
            consumer, problem = candidates[0], None
        elif not candidates:
            consumer, problem = None, f"manifest name matches no module file: {path.name}"
        else:
            listed = ", ".join(str(candidate) for candidate in candidates)
            consumer, problem = None, f"manifest name is ambiguous ({listed})"
        manifests.append(
            ImportManifest(
                path=path,
                consumer=consumer,
                declarations=tuple(_parse_declarations(path)),
                problem=problem,
            )
        )
    return manifests


def check_package_imports(
    package_root: Path,
    *,
    depot_paths: list[Path] | tuple[Path, ...] = (),
) -> ImportCheckReport:
    package_root = Path(package_root)
    depot_models = [parse_depot(depot) for depot in depot_paths]
    results: list[ImportCheckResult] = []
    problems: list[tuple[str, str]] = []
    for manifest in discover_import_manifests(package_root):
        rel_manifest = str(manifest.path.relative_to(package_root))
        if manifest.problem is not None:
            problems.append((rel_manifest, manifest.problem))
        consumer_text = None
        if manifest.consumer is not None:
            consumer_text = (package_root / manifest.consumer).read_text(encoding="utf-8")
        for declaration in manifest.declarations:
            results.append(
                _check_declaration(
                    declaration,
                    manifest=rel_manifest,
                    consumer=manifest.consumer,
                    consumer_text=consumer_text,
                    depot_models=depot_models,
                    had_depots=bool(depot_paths),
                )
            )
    return ImportCheckReport(results=tuple(results), manifest_problems=tuple(problems))


def _check_declaration(
    declaration: ImportDeclaration,
    *,
    manifest: str,
    consumer: Path | None,
    consumer_text: str | None,
    depot_models: list,
    had_depots: bool,
) -> ImportCheckResult:
    def result(status: str, detail: str | None = None) -> ImportCheckResult:
        return ImportCheckResult(
            manifest=manifest,
            consumer=str(consumer) if consumer is not None else None,
            target=declaration.target,
            binding=declaration.binding,
            status=status,
            detail=detail,
            line=declaration.line,
        )

    if declaration.binding not in _BINDINGS:
        return result("invalid", f"unknown binding: {declaration.binding!r}")
    if declaration.binding == "derived":
        return result("skipped-agentic", "derived bindings are checked by the builder's agentic pass")

    target_content, detail = _resolve_target(
        declaration.target, depot_models=depot_models, had_depots=had_depots
    )
    if target_content is None:
        return result("unresolvable", detail)
    if declaration.binding == "pointer":
        return result("resolved")

    # copy: compare target content against the landing region in the consumer
    if consumer is None or consumer_text is None:
        return result("unresolvable", "consumer module could not be resolved")
    if declaration.lands is None:
        region = _normalized(consumer_text.splitlines())
    else:
        section = _region_lines(consumer_text, declaration.lands.lstrip("#").strip())
        if section is None:
            return result("unresolvable", f"landing region not found: {declaration.lands}")
        region = _normalized(section)
    if region == _normalized(target_content):
        return result("equal")
    return result("drifted", "landing region differs from the target content")


def _resolve_target(
    target: str,
    *,
    depot_models: list,
    had_depots: bool,
) -> tuple[list[str] | None, str | None]:
    if target.startswith("@"):
        raw = target[1:]
        region = None
        if "#" in raw:
            raw, region = raw.split("#", 1)
        path = Path(raw)
        if not path.is_file():
            return None, f"target file not found: {raw}"
        text = path.read_text(encoding="utf-8")
        if region is None:
            return text.splitlines(), None
        section = _region_lines(text, region.strip())
        if section is None:
            return None, f"target region not found: #{region}"
        return section, None
    # ontology name: resolve as a block heading in the supplied depots
    if not had_depots:
        return None, "ontology target needs an index depot (--depot) to resolve"
    for model in depot_models:
        for document in model.documents:
            block_lines: list[str] | None = None
            for node in document.nodes:
                if isinstance(node, BlockHeading) and str(node.parsed.get("path", "")).strip() == target:
                    block_lines = []
                elif block_lines is not None:
                    if isinstance(node, BlockHeading):
                        break
                    if isinstance(node, KernelLine):
                        block_lines.append(node.src)
            if block_lines is not None:
                return block_lines, None
    return None, "target block not found in the supplied depots"


def _parse_declarations(path: Path) -> list[ImportDeclaration]:
    document = parse_index_file(path, surface_kind="unknown")
    declarations: list[ImportDeclaration] = []
    current: dict | None = None

    def flush() -> None:
        if current is not None:
            declarations.append(
                ImportDeclaration(
                    target=current["target"],
                    binding=current.get("binding"),
                    lands=current.get("lands"),
                    context_lines=tuple(current.get("context", [])),
                    line=current["line"],
                )
            )

    for node in document.nodes:
        if isinstance(node, BlockHeading):
            flush()
            current = {"target": str(node.parsed.get("path", "")).strip(), "line": node.start_line, "context": []}
            continue
        if current is None or not isinstance(node, KernelLine):
            continue
        body = node.src.lstrip("- ").strip()
        if body.startswith("binding:"):
            current["binding"] = body.split(":", 1)[1].strip()
        elif body.startswith("lands:"):
            current["lands"] = body.split(":", 1)[1].strip()
        elif body.startswith("context:"):
            current["context"].append(body.split(":", 1)[1].strip())
        else:
            current["context"].append(body)
    flush()
    return declarations


def _flattened_module_names(package_root: Path) -> dict[str, list[Path]]:
    flattened: dict[str, list[Path]] = {}
    for path in sorted(package_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(package_root)
        if rel.parts and rel.parts[0] == "build":
            continue
        key = "-".join([*rel.parts[:-1], rel.stem])
        flattened.setdefault(key, []).append(rel)
    return flattened


def _region_lines(text: str, region: str) -> list[str] | None:
    lines = text.splitlines()
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        if not line.startswith("#"):
            continue
        heading_level = len(line) - len(line.lstrip("#"))
        title = line.lstrip("#").strip()
        if start is None:
            if title == region:
                start = index + 1
                level = heading_level
        elif heading_level <= level:
            return lines[start:index]
    if start is None:
        return None
    return lines[start:]


def _normalized(lines: list[str]) -> list[str]:
    cleaned = [line.rstrip() for line in lines if line.strip() != "****"]
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned


__all__ = [
    "ImportCheckReport",
    "ImportCheckResult",
    "ImportDeclaration",
    "ImportManifest",
    "check_package_imports",
    "discover_import_manifests",
]
