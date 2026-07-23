from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos.skwlint import add_check_selection_args
from agentos.skillware.build import (
    SkillwareError,
    bless_pois_by_kind,
    bless_skill,
    build_skill,
    check_project,
    check_skill,
    expand_file,
    find_project_root,
    load_skillware,
)
from agentos.skillware.model import parse_skw_source

# once-per-kind legend: meaning + prescribed response; the full fix protocols
# live in the agentos-skillware skill (references/check.md)
POI_LEGEND = {
    "parse-error": (
        "the src is below the Parse.Floor — malformed machinery or an unclosed construct",
        "fix the src; parse errors gate the file's other checks and are never blessable",
    ),
    "unresolvable": (
        "a --from target does not resolve at its address",
        "fix the address or restore the target; never blessable",
    ),
    "never-built": ("src exists but no lock entry", "run: agentos skw build"),
    "stale-build": (
        "the on-disk target matches the lock but a recompile differs",
        "run: agentos skw build",
    ),
    "hand-edited": (
        "the compiled target was edited by hand",
        "judgment call: move the content into src, or rebuild over it",
    ),
    "copy-drift": (
        "a copy body no longer equals its target's expansion",
        "mechanical: agentos skw build repairs it",
    ),
    "derived-stale": (
        "a dependency changed since the derived body was written",
        "re-derive the body in src, or accept explicitly: agentos skw bless --poi <hash>",
    ),
    "undeclared-dependency": (
        "compiled text mentions a resolving Dotted.Name without declaring the dependency",
        "declare it with $kw: --from <name>, or baseline current findings: agentos skw bless --kind undeclared-dependency --all",
    ),
    "unhonored-dependency": (
        "a declared dependency is not mentioned in the compiled text",
        "mention the dependency, remove the declaration, or bless the current finding",
    ),
    "dangling-dependency": (
        "a declared --from no longer resolves in the configured depots",
        "restore or repoint the target, or bless: agentos skw bless --kind dangling-dependency --all",
    ),
    "malformed-note": (
        "a --note/--supp is missing its [TYPE] act code or its ^anchor",
        "add the missing [TYPE] and/or trailing ^anchor to the note in src",
    ),
    "address-mismatch": (
        "a fenced element's name does not match the block's declared #address",
        "rename the element or the address so they agree",
    ),
    "legacy-callout": (
        "a v2 [!skw] callout survives outside a fence — inert prose to the parser",
        "rewrite it in the $kw grammar",
    ),
    "non-skw-annotation": (
        "a comment on a skw-managed code surface is not a Skw.Annotation — an annotation leaking outside the language",
        "wrap it as a skw annotation (# $kw: --note/--from …), or accept a throwaway: agentos skw bless --poi <hash>",
    ),
}


def _load(args: argparse.Namespace):
    try:
        return load_skillware(Path(args.skill))
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc


def _cmd_skillware_build(args: argparse.Namespace) -> int:
    _load(args)
    try:
        report = build_skill(Path(args.skill))
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "agentos skw build",
        "skill": str(args.skill),
        "entries": [
            {
                "target": str(entry.target),
                "action": entry.action,
                "src_refreshed": entry.src_refreshed,
            }
            for entry in report.entries
        ],
        "findings": [
            {"line": finding.line, "message": finding.message} for finding in report.findings
        ],
    }
    exit_code = 1 if report.findings else 0
    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code
    print("Skillware build")
    for entry in report.entries:
        refreshed = " (src refreshed)" if entry.src_refreshed else ""
        print(f"- [{entry.action}] {entry.target}{refreshed}")
    for finding in report.findings:
        print(f"- [finding] {finding.message}")
    print(
        f"Summary: {len(report.entries)} file(s), "
        f"{sum(1 for e in report.entries if e.action == 'built')} built, "
        f"{len(report.findings)} finding(s)."
    )
    return exit_code


def _cmd_skillware_project_check(args: argparse.Namespace) -> int:
    project_root = find_project_root(Path.cwd())
    if project_root is None:
        raise CliError(
            "no .agentos/project.json found from the current directory; "
            "pass --skill to check a single package"
        )
    try:
        report = check_project(project_root)
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    enabled, known = _enabled_poi_selectors(args)
    package_pois = [
        (pkg, _filter_pois(pr.pois, enabled, known)) for pkg, pr in report.packages
    ]
    poi_count = sum(len(pois) for _pkg, pois in package_pois)
    payload = {
        "command": "agentos skw check",
        "project_root": str(report.project_root),
        "packages": [
            {
                "package": str(pkg.relative_to(report.project_root))
                if pkg != report.project_root
                else ".",
                "pois": [
                    {"kind": poi.kind, "target": str(poi.target), "key": poi.key, "hash": poi.poi_hash}
                    for poi in pois
                ],
            }
            for pkg, pois in package_pois
        ],
        "summary": {"packages": len(report.packages), "pois": poi_count},
    }
    exit_code = 1 if poi_count else 0
    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code
    print(f"skw check (project scope): {report.project_root}")
    for pkg, pois in package_pois:
        rel = pkg.relative_to(report.project_root) if pkg != report.project_root else Path(".")
        print(f"- {rel}: {len(pois)} POI(s)")
        for poi in pois:
            location = f"{poi.target} :: {poi.key}" if poi.key else str(poi.target)
            print(f"    [{poi.kind}] {location} ({poi.poi_hash})")
    print(f"Summary: {len(report.packages)} package(s), {poi_count} POI(s).")
    return exit_code


# POI kinds are the skw linter's selectable checks. The hard, never-blessable
# kinds that gate a file's other checks are structural (always shown); the rest
# are advisory drift a caller may include/exclude (Impl.Req 702, shared core).
_SKW_STRUCTURAL_KINDS = frozenset({"parse-error", "unresolvable"})
# opt-in kinds: over-report on real surfaces, so they stay off unless
# `--check`ed (mirrors the index `dangling-mention` default-off pattern)
_SKW_DEFAULT_OFF_KINDS = frozenset({"non-skw-annotation"})


@dataclass(frozen=True)
class _SkwCheckKind:
    code: str
    title: str
    default_on: bool = True
    structural: bool = False


def _skw_check_kinds() -> tuple[_SkwCheckKind, ...]:
    return tuple(
        _SkwCheckKind(
            code=kind,
            title=meaning,
            default_on=kind not in _SKW_DEFAULT_OFF_KINDS,
            structural=kind in _SKW_STRUCTURAL_KINDS,
        )
        for kind, (meaning, _response) in POI_LEGEND.items()
    )


def _enabled_poi_selectors(args: argparse.Namespace) -> tuple[set[str], set[str]]:
    """(enabled selectors, all known selectors) resolved from --check/--skip."""
    from agentos.skwlint import check_selector, resolve_enabled_checks

    kinds = _skw_check_kinds()
    enabled = resolve_enabled_checks(
        kinds,
        include=tuple(getattr(args, "check", ()) or ()),
        exclude=tuple(getattr(args, "skip", ()) or ()),
    )
    known = {check_selector(k.code) for k in kinds}
    return {check_selector(k.code) for k in enabled}, known


def _filter_pois(pois, enabled: set[str], known: set[str]):
    """Keep enabled kinds; an unknown kind (absent from the registry) always
    passes — selection never silently hides a POI the registry does not model."""
    from agentos.skwlint import check_selector

    kept = []
    for poi in pois:
        selector = check_selector(poi.kind)
        if selector not in known or selector in enabled:
            kept.append(poi)
    return kept


def _cmd_skillware_check(args: argparse.Namespace) -> int:
    if getattr(args, "list_checks", False):
        from agentos.skwlint import check_registry, render_check_registry

        for line in render_check_registry(check_registry(_skw_check_kinds())):
            print(line)
        return 0
    if getattr(args, "skill", None) is None:
        return _cmd_skillware_project_check(args)
    _load(args)
    try:
        report = check_skill(Path(args.skill))
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    enabled, known = _enabled_poi_selectors(args)
    pois = _filter_pois(report.pois, enabled, known)
    payload = {
        "command": "agentos skw check",
        "skill": str(args.skill),
        "entries": [
            {
                "target": str(entry.target),
                "status": entry.status,
                "copy_drift": list(entry.copy_drift),
                "derived_stale": list(entry.derived_stale),
            }
            for entry in report.entries
        ],
        "pois": [
            {
                "kind": poi.kind,
                "target": str(poi.target),
                "key": poi.key,
                "hash": poi.poi_hash,
                "detail": poi.detail,
            }
            for poi in pois
        ],
        "summary": {"files": len(report.entries), "pois": len(pois)},
    }
    exit_code = 1 if pois else 0
    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code
    print("Skillware check")
    for entry in report.entries:
        print(f"- [{entry.status}] {entry.target}")
    if pois:
        print("Legend:")
        for kind in dict.fromkeys(poi.kind for poi in pois):
            meaning, response = POI_LEGEND.get(
                kind, ("a point of interest", "inspect the src")
            )
            print(f"- {kind} — {meaning}; {response}")
        print("POIs:")
        for poi in pois:
            location = f"{poi.target} :: {poi.key}" if poi.key else f"{poi.target} :: {poi.detail}"
            print(f"- [{poi.kind}] {location} ({poi.poi_hash})")
    print(f"Summary: {len(report.entries)} file(s), {len(pois)} POI(s).")
    return exit_code


def _cmd_skillware_bless(args: argparse.Namespace) -> int:
    _load(args)
    if getattr(args, "all", False) or getattr(args, "kind", None):
        if not args.all or not args.kind:
            raise CliError("bulk bless requires both --kind <poi-kind> and --all")
        try:
            records = bless_pois_by_kind(Path(args.skill), args.kind)
        except SkillwareError as exc:
            raise CliError(str(exc)) from exc
        payload = {
            "command": "agentos skw bless",
            "skill": str(args.skill),
            "kind": args.kind,
            "blessed": [
                {
                    "target": str(poi.target),
                    "key": poi.key,
                    "hash": poi.poi_hash,
                    "detail": poi.detail,
                }
                for poi in records
            ],
            "summary": {"blessed": len(records)},
        }
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        print("Skillware bless")
        print(f"- blessed {len(records)} {args.kind} POI(s)")
        return 0
    if not args.poi:
        raise CliError("bless requires --poi <hash> or --kind <poi-kind> --all")
    try:
        record = bless_skill(Path(args.skill), args.poi)
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "agentos skw bless",
        "skill": str(args.skill),
        "blessed": {
            "target": str(record.target),
            "key": record.key,
            "deps": record.deps,
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("Skillware bless")
    print(f"- blessed: {record.target} :: {record.key}")
    for locator, shas in record.deps.items():
        print(f"  - {locator}: {shas['old']} -> {shas['new']}")
    return 0


def _cmd_skillware_status(args: argparse.Namespace) -> int:
    skillware = _load(args)
    lock_present = (skillware.build_root / "lock.json").is_file()
    files = []
    for src_rel in skillware.src_files():
        source = parse_skw_source((skillware.src_root / src_rel).read_text(encoding="utf-8"))
        expansion = expand_file(skillware, src_rel)
        files.append(
            {
                "src": str(src_rel),
                "target": str(expansion.target_rel),
                "target_exists": (skillware.skill_root / expansion.target_rel).is_file(),
                "recipes": {
                    verb: sum(1 for r in source.recipes if r.verb == verb)
                    for verb in ("copy", "derived")
                },
                "constructs": {
                    command: count
                    for command in ("text", "router", "when", "then")
                    if (count := sum(1 for c in source.constructs if c.command == command))
                },
            }
        )
    payload = {
        "command": "agentos skw status",
        "skill": str(args.skill),
        "lock_present": lock_present,
        "depots": [str(depot) for depot in skillware.depots],
        "files": files,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("Skillware status")
    print(f"- lock: {'present' if lock_present else 'missing'}")
    for entry in files:
        recipes = entry["recipes"]
        print(
            f"- {entry['src']} -> {entry['target']} "
            f"({'exists' if entry['target_exists'] else 'missing'}; "
            f"copy: {recipes['copy']}, derived: {recipes['derived']})"
        )
    return 0


def register_skillware_commands(subparsers: argparse._SubParsersAction) -> None:
    skillware_parser = subparsers.add_parser(
        "skw",
        aliases=["skillware"],
        help="Compile and check a package's runnable files from .skw/src sources.",
        description=(
            "skw: a package's files can be produced from .skw/src/**/*.skw.md "
            "sources — markdown plus $kw machinery lines. build compiles and refreshes "
            "copy bodies; check lints for POIs; bless accepts a derived-stale POI; "
            "status inventories the managed files. (skillware is a deprecated alias.)"
        ),
    )
    skillware_subparsers = skillware_parser.add_subparsers(dest="skillware_command")

    for name, handler, help_text in (
        ("build", _cmd_skillware_build, "Refresh copy bodies, compile targets, write the lock."),
        ("check", _cmd_skillware_check, "Lint for POIs; exits non-zero when any are raised."),
        ("bless", _cmd_skillware_bless, "Accept a derived-stale POI: rewrite its locked dep hashes."),
        ("status", _cmd_skillware_status, "Inventory managed files, recipes, and lock state."),
    ):
        sub = skillware_subparsers.add_parser(name, help=help_text)
        # check with no --skill runs project-scope over every discovered package
        sub.add_argument(
            "--skill",
            required=(name != "check"),
            help="Package root containing .skw/src (omit on check for project scope).",
        )
        sub.add_argument("--json", action="store_true", help="Emit the report as JSON.")
        if name == "check":
            add_check_selection_args(sub, unit="POI kind")
        if name == "bless":
            sub.add_argument("--poi", help="POI identity hash from check output.")
            sub.add_argument("--kind", help="POI kind to bulk bless with --all.")
            sub.add_argument("--all", action="store_true", help="Bless all current POIs of --kind.")
        sub.set_defaults(handler=handler)


__all__ = ["register_skillware_commands"]
