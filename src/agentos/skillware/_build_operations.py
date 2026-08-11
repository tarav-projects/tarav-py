# $kw: ^skillware-poi-operations --from POI.System --from POI.Linter --note [CT] Skillware operations preserve legacy hashes blessing and parser diagnostics through common POI instances ^c20260729-49u
"""Skillware build, check, project-check, and blessing operations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from agentos.poi import POIDiagnostic
from agentos.skw.network import extract_mentions, run_dependency_sync
from agentos.skillware.model import (
    SkwFinding,
    SkwSource,
    parse_skw_source,
    recipe_key,
)

from ._build_core import (
    BUILD_DIR,
    LEGACY_BUILD_DIR,
    Expansion,
    Skillware,
    SkillwareError,
    _is_dotted_name_locator,
    _resolved_dotted_names,
    _role_edges,
    _trim,
    content_hash,
    expand_file,
    load_project_skw_config,
    load_skillware,
    resolve_project_depots,
    unlock_requirements,
)
from ._code_model import CodeCheckReport
from ._code_index import index_code_dependency_resolver
from ._code_surfaces import check_code_surfaces
from .poi import (
    SkillwarePOIInstance,
    network_finding_to_poi,
    parser_diagnostics,
    skillware_poi as _poi,
    suppress_blessed as _suppress_blessed,
)


LOCK_NAME = "lock.json"


@dataclass(frozen=True)
class BuildEntry:
    target: Path
    action: str
    src_refreshed: bool


@dataclass(frozen=True)
class BuildReport:
    entries: tuple[BuildEntry, ...]
    findings: tuple[SkwFinding, ...]


@dataclass(frozen=True)
class CheckEntry:
    target: Path
    status: (
        str
    )
    copy_drift: tuple[str, ...]
    derived_stale: tuple[str, ...]


@dataclass(frozen=True)
class BlessRecord:
    target: Path
    key: str
    deps: dict[str, dict[str, str | None]]


@dataclass(frozen=True)
class CheckReport:
    entries: tuple[CheckEntry, ...]
    pois: tuple[SkillwarePOIInstance, ...]
    diagnostics: tuple[POIDiagnostic, ...] = ()


BLESSABLE_KINDS = ("derived-stale",)
SUPPRESSIBLE_KINDS = (
    "undeclared-dependency",
    "unhonored-dependency",
    "dangling-dependency",
    "uncited-dependency",
    "context-assembly-bypass",
    "non-skw-annotation",
)

_LEGACY_CALLOUT_RE = re.compile(r"^>\s*\[!skw\]")


def _write_lock(skillware: Skillware, lock: dict) -> None:
    _lock_path(skillware).write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )


def _append_poi_blessing(
    skillware: Skillware,
    poi: SkillwarePOIInstance,
) -> None:
    lock = _read_lock(skillware)
    blessings = lock.setdefault("blessings", [])
    if not any(record.get("hash") == poi.poi_hash for record in blessings):
        blessings.append(
            {
                "hash": poi.poi_hash,
                "kind": poi.kind,
                "target": str(poi.target),
                "key": poi.key,
            }
        )
    _write_lock(skillware, lock)


AGENTS_NAME = "AGENTS.md"

AGENTS_MD_TEXT = """\
# .skw — skw Build Surface

- this folder is the skw build surface of the package above it
- the package's skw-managed files are compiled from `src/**/*.skw.md` — NEVER edit those targets by hand
- to change managed content: edit the src file, then run `agentos skw build --skill <package-root>`
- to inspect drift (read-only): `agentos skw check --skill <package-root>`
- `lock.json` and this `AGENTS.md` are engine-owned and overwritten on every build
- for the full skw discipline, load the `agentos-skillware` skill
"""


def _lock_path(skillware: Skillware) -> Path:
    return skillware.build_root / LOCK_NAME


def _read_lock(skillware: Skillware) -> dict:
    path = _lock_path(skillware)
    if not path.is_file():
        return {"schema_version": 1, "files": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _recipe_states(
    skillware: Skillware, src_rel: Path, expansion: Expansion
) -> list[dict]:
    source = parse_skw_source(
        (skillware.src_root / src_rel).read_text(encoding="utf-8")
    )
    states = []
    for recipe in source.recipes:
        key = recipe_key(recipe)
        states.append(
            {
                "heading": key,
                "verb": recipe.verb,
                "body_sha256": content_hash(_trim(list(recipe.body))),
                "deps": expansion.dep_hashes.get(key, {}),
            }
        )
    return states


def _match_locked_derived(
    entries: list[dict], key: str, body_sha256: str
) -> dict | None:
    """Locked state for a derived recipe: by key, else by unchanged body.

    The body-hash fallback keeps lock continuity when positional keys shift
    (a recipe inserted or reordered under the same heading) — a stale
    derivation must never be re-blessed by a key miss.
    """
    for entry in entries:
        if entry.get("verb") != "derived":
            continue
        if entry.get("heading") == key and entry.get("body_sha256") == body_sha256:
            return entry
    matches = [
        entry
        for entry in entries
        if entry.get("verb") == "derived" and entry.get("body_sha256") == body_sha256
    ]
    return matches[0] if len(matches) == 1 else None


def build_skill(skill_root: Path) -> BuildReport:
    skillware = load_skillware(skill_root)
    old_lock = _read_lock(skillware)
    lock: dict = {
        "schema_version": 1,
        "files": {},
        "blessings": list(old_lock.get("blessings", [])),
    }
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



        recipes = _recipe_states(skillware, src_rel, expansion)
        old_entries = (
            old_lock.get("files", {})
            .get(str(expansion.target_rel), {})
            .get("recipes", [])
        )
        for state in recipes:
            if state["verb"] != "derived":
                continue
            old = _match_locked_derived(
                old_entries, state["heading"], state["body_sha256"]
            )
            if old is not None:
                state["deps"] = old.get("deps", state["deps"])

        lock["files"][str(expansion.target_rel)] = {
            "output_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
            "recipes": recipes,
        }
        entries.append(
            BuildEntry(
                target=expansion.target_rel, action=action, src_refreshed=src_refreshed
            )
        )

    _lock_path(skillware).write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )
    (skillware.build_root / AGENTS_NAME).write_text(AGENTS_MD_TEXT, encoding="utf-8")
    return BuildReport(entries=tuple(entries), findings=tuple(findings))


def _legacy_callout_pois(
    target_rel: Path,
    src_text: str,
) -> list[SkillwarePOIInstance]:
    pois: list[SkillwarePOIInstance] = []
    in_fence = False
    for number, line in enumerate(src_text.splitlines(), start=1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence and _LEGACY_CALLOUT_RE.match(line):
            pois.append(
                _poi(
                    "legacy-callout",
                    target_rel,
                    None,
                    f"{number}|{line.strip()}",
                    f"line {number}: {line.strip()}",
                )
            )
    return pois


class _SkwSurfaceProvider:
    """The skw-skills backend's binding into the dependency-sync engine.

    Extracts declared edges from a `SkwSource`'s dependencies and recipes, its
    mentions from the compiled (`Expansion`) text, and resolves names against
    the package's configured depots — the `SurfaceProvider` the core drives.
    """

    def __init__(
        self, skillware: "Skillware", source: SkwSource, expansion: "Expansion"
    ) -> None:
        self._skillware = skillware
        self._source = source
        self._expansion = expansion

    def declared_edges(self) -> tuple[set[str], set[str]]:
        declared: set[str] = set()
        declared_from_depends: set[str] = set()
        for dependency in self._source.dependencies:
            for locator in dependency.froms:
                if _is_dotted_name_locator(locator):
                    declared.add(locator)
                    declared_from_depends.add(locator)
            for locator in (*dependency.dev_froms, *dependency.cites):
                if _is_dotted_name_locator(locator):
                    declared.add(locator)
        for recipe in self._source.recipes:
            for _role, locator in _role_edges(recipe):
                if _is_dotted_name_locator(locator):
                    declared.add(locator)
        for construct in self._source.constructs:
            for _role, locator in _role_edges(construct):
                if _is_dotted_name_locator(locator):
                    declared.add(locator)
        return declared, declared_from_depends

    def mentions(self) -> set[str]:
        return extract_mentions("\n".join(self._expansion.fresh_lines))

    def resolve(self, names: set[str]) -> dict[str, str]:
        return _resolved_dotted_names(self._skillware, names)


def _dependency_sync_pois(
    skillware: Skillware, target_rel: Path, source: SkwSource, expansion: Expansion
) -> list[SkillwarePOIInstance]:
    provider = _SkwSurfaceProvider(skillware, source, expansion)
    return [
        network_finding_to_poi(finding)
        for finding in run_dependency_sync(target_rel, provider)
    ]


def _citation_pois(
    target_rel: Path, source: SkwSource, expansion: Expansion
) -> list[SkillwarePOIInstance]:
    text = "\n".join(expansion.fresh_lines)
    mentions = extract_mentions(text)
    pois: list[SkillwarePOIInstance] = []
    blocks = (*source.dependencies, *source.recipes, *source.constructs)
    for block in blocks:
        for locator in block.cites:
            visible = (
                locator in mentions
                if _is_dotted_name_locator(locator)
                else locator in text
            )
            if not visible:
                pois.append(
                    _poi(
                        "uncited-dependency",
                        target_rel,
                        locator,
                        f"{block.line}|{locator}",
                        f"`--cite {locator}` is not explicit in the compiled surface",
                    )
                )
    return pois


def _context_assembly_coverage(
    skillware: Skillware,
) -> dict[str, set[Path]]:
    coverage: dict[str, set[Path]] = {}
    for src_rel in skillware.src_files():
        source = parse_skw_source(
            (skillware.src_root / src_rel).read_text(encoding="utf-8")
        )
        if source.findings:
            continue
        for dependency in source.dependencies:
            if not dependency.context_assembly:
                continue
            for locator in dependency.froms:
                coverage.setdefault(locator, set()).add(src_rel)
    return coverage


def _context_assembly_bypass_pois(
    target_rel: Path,
    src_rel: Path,
    source: SkwSource,
    coverage: dict[str, set[Path]],
) -> list[SkillwarePOIInstance]:
    blocks = (*source.dependencies, *source.recipes, *source.constructs)
    dev_froms = {locator for block in blocks for locator in block.dev_froms}
    dependencies = {
        locator for block in blocks for _role, locator in _role_edges(block)
    }
    pois: list[SkillwarePOIInstance] = []
    for locator in sorted(dependencies):
        for assembly in sorted(coverage.get(locator, set())):
            if assembly == src_rel or assembly.as_posix() in dev_froms:
                continue
            pois.append(
                _poi(
                    "context-assembly-bypass",
                    target_rel,
                    locator,
                    f"{assembly.as_posix()}|{locator}",
                    f"dependency `{locator}` is covered by `{assembly.as_posix()}` "
                    f"but the surface has no `--dev-from {assembly.as_posix()}`",
                )
            )
    return pois


def _note_pois(
    target_rel: Path,
    source: SkwSource,
) -> list[SkillwarePOIInstance]:
    """`--note`/`--supp` are typed, anchored `Index.Line`s: a `--note` missing
    its `[TYPE]` act code, or either flag missing its `^anchor`, is malformed."""
    pois: list[SkillwarePOIInstance] = []
    for note in source.notes:
        problems: list[str] = []
        if note.flag == "note" and note.type is None:
            problems.append("missing [TYPE] act code")
        if note.anchor is None:
            problems.append("missing ^anchor")
        if problems:
            pois.append(
                _poi(
                    "malformed-note",
                    target_rel,
                    note.address or f"line {note.line}",
                    f"{note.line}|{note.text}",
                    f"line {note.line}: --{note.flag} {'; '.join(problems)}",
                )
            )
    return pois


def _address_mismatch_pois(
    target_rel: Path,
    source: SkwSource,
) -> list[SkillwarePOIInstance]:
    """A block that fences a named host element checks its declared `#address`
    against that element's name — a mismatch is a POI (the fence checks the
    name, it does not source it)."""
    pois: list[SkillwarePOIInstance] = []
    blocks: list = [*source.recipes, *source.constructs]
    for block in blocks:
        address = getattr(block, "address", None)
        if not address or not address.startswith("#"):
            continue
        want = address[1:]
        head = next(
            (line for line in block.body if line.lstrip().startswith("#")), None
        )
        if head is None:
            continue
        name = head.lstrip("#").strip()
        if name != want:
            pois.append(
                _poi(
                    "address-mismatch",
                    target_rel,
                    address,
                    name,
                    f"fenced element `{name}` does not match declared address `{address}`",
                )
            )
    return pois


def check_skill(skill_root: Path, extra_depots: tuple[Path, ...] = ()) -> CheckReport:
    """The `Poi.Linter` pass: lint parse results, emit advisory POIs.

    Parse errors gate a file — below the `Parse.Floor` its semantic checks
    do not run; sibling files still check normally. Every POI carries a
    stable identity hash bound to the current situation.
    """
    skillware = load_skillware(skill_root, extra_depots=extra_depots)
    lock = _read_lock(skillware)
    entries: list[CheckEntry] = []
    pois: list[SkillwarePOIInstance] = []
    context_assembly_coverage = _context_assembly_coverage(skillware)

    for src_rel in skillware.src_files():
        target_rel = skillware.target_rel(src_rel)
        src_text = (skillware.src_root / src_rel).read_text(encoding="utf-8")
        pois.extend(_legacy_callout_pois(target_rel, src_text))

        source = parse_skw_source(src_text)
        if source.findings:
            pois.extend(
                _poi(
                    "parse-error",
                    target_rel,
                    None,
                    f"{f.line}|{f.message}",
                    f"line {f.line}: {f.message}",
                )
                for f in source.findings
            )
            entries.append(CheckEntry(target_rel, "parse-error", (), ()))
            continue

        expansion = expand_file(skillware, src_rel)
        if expansion.findings:
            pois.extend(
                _poi(
                    "unresolvable",
                    target_rel,
                    None,
                    f"{f.line}|{f.message}",
                    f"line {f.line}: {f.message}",
                )
                for f in expansion.findings
            )
            entries.append(CheckEntry(target_rel, "unresolvable", (), ()))
            continue

        target_path = skillware.skill_root / target_rel
        expected_text = "\n".join(expansion.fresh_lines) + "\n"
        lock_entry = lock.get("files", {}).get(str(target_rel))

        copy_drift: list[str] = []
        if "\n".join(expansion.src_refresh_lines) + "\n" != src_text:
            copy_drift = [
                recipe_key(recipe)
                for recipe in source.recipes
                if recipe.verb == "copy"
                and expansion.dep_hashes.get(recipe_key(recipe), {}).get(
                    recipe.froms[0] if recipe.froms else ""
                )
                != content_hash(_trim(list(recipe.body)))
            ]

        derived_stale: list[str] = []
        if lock_entry is not None:
            locked_entries = lock_entry.get("recipes", [])
            for recipe in source.recipes:
                if recipe.verb != "derived":
                    continue
                key = recipe_key(recipe)
                body_sha = content_hash(_trim(list(recipe.body)))
                old = _match_locked_derived(locked_entries, key, body_sha)
                if old is None:
                    continue
                current = expansion.dep_hashes.get(key, {})
                if any(
                    current.get(locator) != sha
                    for locator, sha in old.get("deps", {}).items()
                ):
                    derived_stale.append(key)

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
        pois.extend(_dependency_sync_pois(skillware, target_rel, source, expansion))
        pois.extend(_citation_pois(target_rel, source, expansion))
        pois.extend(
            _context_assembly_bypass_pois(
                target_rel,
                src_rel,
                source,
                context_assembly_coverage,
            )
        )
        pois.extend(_note_pois(target_rel, source))
        pois.extend(_address_mismatch_pois(target_rel, source))
        if entry.status != "ok":
            pois.append(
                _poi(entry.status, target_rel, None, entry.status, entry.status)
            )
        for key in entry.copy_drift:
            pois.append(
                _poi(
                    "copy-drift",
                    target_rel,
                    key,
                    json.dumps(expansion.dep_hashes.get(key, {}), sort_keys=True),
                    "copy body no longer equals its target's expansion",
                )
            )
        for key in entry.derived_stale:


            pois.append(
                _poi(
                    "derived-stale",
                    target_rel,
                    key,
                    json.dumps(expansion.dep_hashes.get(key, {}), sort_keys=True),
                    "a dependency changed since the derived body was written",
                )
            )

    visible_pois = tuple(_suppress_blessed(lock, pois))
    return CheckReport(
        entries=tuple(entries),
        pois=visible_pois,
        diagnostics=parser_diagnostics(visible_pois),
    )


@dataclass(frozen=True)
class ProjectCheckReport:
    project_root: Path
    packages: tuple[tuple[Path, CheckReport], ...]
    code: CodeCheckReport

    @property
    def poi_count(self) -> int:
        return len(self.code.pois) + sum(
            len(report.pois) for _, report in self.packages
        )


def discover_packages(project_root: Path) -> list[Path]:
    """Every skw package under the project: a directory holding a `.skw/src`
    (or legacy `.skillware/src`). Honors the project config's `surfaces`
    (explicit set) and `exclude` (trim). A config-only project root — a
    `.skw/` with no `src/` — is not itself a package."""
    project_root = Path(project_root).resolve()
    config = load_project_skw_config(project_root)
    excluded = {(project_root / raw).resolve() for raw in config.exclude}

    roots: dict[Path, None] = {}
    if config.surfaces:
        candidates = [(project_root / raw).resolve() for raw in config.surfaces]
    else:
        candidates = []
        for build_name in (BUILD_DIR, LEGACY_BUILD_DIR):
            for build_dir in project_root.rglob(build_name):
                if not (build_dir / "src").is_dir():
                    continue
                if {".git", "node_modules"} & set(build_dir.parts):
                    continue
                candidates.append(build_dir.parent.resolve())
    for pkg in candidates:
        if pkg in excluded:
            continue
        roots[pkg] = None
    return sorted(roots)


def check_project(project_root: Path) -> ProjectCheckReport:
    """Project-scope `Poi.Linter`: check every discovered package with the
    project-scope depots cascaded in, so cross-package name bindings resolve."""
    project_root = Path(project_root).resolve()
    config = load_project_skw_config(project_root)
    extra = tuple(resolve_project_depots(project_root))
    packages = tuple(
        (pkg, check_skill(pkg, extra_depots=extra))
        for pkg in discover_packages(project_root)
    )
    return ProjectCheckReport(
        project_root=project_root,
        packages=packages,
        code=check_code_surfaces(
            project_root,
            config.code_surfaces,
            dependency_resolver=index_code_dependency_resolver(extra),
        ),
    )


def _require_unlock_receipts(
    skill_root: Path,
    poi_kind: str,
    unlocks: tuple[str, ...],
    *,
    poi_hash: str | None = None,
) -> None:
    provided = set(unlocks)
    missing = [
        requirement
        for requirement in unlock_requirements(skill_root, poi_kind)
        if requirement.token not in provided
    ]
    if not missing:
        return
    subject = f"POI {poi_hash} ({poi_kind})" if poi_hash else f"POI kind {poi_kind}"
    surfaces = "\n".join(
        f"- {requirement.surface} (registry: {requirement.registry})"
        for requirement in missing
    )
    raise SkillwareError(
        f"{subject} requires unlock token(s) from these context surfaces:\n"
        f"{surfaces}\n"
        "read every surface and provide each receipt with --unlock <token>"
    )


def bless_skill(
    skill_root: Path,
    poi_hash: str,
    *,
    unlocks: tuple[str, ...] = (),
) -> BlessRecord:
    """`Poi.Bless`: accept a current POI's situation as correct.

    `derived-stale` updates the locked dependency hashes. Suppressible linter
    POIs record the current POI hash in the lock until the situation changes.
    """
    skillware = load_skillware(skill_root)
    report = check_skill(skill_root)
    match = next((p for p in report.pois if p.poi_hash == poi_hash), None)
    if match is None:
        raise SkillwareError(f"no POI with hash {poi_hash} in the current check")
    accepted = (*BLESSABLE_KINDS, *SUPPRESSIBLE_KINDS)
    if match.kind not in accepted:
        raise SkillwareError(
            f"POI {poi_hash} ({match.kind}) is not blessable — only "
            f"{', '.join(accepted)} can be accepted; fix the surface instead"
        )
    _require_unlock_receipts(
        skill_root,
        match.kind,
        unlocks,
        poi_hash=poi_hash,
    )
    if match.kind in SUPPRESSIBLE_KINDS:
        _append_poi_blessing(skillware, match)
        return BlessRecord(target=match.target_path, key=match.key or "", deps={})

    src_rel = next(
        rel
        for rel in skillware.src_files()
        if skillware.target_rel(rel) == match.target_path
    )
    expansion = expand_file(skillware, src_rel)
    current = expansion.dep_hashes.get(match.key, {})

    lock = _read_lock(skillware)
    lock_entry = lock.get("files", {}).get(str(match.target), {})
    recipe_entry = next(
        (
            entry
            for entry in lock_entry.get("recipes", [])
            if entry.get("verb") == "derived" and entry.get("heading") == match.key
        ),
        None,
    )
    if recipe_entry is None:
        raise SkillwareError(
            f"no locked derived recipe for {match.target} :: {match.key}"
        )
    old_deps = dict(recipe_entry.get("deps", {}))
    recipe_entry["deps"] = current
    _write_lock(skillware, lock)
    return BlessRecord(
        target=match.target_path,
        key=match.key,
        deps={
            locator: {"old": old_deps.get(locator), "new": sha}
            for locator, sha in current.items()
        },
    )


def bless_pois_by_kind(
    skill_root: Path,
    kind: str,
    *,
    unlocks: tuple[str, ...] = (),
) -> tuple[SkillwarePOIInstance, ...]:
    """Bless all currently visible POIs of one kind."""
    accepted = (*BLESSABLE_KINDS, *SUPPRESSIBLE_KINDS)
    if kind not in accepted:
        raise SkillwareError(
            f"POI kind {kind} is not blessable — only {', '.join(accepted)} can be accepted"
        )
    report = check_skill(skill_root)
    matches = tuple(poi for poi in report.pois if poi.kind == kind)
    if matches:
        _require_unlock_receipts(skill_root, kind, unlocks)
    if kind in SUPPRESSIBLE_KINDS:
        skillware = load_skillware(skill_root)
        lock = _read_lock(skillware)
        blessings = lock.setdefault("blessings", [])
        seen = {record.get("hash") for record in blessings}
        for poi in matches:
            if poi.poi_hash in seen:
                continue
            blessings.append(
                {
                    "hash": poi.poi_hash,
                    "kind": poi.kind,
                    "target": str(poi.target),
                    "key": poi.key,
                }
            )
            seen.add(poi.poi_hash)
        _write_lock(skillware, lock)
        return matches
    for poi in matches:
        bless_skill(skill_root, poi.poi_hash, unlocks=unlocks)
    return matches
