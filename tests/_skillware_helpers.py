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
    (skill / ".skw" / "skw.json").write_text(
        json.dumps({"depots": ["../depot"]}), encoding="utf-8"
    )
    (skill / "references").mkdir()
    (skill / "references" / "hand.md").write_text(
        "# hand\n\nhand-owned\n", encoding="utf-8"
    )
    depot = root / "depot"
    (depot / "design").mkdir(parents=True)
    (depot / "000-INDEX.md").write_text(
        "- `design/100-design.md` — Concept.One\n", encoding="utf-8"
    )
    (depot / "design" / "100-design.md").write_text(DEPOT_CHAPTER, encoding="utf-8")
    return skill


def _entry(report, target: str):
    return next(entry for entry in report.entries if str(entry.target) == target)
