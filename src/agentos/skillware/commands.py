from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.skillware.build import (
    SkillwareError,
    bless_skill,
    build_skill,
    check_skill,
    expand_file,
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
    "never-built": ("src exists but no lock entry", "run: agentos skillware build"),
    "stale-build": (
        "the on-disk target matches the lock but a recompile differs",
        "run: agentos skillware build",
    ),
    "hand-edited": (
        "the compiled target was edited by hand",
        "judgment call: move the content into src, or rebuild over it",
    ),
    "copy-drift": (
        "a copy body no longer equals its target's expansion",
        "mechanical: agentos skillware build repairs it",
    ),
    "derived-stale": (
        "a dependency changed since the derived body was written",
        "re-derive the body in src, or accept explicitly: agentos skillware bless --poi <hash>",
    ),
    "legacy-callout": (
        "a v2 [!skw] callout survives outside a fence — inert prose to the parser",
        "rewrite it in the $kw grammar",
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
        "command": "agentos skillware build",
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


def _cmd_skillware_check(args: argparse.Namespace) -> int:
    _load(args)
    try:
        report = check_skill(Path(args.skill))
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "agentos skillware check",
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
            for poi in report.pois
        ],
        "summary": {"files": len(report.entries), "pois": len(report.pois)},
    }
    exit_code = 1 if report.pois else 0
    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code
    print("Skillware check")
    for entry in report.entries:
        print(f"- [{entry.status}] {entry.target}")
    if report.pois:
        print("Legend:")
        for kind in dict.fromkeys(poi.kind for poi in report.pois):
            meaning, response = POI_LEGEND[kind]
            print(f"- {kind} — {meaning}; {response}")
        print("POIs:")
        for poi in report.pois:
            location = f"{poi.target} :: {poi.key}" if poi.key else f"{poi.target} :: {poi.detail}"
            print(f"- [{poi.kind}] {location} ({poi.poi_hash})")
    print(f"Summary: {len(report.entries)} file(s), {len(report.pois)} POI(s).")
    return exit_code


def _cmd_skillware_bless(args: argparse.Namespace) -> int:
    _load(args)
    try:
        record = bless_skill(Path(args.skill), args.poi)
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    payload = {
        "command": "agentos skillware bless",
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
    lock_present = (skillware.skill_root / ".skillware" / "lock.json").is_file()
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
        "command": "agentos skillware status",
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
        "skillware",
        help="Compile and check a skill's runnable files from .skillware/src sources.",
        description=(
            "Skillware: a skill's files can be produced from .skillware/src/**/*.skw.md "
            "sources — markdown plus $kw machinery lines. build compiles and refreshes "
            "copy bodies; check lints for POIs; bless accepts a derived-stale POI; "
            "status inventories the managed files."
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
        sub.add_argument("--skill", required=True, help="Skill root containing .skillware/src.")
        sub.add_argument("--json", action="store_true", help="Emit the report as JSON.")
        if name == "bless":
            sub.add_argument("--poi", required=True, help="POI identity hash from check output.")
        sub.set_defaults(handler=handler)


__all__ = ["register_skillware_commands"]
