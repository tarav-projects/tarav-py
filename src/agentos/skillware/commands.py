# $kw: ^skillware-commands --from Skw.Edition.History.Service --from POI.System --from POI.Linter --note [DF] Skillware command registration including required-support edition-history recording and common POI reporting ^c20260725-12u --supp schema migration authorized ^c20260725-14u --supp live Chatlas resolution authorized ^c20260725-15u --supp project policy integration authorized ^c20260725-25u --supp CLI diagnostics expose context-assembly and citation POIs ^c20260725-27u --supp opt-in completeness and amendment authorized ^c20260725-32u --supp common POI migration execution ^c20260729-49u
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.json_input import load_json_object_arg
from agentos.bloberia import BloberiaDepot
from agentos.poi import (
    POILinterReport,
    add_check_selection_args,
    build_poi_report,
)
from agentos.skillware.build import (
    SkillwareError,
    bless_pois_by_kind,
    bless_skill,
    build_skill,
    check_project,
    check_skill,
    expand_edition_history_targets,
    expand_file,
    find_project_root,
    load_project_skw_config,
    load_skillware,
    unlock_requirements,
)
from agentos.skillware.model import parse_skw_source
from agentos.skillware.edition_history import (
    EditionFile,
    EditionHistoryError,
    EditionHistoryService,
    EditionSupportResolver,
    DEFAULT_EDITION_HISTORY_DEPOT,
    default_edition_history_depot,
)
from agentos.skillware.poi import (
    edition_history_findings_to_pois,
)

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
    "uncited-dependency": (
        "a --cite target is not explicit in the compiled surface",
        "cite the target visibly, change the dependency role, or bless the current finding",
    ),
    "context-assembly-bypass": (
        "a surface depends on an assembly-covered source without loading its context assembly",
        "add --dev-from <assembly-file>, or bless the intentional bypass",
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
        "wrap it as a skw annotation (# $kw: --note/--from …), delete the comment, or accept a throwaway: agentos skw bless --poi <hash>",
    ),
    "illegal-attachment": (
        "a skw block attaches at a point outside the surface's allow-set (skw-code: only the line-1 file point is open)",
        "move the block to a sanctioned point (the line-1 file header), or open a finer point in config",
    ),
    "missing-header": (
        "a skw-managed code file has no line-1 annotation — the required file point is empty",
        "add the line-1 # $kw: header, or relax the presence policy in config",
    ),
    "missing-edition-history": (
        "a configured file has no valid edition/session association",
        "inspect Git and Chatlas, then record a supported association",
    ),
    "invalid-edition-history-record": (
        "an edition-history record violates the service schema",
        "repair or replace the invalid Bloberia record",
    ),
    "duplicate-edition-session": (
        "one file edition/session association is recorded more than once",
        "remove the duplicate Bloberia record",
    ),
    "unresolvable-edition-support": (
        "an edition/session support set cannot be resolved through Chatlas",
        "repair the exact session/event support members",
    ),
    "unsupported-git-edition": (
        "a Git edition has no resolvable edition/session association",
        "recover candidate chats and record supported associations",
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
            {"line": finding.line, "message": finding.message}
            for finding in report.findings
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


def _edition_history_project_pois(
    project_root: Path,
    *,
    support_resolver: EditionSupportResolver | None,
    require_complete: bool,
):
    config = load_project_skw_config(project_root)
    policy = config.edition_history
    if policy is None:
        return ()
    targets = expand_edition_history_targets(project_root, policy)
    depot = (
        (project_root / policy.depot).resolve()
        if policy.depot is not None
        else project_root / DEFAULT_EDITION_HISTORY_DEPOT
    )
    result = EditionHistoryService(
        BloberiaDepot(depot),
        support_resolver=support_resolver,
    ).check(targets, require_complete=require_complete)
    return edition_history_findings_to_pois(result.findings)


def _cmd_skillware_project_check(args: argparse.Namespace) -> int:
    project_root = find_project_root(Path.cwd())
    if project_root is None:
        raise CliError(
            "no .agentos/project.json found from the current directory; "
            "pass --skill to check a single package"
        )
    enabled, known = _enabled_poi_selectors(args)
    from agentos.poi import check_selector

    require_complete = check_selector("unsupported-git-edition") in enabled
    try:
        report = check_project(project_root)
        project_pois = _edition_history_project_pois(
            project_root,
            support_resolver=getattr(args, "edition_history_support_resolver", None),
            require_complete=require_complete,
        )
    except SkillwareError as exc:
        raise CliError(str(exc)) from exc
    except EditionHistoryError as exc:
        raise CliError(str(exc)) from exc
    package_pois = [
        (pkg, _filter_pois(pr.pois, enabled, known)) for pkg, pr in report.packages
    ]
    project_pois = _filter_pois(project_pois, enabled, known)
    poi_count = len(project_pois) + sum(len(pois) for _pkg, pois in package_pois)
    all_pois = [poi for _package, pois in package_pois for poi in pois] + list(
        project_pois
    )
    diagnostics = tuple(
        diagnostic
        for _package, package_report in report.packages
        for diagnostic in package_report.diagnostics
        if diagnostic.evidence.get("compatibility_poi")
        in {poi.instance_id for poi in all_pois}
    )
    domain = {
        "command": "agentos skw check",
        "project_root": str(report.project_root),
        "packages": [
            {
                "package": str(pkg.relative_to(report.project_root))
                if pkg != report.project_root
                else ".",
                "poi_ids": [poi.instance_id for poi in pois],
            }
            for pkg, pois in package_pois
        ],
        "project_poi_ids": [poi.instance_id for poi in project_pois],
    }
    linter_report = POILinterReport(
        poi_report=build_poi_report(all_pois),
        diagnostics=diagnostics,
        summary={
            "packages": len(report.packages),
            "poi_count": poi_count,
            "diagnostic_count": len(diagnostics),
        },
        domain=domain,
    )
    exit_code = 1 if poi_count else 0
    if args.json:
        print(json.dumps(linter_report.as_dict(), indent=2))
        return exit_code
    print(f"skw check (project scope): {report.project_root}")
    if project_pois:
        print(f"- project policy: {len(project_pois)} POI(s)")
        for poi in project_pois:
            print(f"    [{poi.kind}] {poi.target} ({poi.poi_hash})")
    for pkg, pois in package_pois:
        rel = (
            pkg.relative_to(report.project_root)
            if pkg != report.project_root
            else Path(".")
        )
        print(f"- {rel}: {len(pois)} POI(s)")
        for poi in pois:
            location = f"{poi.target} :: {poi.key}" if poi.key else str(poi.target)
            print(f"    [{poi.kind}] {location} ({poi.poi_hash})")
    rendered = linter_report.render_text()
    if rendered:
        print(rendered)
    print(
        f"Summary: {len(report.packages)} package(s), {poi_count} POI(s), "
        f"{len(diagnostics)} diagnostic(s)."
    )
    return exit_code


# POI kinds are the skw linter's selectable checks. The hard, never-blessable
# kinds that gate a file's other checks are structural (always shown); the rest
# are advisory drift a caller may include/exclude (Impl.Req 702, shared core).
_SKW_STRUCTURAL_KINDS = frozenset({"parse-error", "unresolvable"})
# opt-in kinds: over-report on real surfaces, so they stay off unless
# `--check`ed (mirrors the index `dangling-mention` default-off pattern)
_SKW_DEFAULT_OFF_KINDS = frozenset({"non-skw-annotation", "unsupported-git-edition"})


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
    from agentos.poi import check_selector, resolve_enabled_checks

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
    from agentos.poi import check_selector

    kept = []
    for poi in pois:
        selector = check_selector(poi.kind)
        if selector not in known or selector in enabled:
            kept.append(poi)
    return kept


def _cmd_skillware_check(args: argparse.Namespace) -> int:
    if getattr(args, "list_checks", False):
        from agentos.poi import check_registry, render_check_registry

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
    requirements_by_kind = {
        kind: unlock_requirements(Path(args.skill), kind)
        for kind in {poi.kind for poi in pois}
    }
    visible_ids = {poi.instance_id for poi in pois}
    diagnostics = tuple(
        diagnostic
        for diagnostic in report.diagnostics
        if diagnostic.evidence.get("compatibility_poi") in visible_ids
    )
    linter_report = POILinterReport(
        poi_report=build_poi_report(pois),
        diagnostics=diagnostics,
        summary={
            "files": len(report.entries),
            "poi_count": len(pois),
            "diagnostic_count": len(diagnostics),
        },
        domain={
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
            "unlock_requirements": {
                kind: [
                    {
                        "surface": requirement.surface,
                        "registry": str(requirement.registry),
                    }
                    for requirement in requirements
                ]
                for kind, requirements in requirements_by_kind.items()
            },
        },
    )
    exit_code = 1 if pois else 0
    if args.json:
        print(json.dumps(linter_report.as_dict(), indent=2))
        return exit_code
    print("Skillware check")
    for entry in report.entries:
        print(f"- [{entry.status}] {entry.target}")
    rendered = linter_report.render_text()
    if rendered:
        print(rendered)
    if any(requirements_by_kind.values()):
        print("Context requirements:")
        for kind, requirements in requirements_by_kind.items():
            for requirement in requirements:
                print(
                    f"- {kind}: {requirement.surface} "
                    f"(registry: {requirement.registry})"
                )
    print(
        f"Summary: {len(report.entries)} file(s), {len(pois)} POI(s), "
        f"{len(diagnostics)} diagnostic(s)."
    )
    return exit_code


def _cmd_skillware_bless(args: argparse.Namespace) -> int:
    _load(args)
    unlocks = tuple(getattr(args, "unlock", ()) or ())
    if getattr(args, "all", False) or getattr(args, "kind", None):
        if not args.all or not args.kind:
            raise CliError("bulk bless requires both --kind <poi-kind> and --all")
        try:
            records = bless_pois_by_kind(
                Path(args.skill),
                args.kind,
                unlocks=unlocks,
            )
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
        record = bless_skill(Path(args.skill), args.poi, unlocks=unlocks)
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
        source = parse_skw_source(
            (skillware.src_root / src_rel).read_text(encoding="utf-8")
        )
        expansion = expand_file(skillware, src_rel)
        files.append(
            {
                "src": str(src_rel),
                "target": str(expansion.target_rel),
                "target_exists": (
                    skillware.skill_root / expansion.target_rel
                ).is_file(),
                "recipes": {
                    verb: sum(1 for r in source.recipes if r.verb == verb)
                    for verb in ("copy", "derived")
                },
                "constructs": {
                    command: count
                    for command in (
                        "text",
                        "router",
                        "when",
                        "then",
                        "routing-table",
                        "router-row",
                        "routing-view",
                    )
                    if (
                        count := sum(
                            1 for c in source.constructs if c.command == command
                        )
                    )
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


def _edition_history_service(
    args: argparse.Namespace,
    references: tuple[Path | str, ...],
) -> EditionHistoryService:
    if args.depot is not None:
        depot = Path(args.depot)
    else:
        depots = {default_edition_history_depot(reference) for reference in references}
        if len(depots) != 1:
            raise EditionHistoryError(
                "edition-history targets span multiple Agentos projects; "
                "pass --depot explicitly"
            )
        depot = depots.pop()
    return EditionHistoryService(
        BloberiaDepot(depot),
        support_resolver=args.edition_history_support_resolver,
    )


def _print_edition_history_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_edition_history_record(args: argparse.Namespace) -> int:
    support = load_json_object_arg(
        args.support_json,
        args.support_file,
        field_name="support",
    )
    try:
        service = _edition_history_service(args, (args.file,))
        result = service.record(
            args.file,
            args.commit,
            args.session,
            support=support,
            session_started_at=args.session_started_at,
        )
        file = EditionFile.resolve(args.file)
    except EditionHistoryError as exc:
        raise CliError(str(exc)) from exc
    _print_edition_history_json(
        {
            "command": "agentos skw edition-history record",
            "depot": str(service.depot.root),
            "file": file.as_dict(),
            "result": result.as_dict(),
        }
    )
    return 0


def _cmd_edition_history_list(args: argparse.Namespace) -> int:
    try:
        service = _edition_history_service(args, (args.file,))
        history = service.list(args.file)
    except EditionHistoryError as exc:
        raise CliError(str(exc)) from exc
    payload = history.as_dict()
    payload.update(
        {
            "command": "agentos skw edition-history list",
            "depot": str(service.depot.root),
            "summary": {
                "editions": len(history.editions),
                "supported_editions": history.supported_editions,
                "unsupported_editions": history.unsupported_editions,
                "sessions": sum(len(edition.sessions) for edition in history.editions),
            },
        }
    )
    _print_edition_history_json(payload)
    return 0


def _cmd_edition_history_check(args: argparse.Namespace) -> int:
    try:
        service = _edition_history_service(args, tuple(args.target))
        targets = [EditionFile.resolve(target) for target in args.target]
        result = service.check(
            args.target,
            require_complete=args.complete,
        )
    except EditionHistoryError as exc:
        raise CliError(str(exc)) from exc
    pois = edition_history_findings_to_pois(result.findings)
    linter_report = POILinterReport(
        poi_report=build_poi_report(pois),
        summary={
            "target_count": len(targets),
            "poi_count": len(pois),
        },
        domain={
            "command": "agentos skw edition-history check",
            "depot": str(service.depot.root),
            "targets": [target.as_dict() for target in targets],
            "status": "ok" if result.ok else "error",
        },
    )
    _print_edition_history_json(linter_report.as_dict())
    return 0 if result.ok else 1


def _cmd_edition_history_amend(args: argparse.Namespace) -> int:
    support = load_json_object_arg(
        args.support_json,
        args.support_file,
        field_name="support",
    )
    try:
        service = _edition_history_service(args, (args.file,))
        result = service.amend(
            args.file,
            args.record,
            support=support,
            session_started_at=args.session_started_at,
        )
        file = EditionFile.resolve(args.file)
    except EditionHistoryError as exc:
        raise CliError(str(exc)) from exc
    _print_edition_history_json(
        {
            "command": "agentos skw edition-history amend",
            "depot": str(service.depot.root),
            "file": file.as_dict(),
            "result": result.as_dict(),
        }
    )
    return 0


def _add_edition_history_commands(
    subparsers: argparse._SubParsersAction,
    *,
    support_resolver: EditionSupportResolver | None,
) -> None:
    parser = subparsers.add_parser(
        "edition-history",
        help="Record, list, and check file edition/chat provenance.",
    )
    parser.set_defaults(edition_history_support_resolver=support_resolver)
    commands = parser.add_subparsers(
        dest="edition_history_command",
        required=True,
    )

    record_parser = commands.add_parser(
        "record",
        help="Record one file edition/session association.",
    )
    record_parser.add_argument("--file", required=True, help="Managed file path.")
    record_parser.add_argument(
        "--commit",
        required=True,
        help="Git commit identity for the file edition.",
    )
    record_parser.add_argument(
        "--session",
        required=True,
        help="Neutral Chatlas session identity hash.",
    )
    record_parser.add_argument(
        "--session-started-at",
        help="Optional Chatlas session start time as ISO 8601.",
    )
    support = record_parser.add_mutually_exclusive_group(required=True)
    support.add_argument(
        "--support-json",
        help="Embedded chatlas.support-set.v1 JSON object.",
    )
    support.add_argument(
        "--support-file",
        help="Path to embedded chatlas.support-set.v1 JSON.",
    )
    record_parser.add_argument(
        "--depot",
        help="Bloberia depot override; defaults below the file's Agentos project.",
    )
    record_parser.set_defaults(handler=_cmd_edition_history_record)

    list_parser = commands.add_parser(
        "list",
        help="List grouped edition history for one file.",
    )
    list_parser.add_argument("--file", required=True, help="Managed file path.")
    list_parser.add_argument(
        "--depot",
        help="Bloberia depot override; defaults below the file's Agentos project.",
    )
    list_parser.set_defaults(handler=_cmd_edition_history_list)

    check_parser = commands.add_parser(
        "check",
        help="Require edition history for explicit target files.",
    )
    check_parser.add_argument(
        "--target",
        action="append",
        required=True,
        help="Managed file requiring edition history; repeatable.",
    )
    check_parser.add_argument(
        "--depot",
        help="Bloberia depot override; defaults below the targets' Agentos project.",
    )
    check_parser.add_argument(
        "--complete",
        action="store_true",
        help="Report every Git edition lacking resolvable session support.",
    )
    check_parser.set_defaults(handler=_cmd_edition_history_check)

    amend_parser = commands.add_parser(
        "amend",
        help="Replace one association's support set.",
    )
    amend_parser.add_argument("--file", required=True, help="Managed file path.")
    amend_parser.add_argument(
        "--record",
        required=True,
        help="Bloberia record identity from edition-history list.",
    )
    amend_parser.add_argument(
        "--session-started-at",
        help="Replacement Chatlas session start time as ISO 8601.",
    )
    support = amend_parser.add_mutually_exclusive_group(required=True)
    support.add_argument(
        "--support-json",
        help="Replacement chatlas.support-set.v1 JSON object.",
    )
    support.add_argument(
        "--support-file",
        help="Path to replacement chatlas.support-set.v1 JSON.",
    )
    amend_parser.add_argument(
        "--depot",
        help="Bloberia depot override; defaults below the file's Agentos project.",
    )
    amend_parser.set_defaults(handler=_cmd_edition_history_amend)


def register_skillware_commands(
    subparsers: argparse._SubParsersAction,
    *,
    edition_history_support_resolver: EditionSupportResolver | None = None,
) -> None:
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
    skillware_parser.set_defaults(
        edition_history_support_resolver=edition_history_support_resolver
    )
    skillware_subparsers = skillware_parser.add_subparsers(dest="skillware_command")
    _add_edition_history_commands(
        skillware_subparsers,
        support_resolver=edition_history_support_resolver,
    )

    for name, handler, help_text in (
        (
            "build",
            _cmd_skillware_build,
            "Refresh copy bodies, compile targets, write the lock.",
        ),
        (
            "check",
            _cmd_skillware_check,
            "Lint for POIs; exits non-zero when any are raised.",
        ),
        (
            "bless",
            _cmd_skillware_bless,
            "Accept a derived-stale POI: rewrite its locked dep hashes.",
        ),
        (
            "status",
            _cmd_skillware_status,
            "Inventory managed files, recipes, and lock state.",
        ),
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
            sub.add_argument(
                "--all", action="store_true", help="Bless all current POIs of --kind."
            )
            sub.add_argument(
                "--unlock",
                action="append",
                default=[],
                help="Unlock-token receipt from a required context surface; repeatable.",
            )
        sub.set_defaults(handler=handler)


__all__ = ["register_skillware_commands"]
