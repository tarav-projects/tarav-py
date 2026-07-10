"""Skillware expansion: locator resolution, src compilation, and refresh.

Deterministic by construction — `derived` bodies are spliced as materialized
in src, never regenerated here; `copy` bodies are resolved fresh. Compiling
strips every `[!skw]` callout so zero machinery lands on the runnable surface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from agentos.index.model import BlockHeading, KernelLine, parse_depot
from agentos.skillware.model import SkwFinding, SkwSource, parse_skw_source

SRC_SUFFIX = ".skw.md"
SETTINGS_NAME = "skillware.json"


class SkillwareError(Exception):
    pass


@dataclass
class Skillware:
    skill_root: Path
    src_root: Path
    depots: tuple[Path, ...]
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


def load_skillware(skill_root: Path) -> Skillware:
    skill_root = Path(skill_root)
    src_root = skill_root / ".skillware" / "src"
    if not src_root.is_dir():
        raise SkillwareError(f"not a skillware skill (no .skillware/src): {skill_root}")
    depots: list[Path] = []
    settings_path = skill_root / ".skillware" / SETTINGS_NAME
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        for raw_depot in settings.get("depots", []):
            depot = (skill_root / raw_depot).resolve()
            if not depot.is_dir():
                raise SkillwareError(f"configured depot is not a directory: {raw_depot}")
            depots.append(depot)
    return Skillware(skill_root=skill_root, src_root=src_root, depots=tuple(depots))


def content_hash(lines: list[str] | tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def expand_file(skillware: Skillware, src_rel: Path) -> Expansion:
    src_rel = Path(src_rel)
    text = (skillware.src_root / src_rel).read_text(encoding="utf-8")
    source = parse_skw_source(text)
    findings: list[SkwFinding] = list(source.findings)
    dep_hashes: dict[str, dict[str, str | None]] = {}

    resolved_copies: dict[tuple[int, int], list[str]] = {}
    for recipe in source.recipes:
        recipe_deps: dict[str, str | None] = {}
        for locator in recipe.froms:
            lines, detail = _resolve_locator(skillware, locator, stack=(src_rel,))
            if lines is None:
                findings.append(SkwFinding(recipe.line, f"unresolvable from: {locator} ({detail})"))
                recipe_deps[locator] = None
                continue
            recipe_deps[locator] = content_hash(lines)
            if recipe.verb == "copy" and locator == recipe.froms[0]:
                resolved_copies[recipe.body_span] = lines
        dep_hashes[recipe.heading or f"line {recipe.line}"] = recipe_deps

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


def _expand_lines(skillware: Skillware, src_rel: Path, stack: tuple[Path, ...]) -> tuple[list[str], list[SkwFinding]]:
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
        lines, detail = _resolve_locator(skillware, recipe.froms[0], stack=(*stack, src_rel)) if recipe.froms else (None, "no from")
        if lines is None:
            findings.append(SkwFinding(recipe.line, f"{src_rel}: unresolvable from: {recipe.froms[0] if recipe.froms else '?'} ({detail})"))
            continue
        resolved_copies[recipe.body_span] = lines
    return _emit(source, resolved_copies, keep_machinery=False), findings


def _resolve_locator(
    skillware: Skillware, locator: str, *, stack: tuple[Path, ...]
) -> tuple[list[str] | None, str | None]:
    if "#" in locator:
        path_part, region = locator.split("#", 1)
        region = region.strip()
    else:
        path_part, region = locator, None
    path_part = path_part.strip()

    if "/" in path_part or path_part.endswith(".md"):
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

    # bare Dotted.Name: an index block body resolved in the configured depots
    if not skillware.depots:
        return None, "Dotted.Name target needs a depot in skillware.json"
    for depot in skillware.depots:
        model = skillware._depot_cache.get(depot)
        if model is None:
            model = parse_depot(depot)
            skillware._depot_cache[depot] = model
        block = _depot_block_body(model, locator)
        if block is not None:
            return block, None
    return None, "block not found in the configured depots"


def _depot_block_body(model, name: str) -> list[str] | None:
    for document in model.documents:
        block_lines: list[str] | None = None
        for node in document.nodes:
            if isinstance(node, BlockHeading) and str(node.parsed.get("path", "")).strip() == name:
                block_lines = []
            elif block_lines is not None:
                if isinstance(node, BlockHeading):
                    break
                if isinstance(node, KernelLine):
                    block_lines.append(node.src)
        if block_lines is not None:
            return block_lines
    return None


def _region_body(lines: list[str], region: str) -> list[str] | None:
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
        for recipe in source.recipes:
            skip_ranges.append(recipe.callout_span)
        skip_ranges.extend(source.end_spans)
    for span, lines in resolved_copies.items():
        replacements[span[0]] = ["", *lines, ""]
        skip_ranges.append((span[0], span[1]))
        # re-add the replacement at the span start
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


__all__ = [
    "SETTINGS_NAME",
    "SRC_SUFFIX",
    "Expansion",
    "Skillware",
    "SkillwareError",
    "content_hash",
    "expand_file",
    "load_skillware",
]


# --- build + lock + check -----------------------------------------------------

LOCK_NAME = "lock.json"


@dataclass(frozen=True)
class BuildEntry:
    target: Path
    action: str  # built | unchanged
    src_refreshed: bool


@dataclass(frozen=True)
class BuildReport:
    entries: tuple[BuildEntry, ...]
    findings: tuple[SkwFinding, ...]


@dataclass(frozen=True)
class CheckEntry:
    target: Path
    status: str  # never-built | stale-build | hand-edited | ok
    copy_drift: tuple[str, ...]
    derived_stale: tuple[str, ...]


@dataclass(frozen=True)
class CheckReport:
    entries: tuple[CheckEntry, ...]
    findings: tuple[SkwFinding, ...]

    @property
    def finding_count(self) -> int:
        return len(self.findings) + sum(
            1
            for entry in self.entries
            if entry.status != "ok" or entry.copy_drift or entry.derived_stale
        )


AGENTS_NAME = "AGENTS.md"

AGENTS_MD_TEXT = """\
# .skillware — Skillware Build Surface

- this folder is the Skillware build surface of the skill above it
- the skill's Skillware-managed files are compiled from `src/**/*.skw.md` — NEVER edit those targets by hand
- to change managed content: edit the src file, then run `agentos skillware build --skill <skill-root>`
- to inspect drift (read-only): `agentos skillware check --skill <skill-root>`
- `lock.json` and this `AGENTS.md` are engine-owned and overwritten on every build
- for the full Skillware discipline, load the `agentos-skillware` skill
"""


def _lock_path(skillware: Skillware) -> Path:
    return skillware.skill_root / ".skillware" / LOCK_NAME


def _read_lock(skillware: Skillware) -> dict:
    path = _lock_path(skillware)
    if not path.is_file():
        return {"schema_version": 1, "files": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _recipe_states(skillware: Skillware, src_rel: Path, expansion: Expansion) -> list[dict]:
    source = parse_skw_source((skillware.src_root / src_rel).read_text(encoding="utf-8"))
    states = []
    for recipe in source.recipes:
        heading = recipe.heading or f"line {recipe.line}"
        states.append(
            {
                "heading": heading,
                "verb": recipe.verb,
                "body_sha256": content_hash(_trim(list(recipe.body))),
                "deps": expansion.dep_hashes.get(heading, {}),
            }
        )
    return states


def build_skill(skill_root: Path) -> BuildReport:
    skillware = load_skillware(skill_root)
    old_lock = _read_lock(skillware)
    lock: dict = {"schema_version": 1, "files": {}}
    entries: list[BuildEntry] = []
    findings: list[SkwFinding] = []

    for src_rel in skillware.src_files():
        expansion = expand_file(skillware, src_rel)
        findings.extend(
            SkwFinding(f.line, f"{src_rel}: {f.message}") for f in expansion.findings
        )

        src_path = skillware.src_root / src_rel
        refreshed_text = "\n".join(expansion.src_refresh_lines) + "\n"
        src_refreshed = refreshed_text != src_path.read_text(encoding="utf-8")
        if src_refreshed:
            src_path.write_text(refreshed_text, encoding="utf-8")
            expansion = expand_file(skillware, src_rel)

        target_path = skillware.skill_root / expansion.target_rel
        output_text = "\n".join(expansion.fresh_lines) + "\n"
        existing = (
            target_path.read_text(encoding="utf-8") if target_path.is_file() else None
        )
        action = "unchanged" if existing == output_text else "built"
        if action == "built":
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(output_text, encoding="utf-8")

        # derived dep hashes persist until the derived body itself changes:
        # build never blesses a stale derived body — only a re-derive does.
        recipes = _recipe_states(skillware, src_rel, expansion)
        old_recipes = {
            (r["heading"], r["verb"]): r
            for r in old_lock.get("files", {}).get(str(expansion.target_rel), {}).get("recipes", [])
        }
        for state in recipes:
            if state["verb"] != "derived":
                continue
            old = old_recipes.get((state["heading"], "derived"))
            if old is not None and old.get("body_sha256") == state["body_sha256"]:
                state["deps"] = old.get("deps", state["deps"])

        lock["files"][str(expansion.target_rel)] = {
            "output_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
            "recipes": recipes,
        }
        entries.append(
            BuildEntry(target=expansion.target_rel, action=action, src_refreshed=src_refreshed)
        )

    _lock_path(skillware).write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    (skillware.skill_root / ".skillware" / AGENTS_NAME).write_text(
        AGENTS_MD_TEXT, encoding="utf-8"
    )
    return BuildReport(entries=tuple(entries), findings=tuple(findings))


def check_skill(skill_root: Path) -> CheckReport:
    skillware = load_skillware(skill_root)
    lock = _read_lock(skillware)
    entries: list[CheckEntry] = []
    findings: list[SkwFinding] = []

    for src_rel in skillware.src_files():
        expansion = expand_file(skillware, src_rel)
        findings.extend(
            SkwFinding(f.line, f"{src_rel}: {f.message}") for f in expansion.findings
        )
        target_rel = expansion.target_rel
        target_path = skillware.skill_root / target_rel
        expected_text = "\n".join(expansion.fresh_lines) + "\n"
        lock_entry = lock.get("files", {}).get(str(target_rel))

        copy_drift: list[str] = []
        src_text = (skillware.src_root / src_rel).read_text(encoding="utf-8")
        if "\n".join(expansion.src_refresh_lines) + "\n" != src_text:
            source = parse_skw_source(src_text)
            copy_drift = [
                recipe.heading or f"line {recipe.line}"
                for recipe in source.recipes
                if recipe.verb == "copy"
                and expansion.dep_hashes.get(recipe.heading or f"line {recipe.line}", {}).get(
                    recipe.froms[0] if recipe.froms else ""
                )
                != content_hash(_trim(list(recipe.body)))
            ]

        derived_stale: list[str] = []
        if lock_entry is not None:
            source = parse_skw_source(src_text)
            locked = {
                (r["heading"], r["verb"]): r for r in lock_entry.get("recipes", [])
            }
            for recipe in source.recipes:
                if recipe.verb != "derived":
                    continue
                heading = recipe.heading or f"line {recipe.line}"
                old = locked.get((heading, "derived"))
                if old is None:
                    continue
                if old.get("body_sha256") != content_hash(_trim(list(recipe.body))):
                    continue  # body re-derived but not rebuilt: stale-build covers it
                current = expansion.dep_hashes.get(heading, {})
                if any(
                    current.get(locator) != sha for locator, sha in old.get("deps", {}).items()
                ):
                    derived_stale.append(heading)

        if not target_path.is_file() or lock_entry is None:
            status = "never-built"
        elif target_path.read_text(encoding="utf-8") == expected_text:
            status = "ok"
        else:
            on_disk_sha = hashlib.sha256(
                target_path.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            status = (
                "stale-build"
                if on_disk_sha == lock_entry.get("output_sha256")
                else "hand-edited"
            )

        entry = CheckEntry(
            target=target_rel,
            status=status,
            copy_drift=tuple(copy_drift),
            derived_stale=tuple(derived_stale),
        )
        entries.append(entry)
        if entry.status != "ok":
            findings.append(SkwFinding(0, f"{target_rel}: {entry.status}"))
        for heading in entry.copy_drift:
            findings.append(SkwFinding(0, f"{target_rel}: copy-drift at '{heading}' (build repairs)"))
        for heading in entry.derived_stale:
            findings.append(
                SkwFinding(0, f"{target_rel}: derived-stale at '{heading}' (agentic re-derive in src)")
            )

    return CheckReport(entries=tuple(entries), findings=tuple(findings))


__all__ += [
    "BuildEntry",
    "BuildReport",
    "CheckEntry",
    "CheckReport",
    "build_skill",
    "check_skill",
]
