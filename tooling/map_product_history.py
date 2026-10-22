"""Explicit agent replay policy for a historical Product Mapping exercise.

This is an operational driver, not the workflow's default confirmation policy.
Run with `tarav run -- tooling/map_product_history.py --help`. Without --apply,
it only lists checkpoint commits. --apply records decisions as the named Agent.
"""

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4
import json

from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.product_mapping import ContinuityDecision, ProductMapper
from tarav.l1.product_mapping.alignment import chunk, partition


POLICY = "conservative-byte-evidence-v1"


def decide(mapper, proposal):
    """The replay Agent's chosen policy, kept separate from generic map mechanics.

    Exact bytes retain IDs except ambiguous cross-file matches. Changed ranges
    retain IDs only with >=80% matching byte evidence within the proposed pair.
    Weaker evidence creates new IDs; large edited ranges are explicitly split.
    Ratios are evidence for this operational choice, never a semantic guarantee.
    """
    changes = mapper.changes(proposal)
    previous = mapper.load(proposal.typed.base) if proposal.typed.base else None
    old = {c.id: c for c in previous.typed.chunks} if previous else {}
    old_blobs = defaultdict(set)
    new_blobs = defaultdict(set)
    for c in old.values():
        old_blobs[c.blob].add(c.path)
    for c in proposal.typed.chunks:
        new_blobs[c.blob].add(c.path)
    changed = {c["id"]: c for c in changes}
    decisions, updated, evidence = [], [], []
    track = mapper.track().typed
    with mapper.product.batch():
        for candidate in proposal.typed.chunks:
            change = changed.get(candidate.id)
            if change is None:
                updated.append(candidate)
                continue
            source = old.get(candidate.id)
            if source is None:
                updated.append(candidate)
                decisions.append(ContinuityDecision(source_ids=[], target_ids=[candidate.id],
                                                     reason="New committed surface partition"))
                continue
            after = mapper.product.blob(candidate.blob)[candidate.start:candidate.end]
            before = mapper.product.blob(source.blob)[source.start:source.end]
            ambiguous = source.path != candidate.path and (
                len(old_blobs[source.blob]) > 1 or len(new_blobs[candidate.blob]) > 1)
            # Count exact matched line bytes; huge lines use bounded blocks. This
            # is conservative evidence, avoiding quadratic character alignment.
            if before == after:
                similarity = 1.0
            else:
                units_before, units_after = before.splitlines(keepends=True), after.splitlines(keepends=True)
                if max((len(line) for line in units_before + units_after), default=0) > 65536:
                    units_before = [before[i:i + 256] for i in range(0, len(before), 256)]
                    units_after = [after[i:i + 256] for i in range(0, len(after), 256)]
                matches = SequenceMatcher(None, units_before, units_after, autojunk=True)
                matched = sum(sum(map(len, units_before[m.a:m.a + m.size]))
                              for m in matches.get_matching_blocks())
                similarity = 2 * matched / max(1, len(before) + len(after))
            preserve = similarity >= .8 and not ambiguous
            split = before != after and len(after) > 2 * (track.target_bytes + track.boundary_bytes)
            if preserve and not split:
                updated.append(candidate)
                decisions.append(ContinuityDecision(
                    source_ids=[source.id], target_ids=[candidate.id],
                    reason=f"Agent replay: exact bytes or aligned byte similarity {similarity:.6f} >= 0.8"))
            else:
                spans = partition(after, track.target_bytes, track.boundary_bytes) if split else [(0, len(after))]
                replacements = [chunk(candidate.path, candidate.blob,
                                      mapper.product.blob(candidate.blob),
                                      candidate.start + a, candidate.start + b, str(uuid4()))
                                for a, b in spans]
                updated.extend(replacements)
                reason = ("Ambiguous cross-file identity: retire/create independently" if ambiguous else
                          f"Agent replay: {'split oversized edited range' if split else 'weak continuity evidence'}; "
                          f"byte similarity {similarity:.6f}; fresh IDs")
                if ambiguous:
                    decisions.extend([
                        ContinuityDecision(source_ids=[source.id], target_ids=[], reason=reason),
                        ContinuityDecision(source_ids=[], target_ids=[c.id for c in replacements], reason=reason)])
                else:
                    decisions.append(ContinuityDecision(source_ids=[source.id],
                                                         target_ids=[c.id for c in replacements], reason=reason))
            evidence.append({"path": candidate.path, "source_id": source.id,
                             "similarity": round(similarity, 6), "ambiguous": ambiguous,
                             "decision": "keep" if preserve and not split else "new-ids"})
        for change in changes:
            if change["after"] is None:
                decisions.append(ContinuityDecision(source_ids=[change["id"]], target_ids=[],
                                                     reason="No surviving proposed range at target checkpoint"))
    proposal.typed.chunks = updated
    return decisions, evidence, dict(Counter(c["kind"] for c in changes))


# tarav.breadcrumb b66e9b02809f
def main(argv=None):
    from tarav.l3.runtime import get_runtime

    get_runtime()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--every", type=int, default=10)
    parser.add_argument("--actor", help="Required for --apply; must begin with agent:")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and (not args.actor or not args.actor.startswith("agent:") or args.report is None):
        parser.error("--apply requires --actor agent:IDENTITY and --report PATH")
    mapper = ProductMapper(args.repo, args.repository_id, root=args.store)
    endpoint = mapper.product.exact(args.commit)
    latest = mapper.latest()
    checkpoints = mapper.product.checkpoints(endpoint, every=args.every,
                                             after=latest.typed.commit if latest else None)
    if not args.apply:
        print(json.dumps({"target": endpoint, "checkpoints": checkpoints}, indent=2))
        return 0
    if mapper.track() is None:
        mapper.create()
    report = {"policy": POLICY, "actor": args.actor, "repository_id": args.repository_id,
              "repository": str(mapper.product.root), "store": str(mapper.store.root),
              "target": endpoint, "every": args.every,
              "interpretation": "Agent-selected byte-evidence decisions; no user review claimed",
              "checkpoints": []}
    if args.report.exists():
        previous_report = json.loads(args.report.read_text())
        for key in ("policy", "actor", "repository_id", "target", "every", "store"):
            if previous_report[key] != report[key]:
                raise ValueError(f"Report resume contract changed: {key}")
        report = previous_report
    reported = {item["map"] for item in report["checkpoints"]}
    for identity in mapper.history():
        if identity not in reported:
            saved = mapper.load(identity)
            if saved.typed.actor != args.actor or POLICY not in saved.typed.reason:
                raise ValueError("Cannot absorb a map from a different actor or policy into this report")
            report["checkpoints"].append({"map": identity, **mapper.audit(saved),
                                          "decisions": len(saved.typed.decisions),
                                          "changes": dict(Counter(c["kind"] for c in mapper.changes(saved))),
                                          "alignment_evidence": [], "recovered_after_interruption": True})
    atomic_write_json(args.report, report)
    for commit in checkpoints:
        proposal = mapper.propose(commit)
        decisions, evidence, changes = decide(mapper, proposal)
        mapper.audit(proposal)
        result = mapper.confirm(proposal, decisions=decisions, actor=args.actor,
                                reason=f"Historical checkpoint exercise; {POLICY}; every {args.every} commits")
        verified = mapper.audit(mapper.load(result.typed.id))
        report["checkpoints"].append({"map": result.typed.id, **verified,
                                      "changes": changes, "decisions": len(decisions),
                                      "alignment_evidence": evidence})
        atomic_write_json(args.report, report)
        print(json.dumps({"checkpoint": len(report["checkpoints"]), **verified,
                          "changes": changes}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
