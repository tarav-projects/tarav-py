# $kw: --from Usage.Surface --note [CT] no write commands: agents edit surfaces, the linter checks them
"""The index command set.

Shaped after `tarav`: **grouped, read-and-lint**. There is deliberately no capture, edit,
land, or adopt command — agents edit the markdown surfaces with ordinary file primitives, and
`tarav index linter` checks conformance afterwards.

The only writes here are the ones markdown editing genuinely cannot do by hand: minting an
anchor, writing a record, and accepting a POI.

    tarav index init | config | session | messages
    tarav index blocks | lines | record | write | revise | trace | gate |
                import | remove | resolve | linter | bless | explain
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .authority import ManifestRegistry
from .chatlas import load_session
from .config import Geography, TaravIndexError, resolve_geography
from .gates import GateRef
from .importer import import_depot
from .linter import BAR_CHECKS, CATALOG, bless, lint
from .record.model import EquivalenceKind, LineRecord, SupportRef
from .record.store import IndexStore
from .scope import parse_scope, resolve_scope_surface
from .standing import (
    IndexStanding,
    ReviewSide,
    Standing,
    lines_on_head_surfaces,
    standings,
)
from .surfaces import (
    ProjectIndex,
    discover_surfaces,
    load_head_surfaces,
    read_surface,
    resolve_surface_path,
    write_head_surfaces,
)


def _geo(args: argparse.Namespace) -> Geography:
    start = Path(args.project).expanduser() if getattr(args, "project", None) else None
    return resolve_geography(start)


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=1, ensure_ascii=False, default=str))


def _derive(geo: Geography) -> dict[str, Standing]:
    """Standings, which means scanning the surfaces — index HEAD is where a line *is*."""

    records = IndexStore(geo).all()
    surface_lines = {
        surface: read_surface(resolve_surface_path(surface, geo.project_root), surface)
        for surface in discover_surfaces(geo, geo.project_root)
    }
    head_lines = lines_on_head_surfaces(records, surface_lines, load_head_surfaces(geo))
    return standings(records, head_lines=head_lines)


def _verdicts(geo: Geography) -> dict[str, list]:
    """Every entry's findings, keyed by entry.

    Reading a line means reading its error bar. The estimate exists whether or not anyone
    consults it; what was missing was carrying it to the read path.
    """

    report = lint(geo)
    vector: dict[str, list] = {}
    for finding in (*report.findings, *report.blocked):
        vector.setdefault(finding.subject, []).append(finding)
    return vector


def _gate_from(args: argparse.Namespace) -> GateRef:
    return GateRef(
        archive="chat",
        session_id=args.session,
        token=args.token,
        user_turn_id=args.user_turn,
        agent_turn_id=args.agent_turn,
    )


# -- top level ----------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    geo = _geo(args)
    geo.ensure_project_tier()
    manifests = ManifestRegistry(geo).bootstrap()
    head_path = write_head_surfaces(geo)

    if args.depot:
        ProjectIndex(geo.project_root, args.depot).ensure_layout()

    print(f"project tier   {geo.project_tier}")
    print(f"user tier      {geo.user_tier}")
    print(f"manifests      {', '.join(m.surface_type for m in manifests)}")
    print(f"HEAD surfaces  {head_path.name}")
    if args.depot:
        print(f"depot          skills/{args.depot}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    geo = _geo(args)
    payload = {
        "project_root": str(geo.project_root),
        "project_tier": str(geo.project_tier),
        "user_tier": str(geo.user_tier),
        "project_index": str(geo.index_dir),
        "user_index": str(geo.user_index_dir),
    }
    if args.json:
        _emit(payload)
    else:
        for key, value in payload.items():
            print(f"{key:14} {value}")
    return 0


# -- chatlas ------------------------------------------------------------------


def cmd_chatlas_session(args: argparse.Namespace) -> int:
    session = load_session(_geo(args), args.session)
    print(
        f"{session.session_id}: {len(session.messages)} messages, "
        f"{len(session.touched())} touched"
    )
    return 0


def cmd_chatlas_messages(args: argparse.Namespace) -> int:
    session = load_session(_geo(args), args.session)
    messages = session.touched() if args.touched else session.messages
    if args.contains:
        needle = args.contains.lower()
        messages = tuple(m for m in messages if needle in m.text.lower())
    if args.limit:
        messages = messages[-args.limit :]

    if args.json:
        _emit(
            [
                {
                    "address": m.address,
                    "side": m.side,
                    "at": m.at,
                    "carries_touch": m.carries_touch,
                    "text": m.text,
                }
                for m in messages
            ]
        )
        return 0
    for message in messages:
        flag = "T" if message.carries_touch else " "
        head = message.text.replace("\n", " ")[: args.width]
        print(f"{flag} {message.address} {message.at or '':24} {head}")
    return 0


# -- index ------------------------------------------------------------------




def cmd_index_blocks(args: argparse.Namespace) -> int:
    """Geography by grounding density — the enrichment worklist."""

    geo = _geo(args)
    records = IndexStore(geo).all()
    groups: dict[str, list[LineRecord]] = {}
    for record in records:
        groups.setdefault(record.scope.address, []).append(record)

    rows = []
    for address, members in groups.items():
        grounded = sum(1 for r in members if r.support)
        rows.append(
            {
                "scope": address,
                "kind": str(members[0].scope.kind),
                "lines": len(members),
                "grounded": grounded,
                "density": round(grounded / len(members), 2) if members else 0.0,
            }
        )
    rows.sort(key=lambda r: (r["density"], -r["lines"]))
    if args.limit:
        rows = rows[: args.limit]

    if args.json:
        _emit(rows)
        return 0
    for row in rows:
        print(
            f"{row['density']:>5.2f}  {row['grounded']:>3}/{row['lines']:<3}  "
            f"{row['kind']:<10}  {row['scope']}"
        )
    print(f"\n{len(groups)} scope(s)")
    return 0


def cmd_index_lines(args: argparse.Namespace) -> int:
    """Index lines as they appear on surfaces, independent of the store."""

    geo = _geo(args)
    root = geo.project_root
    surfaces = [args.surface] if args.surface else discover_surfaces(geo, root)
    total = 0
    for surface in surfaces:
        path = resolve_surface_path(surface, root)
        if not path.exists():
            continue
        lines = read_surface(path, surface)
        if not lines:
            continue
        print(f"\n{surface}")
        for line in lines:
            total += 1
            type_part = f"[{line.line_type}]" if line.line_type else "[--]"
            labels = " ".join(line.labels)
            print(f"  {type_part} {line.body[:66]}  {labels}")
    print(f"\n{total} line(s)")
    return 0


def cmd_index_record(args: argparse.Namespace) -> int:
    geo = _geo(args)
    store = IndexStore(geo)
    if args.line:
        _emit(store.get(args.line).to_json())
        return 0

    derived = _derive(geo)
    records = store.all()
    if args.side:
        records = [r for r in records if str(derived[r.id].side) == args.side]
    if args.json:
        _emit([r.to_json() for r in records])
        return 0

    vector = _verdicts(geo)
    for record in records:
        st = derived[record.id]
        marks = "".join(
            (
                "G" if record.support else "p",
                "U" if st.side is ReviewSide.USER else "a",
                "H" if st.index is IndexStanding.HEAD else "T",
                "*" if st.is_trace_head else " ",
                {"direct": "R", "via_trace": "r", "none": " "}[str(st.review)],
                "L" if record.landing else " ",
            )
        )
        signals = vector.get(record.id, [])
        bar = f"  !{len(signals)}" if signals else ""
        print(
            f"{marks} {record.id} {record.line.label or '-':16} "
            f"{record.scope.label}  {record.line.body[:40]}{bar}"
        )
    print(
        f"\n{len(records)} entr(ies)   "
        "G=grounded U=user-side H=index-head *=trace-head R=reviewed L=landing gate\n"
        "!n = n open signals on this entry; a value without its error bar is half a value"
    )
    return 0


def cmd_index_write(args: argparse.Namespace) -> int:
    """Write the record for a line that already exists on a surface.

    The line itself is authored by editing the surface. This supplies only what markdown
    cannot express: identity and support. Which index it belongs to and whether it is current
    design are both derived, so neither is an argument here.
    """

    geo = _geo(args)
    store = IndexStore(geo)
    support = [
        SupportRef(archive="chat", session_id=args.session, message_id=m)
        for m in (args.support or [])
    ]
    record = LineRecord.create(
        parse_scope(args.scope),
        args.type,
        args.body,
        support=support,
        trace=args.trace,
    )
    if args.anchor:
        record = record.relabel(args.anchor)
    record = store.put(record)
    if not record.line.label:
        record = store.mint_label(record)
    print(f"{record.id}  {record.line.label}  {record.scope.address}")
    return 0


def cmd_index_revise(args: argparse.Namespace) -> int:
    """Write a new version of a line into the same trace.

    The equivalence claim is recorded, not implied — it is the one step no machine can check.
    """

    geo = _geo(args)
    store = IndexStore(geo)
    previous = store.get(args.line)
    successor = previous.successor(
        args.type or previous.line.type,
        args.body,
        kind=EquivalenceKind(args.kind),
    )
    successor = store.mint_label(store.put(successor))
    print(f"{successor.id}  {successor.line.label}  trace {successor.trace}")
    print(f"  claims {args.kind} of {previous.id}")

    # The one mutation that changes a record without touching a note, so it points at
    # the edit rather than leaving the agent to find it.
    # The predecessor's label is on the surface being edited, so it names which file
    # answers to this chapter when more than one does.
    note = resolve_scope_surface(
        successor.scope, geo.project_root, contains=previous.line.label
    )
    if note is not None:
        rel = note.relative_to(geo.project_root) if note.is_relative_to(geo.project_root) else note
        print("  surface   replace  " + previous.line.render())
        print("            with     " + successor.line.render())
        print(f"            in       {rel}")
    return 0


def cmd_index_trace(args: argparse.Namespace) -> int:
    geo = _geo(args)
    store = IndexStore(geo)
    members = store.by_trace(args.trace)
    if not members:
        print(f"no trace {args.trace}", file=sys.stderr)
        return 1
    derived = _derive(geo)
    print(
        f"trace {args.trace}   reviewed={any(m.review for m in members)}   "
        f"landed={any(m.landing for m in members)}"
    )
    for member in members:
        st = derived[member.id]
        head = " HEAD" if st.is_trace_head else ""
        print(f"  {member.id} {member.line.label or '-':16} {st.review:9}{st.index:5}{head}")
        print(f"    [{member.line.type}] {member.line.body}")
    return 0


def cmd_index_gate(args: argparse.Namespace) -> int:
    """Record a user gate on a line: the review turn, or the approval that lands it to HEAD.

    Recording is not asserting. The gate names turns in an immutable archive, and
    `tarav index linter` checks that the token actually round-trips before it counts.
    """

    geo = _geo(args)
    store = IndexStore(geo)
    record = store.get(args.line)
    gate = _gate_from(args)
    updated = record.with_landing(gate) if args.kind == "landing" else record.with_review(gate)
    store.put(updated)

    from .gates import verify_gate

    check = verify_gate(geo, gate, record.line.body)
    print(f"{record.id}  {args.kind} gate recorded  trace {record.trace}")
    print(f"  {check.verdict}: {check.detail}")
    return 0


def cmd_index_remove(args: argparse.Namespace) -> int:
    """Remove an entry. Git records the deletion; the index does not duplicate it."""

    geo = _geo(args)
    store = IndexStore(geo)
    record = store.get(args.line)
    store.remove(args.line)
    print(f"removed {record.id}")
    if record.grounded:
        print("  grounded: `tarav index linter` will report the lost coverage")
    return 0


def cmd_index_resolve(args: argparse.Namespace) -> int:
    geo = _geo(args)
    store = IndexStore(geo)
    record = store.by_label(args.label)
    if record is None:
        print(f"{args.anchor} resolves to no index entry", file=sys.stderr)
        return 1
    if args.json:
        _emit(record.to_json())
        return 0
    st = _derive(geo)[record.id]
    print(f"anchor  {record.line.label}")
    print(f"entry   {record.id}  [{st.side}]  {st.index}  review={st.review}")
    print(f"line    [{record.line.type}] {record.line.body}")
    print(f"scope   {record.scope.address}  ({record.scope.kind})")
    for ref in record.support:
        message = None
        try:
            message = load_session(geo, ref.session_id).message(ref.message_id)
        except TaravIndexError:
            pass
        excerpt = message.text.replace("\n", " ")[:90] if message else "(unreachable)"
        print(f"  support  {ref.message_id[:16]}…  {excerpt}")

    signals = _verdicts(geo).get(record.id, [])
    print(f"verdict  {len(signals)} open signal(s)")
    for finding in signals:
        print(f"  {finding.status:8} {finding.evaluator:6} {finding.poi_class}")
        print(f"           {finding.source}")
    return 0


def cmd_index_import(args: argparse.Namespace) -> int:
    """Bring a legacy depot's notes into the current layout and record every line.

    Reads and copies; the source depot is never modified. Nothing is grounded and nothing is
    promoted — tarav1's review evidence is not evidence this design can check.
    """

    geo = _geo(args)
    report = import_depot(
        geo,
        Path(args.depot_root).expanduser().resolve(),
        depot=args.depot,
        home=args.home,
        chapter=args.chapter,
    )
    print(f"imported {report.depot} → homes/{report.home}")
    for surface in report.chapters:
        print(f"  {surface}")
    print(f"\n{report.lines} line(s) recorded, {len(report.chapters)} chapter(s)")
    if report.relabelled:
        print(f"{len(report.relabelled)} relabelled on collision:")
        for old, new in report.relabelled:
            print(f"  {old} → {new}")
    if report.unlabelled:
        print(f"{report.unlabelled} line(s) had no label; fresh ones were minted")
    print("nothing grounded, nothing promoted — both are gated acts taken afterwards")
    return 0


def cmd_index_linter(args: argparse.Namespace) -> int:
    geo = _geo(args)
    if args.list_checks:
        for entry in CATALOG:
            state = "dev" if entry.dev else ("on " if entry.default_on else "off")
            print(f"{entry.name:26} [{state}] {entry.tier:11} {entry.source}")
        return 0

    dev = args.lane == "dev"
    report = lint(geo, check=args.check, skip=args.skip, dev=dev)
    if report.is_dev and not args.json:
        print("DEV LANE — not a verdict about the project, a verdict about the machinery")
        for name in report.dev:
            entry = next(c for c in CATALOG if c.name == name)
            print(f"  {name} stands in for {entry.replaces}  {entry.source}")
        print()
    if args.json:
        _emit(
            {
                "results": [
                    {"check": r.name, "status": str(r.status), "reason": r.reason}
                    for r in report.results
                ],
                "records_checked": report.records_checked,
                "surface_lines_checked": report.surface_lines_checked,
                "findings": [_finding_json(f) for f in report.findings],
                "blocked": [_finding_json(f) for f in report.blocked],
                "blessed": len(report.blessed),
                "dev": list(report.dev),
            }
        )
        return 1 if report.findings else 0

    scanned = (
        f"{report.records_checked} record(s), "
        f"{report.surface_lines_checked} surface line(s)"
    )

    for poi_class, findings in report.by_class().items():
        print(f"\n{poi_class}  ({len(findings)})")
        for finding in findings:
            print(f"  {finding.identity}  {finding.subject}  {finding.source or ''}")
            for key, value in finding.operands.items():
                print(f"      {key} = {value!r}")

    if report.blocked or report.blocked_checks:
        print("\nUnverifiable — checked nothing, which is not the same as clean")
        for result in report.blocked_checks:
            print(f"  {result.name}: {result.reason}")
        for finding in report.blocked:
            print(f"  {finding.poi_class}  {finding.subject}")

    concentrated = {s: f for s, f in report.by_subject().items() if len(f) > 2}
    if concentrated:
        print("\nConcentration (many assertions on one state, or one across many states)")
        for subject, findings in sorted(
            concentrated.items(), key=lambda kv: -len(kv[1])
        ):
            print(f"  {subject}  {len(findings)} findings")

    print(f"\n{report.summary()}   over {scanned}")
    if report.blessed:
        print(f"{len(report.blessed)} blessed")
    return 1 if report.findings else 0


def _finding_json(finding) -> dict[str, object]:
    return {
        "class": finding.poi_class,
        "id": finding.identity,
        "subject": finding.subject,
        "status": str(finding.status),
        "evaluator": str(finding.evaluator),
        "operands": finding.operands,
        "source": finding.source,
        "surface": finding.surface,
        "tier": str(finding.tier),
    }


def cmd_index_bless(args: argparse.Namespace) -> int:
    """Accept one POI on the user's evidence.

    A blessing silences a check, so it is gated like everything else that claims the user
    decided something. The linter revokes it if the archive contradicts the gate.
    """

    bless(_geo(args), args.identity, _gate_from(args))
    print(f"blessed {args.identity}")
    return 0


# -- poi ----------------------------------------------------------------------


def cmd_poi_explain(args: argparse.Namespace) -> int:
    """Point at the check rather than describe it.

    A prose description of what a check computes is a stored copy of a computable fact, so
    what is printed here is the address of the implementation plus the two things the code
    genuinely does not say: why the constraint exists, and what answers are legitimate.
    """

    needle = args.poi_class.lower()
    matches = [
        c
        for c in CATALOG
        if needle in c.name.lower() or needle in f"index.linter/{c.name}".lower()
    ]
    if not matches:
        print(f"no check matches {args.poi_class!r}", file=sys.stderr)
        print("try `tarav index linter --list-checks`", file=sys.stderr)
        return 1

    for check in matches:
        print(f"\n{check.name}")
        print(f"  computes  {check.source}   ← read it; the body is the specification")
        print(f"  tier      {check.tier}")
        print(f"  default   {'on' if check.default_on else 'off'}")
        if check.name in BAR_CHECKS:
            print("  bar       yes — typed, scoped, and grounded is the minimum")
        if check.why:
            print("  why")
            for line in check.why.splitlines():
                print(f"    {line}" if line.strip() else "")
        if check.resolutions:
            print("  resolutions (choose case by case; none is prescribed):")
            for resolution in check.resolutions:
                print(f"    - {resolution}")
    return 0


# -- parser -------------------------------------------------------------------


def _dispatch(args: argparse.Namespace) -> int:
    """The umbrella CLI dispatches on `handler`; the index tree sets `func`."""
    return args.func(args)


def register_index_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register the index command set under `tarav index`.

    One flat namespace: there is no `tarav index index`, and no `chatlas` or
    `poi` group here — `tarav chatlas2` and `tarav poi` already own those.
    """
    index = subparsers.add_parser(
        "index", help="Touched.Index entries, surfaces, and linting."
    )
    index.add_argument("--project", help="project root override")
    index.add_argument("--json", action="store_true", help="emit JSON")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index.set_defaults(handler=_dispatch)

    p = index_sub.add_parser("init", help="initialize the project tier and manifests")
    p.add_argument("--depot", help="also create this depot's layout")
    p.set_defaults(func=cmd_init)

    p = index_sub.add_parser("config", help="show resolved geo")
    p.set_defaults(func=cmd_config)

    p = index_sub.add_parser("session", help="summarize one normalized chat session")
    p.add_argument("session")
    p.set_defaults(func=cmd_chatlas_session)

    p = index_sub.add_parser("messages", help="list messages with touch standing")
    p.add_argument("session")
    p.add_argument("--touched", action="store_true", help="only qualifying editions")
    p.add_argument("--contains", help="substring filter")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--width", type=int, default=90)
    p.set_defaults(func=cmd_chatlas_messages)

    p = index_sub.add_parser("blocks", help="geo by grounding density")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(func=cmd_index_blocks)

    p = index_sub.add_parser("lines", help="index lines as they appear on surfaces")
    p.add_argument("--surface")
    p.set_defaults(func=cmd_index_lines)

    p = index_sub.add_parser("record", help="inspect index entries")
    p.add_argument("--line")
    p.add_argument("--side", choices=["agent", "user"], help="filter by derived review side")
    p.set_defaults(func=cmd_index_record)

    p = index_sub.add_parser("write", help="write the record for a surface-authored line")
    p.add_argument("--scope", required=True, help="Block.Path or @Locator.Name")
    p.add_argument("--body", required=True)
    p.add_argument("--type", help="Line.Type code")
    p.add_argument("--anchor")
    p.add_argument("--session")
    p.add_argument("--support", nargs="*", help="touched message addresses")
    p.add_argument("--trace", help="join an existing trace (same indexed semantic)")
    p.set_defaults(func=cmd_index_write)

    p = index_sub.add_parser(
        "revise", help="write a new version of a line into its trace"
    )
    p.add_argument("line", help="the line this revises")
    p.add_argument("--body", required=True)
    p.add_argument("--type")
    p.add_argument(
        "--kind", choices=["rename", "rephrase"], default="rephrase",
        help="rename is mechanically verifiable; rephrase is agent judgment",
    )
    p.set_defaults(func=cmd_index_revise)

    p = index_sub.add_parser("trace", help="show one trace and its members")
    p.add_argument("trace")
    p.set_defaults(func=cmd_index_trace)

    p = index_sub.add_parser("remove", help="remove an entry from the semantic model")
    p.add_argument("line")
    p.set_defaults(func=cmd_index_remove)

    def _gate_args(parser_):
        parser_.add_argument("--session", required=True)
        parser_.add_argument("--token", required=True, help="the token both turns carry")
        parser_.add_argument("--user-turn", required=True, help="the turn that opened the gate")
        parser_.add_argument("--agent-turn", required=True, help="the turn it answered")

    p = index_sub.add_parser("gate", help="record a user gate on a line")
    p.add_argument("line")
    p.add_argument(
        "--kind", choices=["review", "landing"], default="review",
        help="review evidences reading; landing evidences approval to HEAD",
    )
    _gate_args(p)
    p.set_defaults(func=cmd_index_gate)

    p = index_sub.add_parser("resolve", help="resolve a label to its entry and standing")
    p.add_argument("label")
    p.set_defaults(func=cmd_index_resolve)

    p = index_sub.add_parser("import", help="bring a legacy depot into the current layout")
    p.add_argument("depot_root", help="path to the tarav1 depot")
    p.add_argument("--depot", help="depot name (defaults to the directory name)")
    p.add_argument("--home", default="agent")
    p.add_argument("--chapter", default="design")
    p.set_defaults(func=cmd_index_import)

    p = index_sub.add_parser("linter", help="run conformance checks")
    p.add_argument(
        "lane", nargs="?", choices=["dev"], default=None,
        help="dev runs the dev lane: registered dev checks displace the ones they stand in for",
    )
    p.add_argument("--check", action="append", help="run only this check; repeatable")
    p.add_argument("--skip", action="append", help="skip this check; repeatable")
    p.add_argument("--list-checks", action="store_true", help="print the check catalog")
    p.set_defaults(func=cmd_index_linter)

    p = index_sub.add_parser("bless", help="accept one exact POI, on a user gate")
    p.add_argument("identity")
    _gate_args(p)
    p.set_defaults(func=cmd_index_bless)

    p = index_sub.add_parser("explain", help="explain a check or POI class")
    p.add_argument("poi_class")
    p.set_defaults(func=cmd_poi_explain)


__all__ = ["register_index_commands"]
