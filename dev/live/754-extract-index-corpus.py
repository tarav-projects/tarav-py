#!/usr/bin/env python3
# $kw: --from Migration.Current.Only --note [DC] one target schema; every legacy surface family is mapped onto Index.Record rather than preserved beside it --note [DC] conservation governs, so a line is never dropped for being ungrounded or unparseable and its defect travels into the workspace as reportable material --note [CT] coordinates are mapped and never invented, so an unresolved anchor produces an empty Support.Set rather than a plausible-looking one
"""Extract the whole Index corpus into `index-2208` as IndexLab `Index.Record`s.

This reads the frozen archive, never the live tree, so re-running it cannot drift with
whatever the working copies happen to say today.

**Conservation governs.** `643-anchory-to-line-records.py` already settled this for the
anchory migration and the reasoning carries: a line is never skipped for being incomplete.
An ungrounded line migrates with an empty `Support.Set`; an unaddressable line falls back to
the file it is written on, and then to a quarantine block. Every one of those is a loud
finding for the new linter rather than a silent omission. We are migrating a format, not
validating a corpus.

**Context and support are orthogonal**, which is what makes migrated records honest.
`Record.Context` bounds *derivation* — and the derivation event here is this migration pass,
not the 2026 chat the line came from. `Support.Set` bounds *authority* — and that is where
the original anchor's session and messages go. Writing the anchor's session into
`Record.Context` would claim these records were derived in a chat that never saw them.

**Isolines carry repetition.** The same anchor is frequently cited on several surfaces. That
is not a collision to resolve but the exact situation `Index.Isoline` exists for: one
semantic line with several projections. Occurrences share an `isoline_id` and take distinct
`Line.Id`s, so the repetition survives as structure instead of being deduplicated away.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
ARCHIVE = PROJECT / "index-archive-2208"
sys.path.insert(0, str(PROJECT / "tarav-py" / "src"))

from tarav.indexlab.model import (  # noqa: E402
    EvidenceNeighborhood,
    IndexRecord,
    MessageRef,
    Operation,
    RecordContext,
    SupportSet,
    TurnRef,
)

#: This migration is itself the derivation event for every record it writes.
MIGRATION_SESSION = "9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5"
MIGRATION_TAG = "index-2208"

#: Where a line lands when no legal address can be built from where it is written. A real
#: block that names no concept, so each one is a finding rather than a plausible-looking home.
QUARANTINE = "@quarantine#Unaddressed"

ANCHOR_RE = re.compile(r"\^([a-z]\d{8}-\d+[a-z]*)")
HEADING_RE = re.compile(r"^#{2,3}\s+(?P<concept>\S+)")
CHAPTER_RE = re.compile(r"^\d+-(?P<chapter>[a-z-]+)\.md$")
# A bullet that is an Index line: optionally typed, optionally anchored.
LINE_RE = re.compile(r"^\s*[-*]\s+(?:\[(?P<type>[A-Z]{2,6})\]\s*)?(?P<body>.+?)\s*$")
KW_RE = re.compile(r"\$kw:(?P<rest>.*)$")
# A note may carry a bracketed type of any length, or none at all; an untyped note is
# still an Index line and migrates as UNTYPED rather than being dropped.
NOTE_RE = re.compile(
    r"--note\s+(?:\[(?P<type>[A-Z]{2,6})\]\s*)?(?P<body>.*?)(?=\s+--(?:note|from|intent)\b|$)"
)


def digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- support


def load_anchor_support() -> dict[str, list[dict]]:
    """anchor -> its support members, from the archived anchory depot.

    The dossier is the only place an anchor's chat coordinates exist. Members are returned
    in the space they were written in; nothing is translated here.
    """
    index: dict[str, list[dict]] = {}
    root = ARCHIVE / "external" / "anchory"
    if not root.is_dir():
        print(f"WARNING: no archived anchory depot at {root}", file=sys.stderr)
        return index
    for shard in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(shard.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        for anchor, dossier in payload.items():
            if not isinstance(dossier, dict):
                continue
            members = (
                dossier.get("relationships", {}).get("support", {}).get("members", [])
            )
            if isinstance(members, list) and members:
                index[anchor] = members
    return index


def support_for(
    anchors: list[str], table: dict[str, list[dict]]
) -> tuple[SupportSet, Counter]:
    """One `Support.Set` per line, grouped into a neighborhood per session.

    An anchor that resolves to nothing contributes nothing. That leaves the line with an
    empty Support.Set, which is the honest record of an ungrounded line and exactly what the
    linter should be able to see.
    """
    counts: Counter = Counter()
    by_session: dict[str, list[MessageRef]] = defaultdict(list)
    for anchor in anchors:
        members = table.get(anchor)
        if not members:
            counts["anchor_unresolved"] += 1
            continue
        counts["anchor_resolved"] += 1
        for member in members:
            session = member.get("session")
            address = member.get("message_address")
            message_hash = member.get("message_hash")
            if not (session and address and message_hash):
                counts["member_incomplete"] += 1
                continue
            by_session[session].append(MessageRef(address=address, hash=message_hash))
    neighborhoods = tuple(
        EvidenceNeighborhood(session=session, grounding=tuple(refs))
        for session, refs in sorted(by_session.items())
    )
    return SupportSet(neighborhoods=neighborhoods), counts


# --------------------------------------------------------------------------- addressing


def scope_for(relative: Path, concept: str | None) -> str:
    """The line's address, derived from where it is written.

    A chapter line inside a skills depot is a block path; anything else is a locator naming
    the file, which is the honest address for a line that does not live in an index chapter.
    """
    parts = relative.parts
    chapter = CHAPTER_RE.match(relative.name)
    if chapter and concept and "skills" in parts:
        depot = parts[parts.index("skills") + 1]
        return f"{depot}/{chapter.group('chapter')}#{concept}"
    if concept:
        return f"@{relative.as_posix()}#{concept}"
    return f"@{relative.as_posix()}"


# --------------------------------------------------------------------------- reading


def read_markdown(root: Path) -> list[dict]:
    """Every Index line on every archived Markdown surface."""
    out: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        try:
            text = path.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        concept: str | None = None
        in_fence = False
        for number, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            heading = HEADING_RE.match(raw)
            if heading:
                concept = heading.group("concept").strip("`")
                continue
            match = LINE_RE.match(raw)
            if not match:
                continue
            body = match.group("body")
            anchors = ANCHOR_RE.findall(body)
            line_type = match.group("type")
            # An untyped, unanchored bullet is ordinary prose, not an Index line.
            if not line_type and not anchors:
                continue
            out.append(
                {
                    "surface": relative.as_posix(),
                    "line_number": number,
                    "concept": concept,
                    "type": line_type,
                    "text": ANCHOR_RE.sub("", body).strip(),
                    "anchors": anchors,
                    "origin": "markdown",
                }
            )
    return out


def read_code(root: Path) -> list[dict]:
    """Every `$kw` note — an Index line under `Natural.Placement`.

    `tarav-py/AGENTS.md` is explicit that an Index line written on code is an ordinary Index
    line and must receive a record through the same mechanics, so these are not a separate
    family here.
    """
    out: list[dict] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        try:
            text = path.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, raw in enumerate(text.splitlines(), start=1):
            found = KW_RE.search(raw)
            if not found:
                continue
            rest = found.group("rest")
            for note in NOTE_RE.finditer(rest):
                body = note.group("body")
                anchors = ANCHOR_RE.findall(body)
                out.append(
                    {
                        "surface": relative.as_posix(),
                        "line_number": number,
                        "concept": None,
                        "type": note.group("type"),
                        "text": ANCHOR_RE.sub("", body).strip(),
                        "anchors": anchors,
                        "origin": "skw",
                    }
                )
    return out


# --------------------------------------------------------------------------- records


def build(
    entries: list[dict],
    support_table: dict[str, list[dict]],
    *,
    labels_taken: set[str] | None = None,
    blocks_taken: dict[str, str] | None = None,
) -> tuple[list[IndexRecord], dict]:
    """Build records for `entries`.

    A delta into a live workspace must pass what that workspace already holds:
    labels are allocated with `~n` suffixes against the taken set, and a block
    already open is reused rather than created a second time.
    """
    horizon = TurnRef(
        address=f"{MIGRATION_TAG}:corpus", hash=digest(MIGRATION_TAG, "corpus")
    )
    context = RecordContext(session=MIGRATION_SESSION, horizon=horizon)

    stats: Counter = Counter()
    records: list[IndexRecord] = []
    blocks_seen: dict[str, str] = dict(blocks_taken or {})
    labels_used: set[str] = set(labels_taken or ())
    isolines: dict[str, str] = {}

    for entry in entries:
        relative = Path(entry["surface"])
        scope = scope_for(relative, entry["concept"])
        if len(scope) > 400 or "\n" in scope:
            scope = QUARANTINE
            stats["quarantined"] += 1

        block_id = blocks_seen.get(scope)
        if block_id is None:
            block_id = f"blk_{digest(scope)}"
            blocks_seen[scope] = block_id
            records.append(
                IndexRecord(
                    id=f"rec_{digest('block', scope)}",
                    ordinal=0,
                    context=context,
                    operation=Operation(
                        type="block.create",
                        parameters={
                            "block_id": block_id,
                            "isoblock_id": f"iso_{digest(scope)}",
                            "name": scope,
                        },
                    ),
                    support=SupportSet(neighborhoods=()),
                )
            )
            stats["blocks"] += 1

        anchors = entry["anchors"]
        support, counts = support_for(anchors, support_table)
        stats.update(counts)

        # The first anchor is the line's public selector, exactly as it is on the surface.
        # Repeated citation of one anchor is an Isoline, not a collision.
        if anchors:
            primary = anchors[0]
            isoline_id = isolines.setdefault(primary, f"isl_{digest(primary)}")
            label = f"^{primary}"
            if label in labels_used:
                stats["isoline_projection"] += 1
                suffix = 2
                while f"{label}~{suffix}" in labels_used:
                    suffix += 1
                label = f"{label}~{suffix}"
        else:
            # Synthetic, clearly namespaced, and ungrounded by construction.
            seed = digest(
                entry["surface"], str(entry["line_number"]), entry["text"][:120]
            )
            isoline_id = f"isl_{seed}"
            label = f"^m{MIGRATION_TAG[-4:]}-{seed}"
            stats["ungrounded"] += 1
        labels_used.add(label)

        text = entry["text"] or "(empty)"
        if not entry["text"]:
            stats["empty_body"] += 1

        line_id = f"ln_{digest(entry['surface'], str(entry['line_number']), label)}"
        assertion = {
            "line_type": entry["type"] or "UNTYPED",
            "origin": entry["origin"],
            "surface": entry["surface"],
            "surface_line": entry["line_number"],
            "migrated_by": MIGRATION_TAG,
        }
        if len(anchors) > 1:
            assertion["additional_anchors"] = anchors[1:]
        if not entry["type"]:
            stats["untyped"] += 1

        records.append(
            IndexRecord(
                id=f"rec_{digest('line', line_id)}",
                ordinal=0,
                context=context,
                operation=Operation(
                    type="line.capture",
                    parameters={
                        "line_id": line_id,
                        "isoline_id": isoline_id,
                        "block_id": block_id,
                        "label": label,
                        "text": text,
                    },
                ),
                support=support,
                assertions=(assertion,),
            )
        )
        stats["lines"] += 1

    return records, dict(stats)


def main() -> int:
    support_table = load_anchor_support()
    entries = read_markdown(ARCHIVE / "surfaces") + read_code(ARCHIVE / "code")
    # Deterministic order: the workspace assigns ordinals in the order records arrive.
    entries.sort(key=lambda item: (item["surface"], item["line_number"]))

    records, stats = build(entries, support_table)

    manifest = {
        "schema": "tarav.indexlab-capture-manifest.v1",
        "records": [record.to_dict() for record in records],
    }
    out = PROJECT / "tarav-py" / "dev" / "live" / "754-index-2208-manifest.json"
    out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", "utf-8")

    print(f"anchors with support   {len(support_table):>7}")
    print(f"index lines read       {len(entries):>7}")
    print(f"records built          {len(records):>7}")
    for key in sorted(stats):
        print(f"  {key:<22} {stats[key]:>7}")
    print(f"manifest -> {out.relative_to(PROJECT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
