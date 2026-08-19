# $kw: --from Depot.Import --note [DC] a tarav1 depot is read and copied, never moved; tarav1 stays untouched until the cut
# $kw: --from Depot.Import --note [DC] imported material lands on the agent side because tarav1's review evidence is ^c anchors no active workflow resolves
"""Bringing a legacy-layout depot into the current layout.

tarav1 lays a depot out as `<depot>/design/NNN-design.md`, with `appendix/`, `agendix/`, and
`issues/` beside it. the current design lays it out as `<depot>/homes/<home>/{chapters,appendix}/`. The
importer reads the first and writes the second — a **copy**, so tarav1 keeps working until the
cut, and a one-time translation, so the system converges on one layout instead of carrying two.

Every kernel line becomes a record. Two things it deliberately does not do:

- **it does not ground anything.** tarav1's support is `^c` anchors, which no active workflow
  resolves; inventing grounding for them would be the fabrication this system exists to
  prevent. Imported lines arrive as `Index.Presumption` and say so.
- **it does not confer standing.** Material lands on the agent side. That tarav1 reviewed a
  line is not evidence this design can check, so promotion to a `HEAD.Surface` stays a gated act
  taken afterwards, line by line.

Labels are preserved where they do not collide, because a legacy label is a true fact about
where a line came from and `anchor-legacy-sigil` should be able to see it. A collision is
resolved by minting a fresh label, which costs nothing: the label is a public id and the
record's identity does not follow it.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import Geography, TaravIndexError
from .record.model import LineRecord
from .record.store import IndexStore, Tier
from .scope import block_scope
from .surfaces import read_block_lines


class ImportError_(TaravIndexError):
    """Raised when a depot cannot be read."""


@dataclass
class ImportReport:
    depot: str
    home: str
    chapters: list[str] = field(default_factory=list)
    recorded: list[LineRecord] = field(default_factory=list)
    relabelled: list[tuple[str, str]] = field(default_factory=list)
    unlabelled: int = 0

    @property
    def lines(self) -> int:
        return len(self.recorded)


def tarav1_chapters(depot_root: Path, chapter: str = "design") -> list[Path]:
    """The tarav1 chapter files for one chapter name, in file order."""

    directory = depot_root / chapter
    if not directory.is_dir():
        raise ImportError_(f"{depot_root} has no {chapter}/ chapter directory")
    return sorted(directory.glob("*.md"))


def import_depot(
    geo: Geography,
    depot_root: Path,
    *,
    depot: str | None = None,
    home: str = "agent",
    chapter: str = "design",
    tier: str = Tier.PROJECT,
) -> ImportReport:
    """Copy a legacy depot's chapter notes into the current layout and record every line."""

    name = depot or depot_root.name
    report = ImportReport(depot=name, home=home)
    store = IndexStore(geo)
    taken = {r.line.label for r in store.all() if r.line.label}

    target_dir = geo.project_root / "skills" / name / "homes" / home / "chapters"
    target_dir.mkdir(parents=True, exist_ok=True)

    for source in tarav1_chapters(depot_root, chapter):
        target = target_dir / source.name
        shutil.copyfile(source, target)
        surface = str(target.relative_to(geo.project_root))
        report.chapters.append(surface)

        for line in read_block_lines(target, surface, kind="chapter"):
            record = LineRecord.create(
                block_scope(name, chapter, line.scope.concept or ""),
                line.line_type,
                line.body,
            )
            label = line.label
            if label is None:
                report.unlabelled += 1
                record = store.mint_label(store.put(record, tier=tier), tier=tier)
            elif label in taken:
                minted = store.mint_label(store.put(record, tier=tier), tier=tier)
                report.relabelled.append((label, str(minted.line.label)))
                _replace_label(target, label, str(minted.line.label))
                record = minted
            else:
                record = store.put(record.relabel(label), tier=tier)
            taken.add(str(record.line.label))
            report.recorded.append(record)

    return report


def _replace_label(surface: Path, old: str, new: str) -> None:
    """Rewrite one label on the copied note so it matches its record."""

    text = surface.read_text("utf-8")
    surface.write_text(text.replace(old, new), encoding="utf-8")


__all__ = ["ImportError_", "ImportReport", "import_depot", "tarav1_chapters"]
