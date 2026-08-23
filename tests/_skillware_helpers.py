from __future__ import annotations

import json
from pathlib import Path

SRC = """# agentos-index2 --ground

Intro prose.

## Copied

> $kw: --copy --from references/lib.skw.md#Alpha

- copied body line

> $kw. end

## Derived

> $kw: --derived --from references/lib.skw.md#Alpha
> --from Concept.One
> --intent reshape alpha for
> --cont this consumer

- derived body

> $kw. end

## Mixed

> $kw: --derived --from Concept.One --intent short

- derived part

> $kw. end

Hand tail prose.

## Hand

Plain hand section.
"""


BASE = """# base

## Root

- root line
"""


LIB = """# lib

## Alpha

- alpha one
- alpha two

## Beta

> $kw: --copy --from references/base.skw.md#Root

- stale beta copy

> $kw. end
"""


MOD = """# mod

Intro prose.

## Copied

> $kw: --copy --from references/lib.skw.md#Alpha

- stale copy

> $kw. end

## Chained

> $kw: --copy --from references/lib.skw.md#Beta

- stale chain

> $kw. end

## Derived

> $kw: --derived --from references/lib.skw.md#Alpha
> --from Concept.One
> --intent reshape alpha for this consumer

- derived solution

> $kw. end

Hand tail.
"""


DEPOT_CHAPTER = """> router

****

## Concept.One

- concept line
****
"""


DEPOT_ALIAS_CHAPTER = """> router

****

## Concept.One

- canonical line

### meta

- aliases: `Concept.Alias`, `Concept.Taken`
****

## Concept.Taken

- taken canonical line
****
"""


MOD_COMPILED = """# mod

Intro prose.

## Copied

- alpha one
- alpha two

## Chained

- root line

## Derived

- derived solution

Hand tail.
"""


def _write_skill(root: Path) -> Path:
    skill = root / "skill"
    src = skill / ".skw" / "src" / "references"
    src.mkdir(parents=True)
    (src / "base.skw.md").write_text(BASE, encoding="utf-8")
    (src / "lib.skw.md").write_text(LIB, encoding="utf-8")
    (src / "mod.skw.md").write_text(MOD, encoding="utf-8")
    (skill / ".skw" / "skw.json").write_text(json.dumps({}), encoding="utf-8")
    (skill / "references").mkdir()
    (skill / "references" / "hand.md").write_text(
        "# hand\n\nhand-owned\n", encoding="utf-8"
    )
    write_index(root)
    return skill


def _entry(report, target: str):
    return next(entry for entry in report.entries if str(entry.target) == target)


# --------------------------------------------------------------- Index records

#: The Index a Skillware test resolves `Dotted.Name` targets against. A block is
#: (address, lines) and a line is (Line.Type, text); an `alias` assertion carries
#: alternate names the way a captured `- aliases:` meta-line does.
DEPOT_BLOCKS = (("depot/design#Concept.One", (("CT", "concept line"),), ()),)

DEPOT_ALIAS_BLOCKS = (
    (
        "depot/design#Concept.One",
        (("CT", "canonical line"),),
        ("Concept.Alias", "Concept.Taken"),
    ),
    ("depot/design#Concept.Taken", (("CT", "taken canonical line"),), ()),
)


def index_records(blocks, *, prefix: str = "a") -> tuple:
    """Build the record stream a capture would write for these blocks.

    `prefix` keeps ids distinct when a test captures more than one batch.
    """
    from tarav.indexlab.model import (
        IndexRecord,
        Operation,
        RecordContext,
        SupportSet,
        TurnRef,
    )

    context = RecordContext(session="test", horizon=TurnRef(address="t", hash="0" * 16))
    records = []

    def add(operation: str, parameters: dict, assertions=()) -> None:
        # The store numbers a batch on append, so records arrive unnumbered.
        records.append(
            IndexRecord(
                id=f"rec_{prefix}_{len(records)}",
                ordinal=0,
                context=context,
                operation=Operation(type=operation, parameters=parameters),
                support=SupportSet(neighborhoods=()),
                assertions=assertions,
            )
        )

    for name, lines, aliases in blocks:
        block_id = f"blk_{prefix}_{len(records)}"
        add(
            "block.create",
            {"block_id": block_id, "isoblock_id": f"iso{block_id}", "name": name},
        )
        entries = [(code, text, ()) for code, text in lines]
        if aliases:
            rendered = ", ".join(f"`{alias}`" for alias in aliases)
            entries.append(("DF", f"aliases: {rendered}", tuple(aliases)))
        for code, text, alias_names in entries:
            line_id = f"lin_{prefix}_{len(records)}"
            assertion = {"line_type": code}
            if alias_names:
                assertion |= {"kind": "alias", "aliases": list(alias_names)}
            add(
                "line.capture",
                {
                    "line_id": line_id,
                    "isoline_id": f"iso{line_id}",
                    "block_id": block_id,
                    "label": f"^{line_id}",
                    "text": text,
                },
                (assertion,),
            )
    return tuple(records)


def write_index(root: Path, blocks=DEPOT_BLOCKS) -> Path:
    """Make `root` a project whose Index is a record workspace holding `blocks`.

    Calling it again replaces the corpus, so a test may state the Index it needs
    without first knowing what the shared skill fixture already wrote.
    """
    import shutil

    from tarav.indexlab import IndexLibrary, RecordStore

    library_root = root / "index-library"
    if library_root.exists():
        shutil.rmtree(library_root)
    library = IndexLibrary.initialize(library_root)
    workspace = library.create_workspace("test")
    RecordStore(workspace).append_many(index_records(blocks))

    # Only add the Index pointer: a caller may already have written the marker,
    # and its project_id is the identity the Wayfinder registry was keyed on.
    marker = root / ".tarav" / "project.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "class": "agentos.project",
        "schema_version": 1,
        "project_id": "00000000-0000-4000-8000-000000000000",
    }
    if marker.is_file():
        try:
            existing = json.loads(marker.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
        if isinstance(existing, dict):
            payload |= existing
    payload["index"] = {"library": "index-library", "workspace": "test"}
    marker.write_text(json.dumps(payload), encoding="utf-8")
    return library_root


def add_index_block(root: Path, name: str, lines, aliases=()) -> None:
    """Capture one more block into the test project's Index records."""
    from tarav.indexlab import IndexLibrary, RecordStore

    workspace = IndexLibrary.open(root / "index-library").resolve("test")
    store = RecordStore(workspace)
    prefix = f"n{len(store.list())}"
    store.append_many(
        index_records(((name, tuple(lines), tuple(aliases)),), prefix=prefix)
    )
