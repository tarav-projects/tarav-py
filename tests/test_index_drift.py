"""Index backend on the shared linter core (Impl.Req 700, slice 3).

Proves the extensibility point: the index depot plugs into the surface-agnostic
`agentos.skwlint` engine through `IndexSurfaceProvider`, and the edge-free
`dangling_mention_findings` fires exactly on a mention whose concept was
removed. Runs over a controlled fixture where every concept is a heading, so
the headings-only resolver is complete — the real-index resolver gap is
deliberately out of scope (see the Impl.Req Impl.Log).
"""

from pathlib import Path

from agentos.index.drift import IndexSurfaceProvider, index_dangling_mentions
from agentos.skwlint import ADVISORY, SurfaceProvider, dangling_mention_findings


def _write_depot(root: Path, design: str) -> Path:
    (root / "design").mkdir(parents=True)
    (root / "000-INDEX.md").write_text(
        "# INDEX\n\n- `design/100-design.md` — concepts\n", encoding="utf-8"
    )
    (root / "design" / "100-design.md").write_text(design, encoding="utf-8")
    return root


CLEAN = """# design

****

## Foo.Bar

- [DF] `Foo.Bar` is a thing that leans on `Baz.Qux`

****

## Baz.Qux

- [DF] `Baz.Qux` is another thing
"""

# same references, but the `Baz.Qux` concept block was renamed away
DRIFTED = """# design

****

## Foo.Bar

- [DF] `Foo.Bar` is a thing that leans on `Baz.Qux`

****

## Baz.Renamed

- [DF] `Baz.Renamed` is the renamed thing
"""


def test_index_backend_satisfies_surface_provider(tmp_path: Path) -> None:
    assert issubclass(IndexSurfaceProvider, SurfaceProvider)
    depot = _write_depot(tmp_path / "d", CLEAN)
    provider = IndexSurfaceProvider(depot)
    assert provider.declared_edges() == (set(), set())
    assert {"Foo.Bar", "Baz.Qux"} <= provider.mentions()


def test_clean_index_has_no_dangling_mentions(tmp_path: Path) -> None:
    depot = _write_depot(tmp_path / "d", CLEAN)
    assert index_dangling_mentions(depot) == []


def test_removed_concept_raises_a_dangling_mention(tmp_path: Path) -> None:
    depot = _write_depot(tmp_path / "d", DRIFTED)
    findings = index_dangling_mentions(depot)
    kinds = {(f.kind, f.key) for f in findings}
    assert ("dangling-mention", "Baz.Qux") in kinds
    assert all(f.severity == ADVISORY for f in findings)


def test_core_dangling_mention_is_surface_agnostic() -> None:
    findings = dangling_mention_findings(
        Path("s"),
        {"Here.Now": "hash", "Gone.Away": "unresolved:no concept block"},
    )
    assert [f.key for f in findings] == ["Gone.Away"]
    assert findings[0].kind == "dangling-mention"


# an inline-defined concept: `Child.Inline` is defined by a [DF] line inside
# Parent.Block, without a block of its own, and referenced from another block.
INLINE_DEFINED = """# design

****

## Parent.Block

- [DF] `Parent.Block` is the parent
- [DF] `Child.Inline` is a concept defined inside the parent block

****

## Other.Block

- [DF] `Other.Block` leans on `Child.Inline`
"""

# same, but the inline definition line was removed — the reference dangles
INLINE_REMOVED = """# design

****

## Parent.Block

- [DF] `Parent.Block` is the parent

****

## Other.Block

- [DF] `Other.Block` leans on `Child.Inline`
"""


def test_inline_definition_resolves(tmp_path: Path) -> None:
    # a concept defined by a [DF] line inside another block resolves — no
    # false dangling on a reference to it (Impl.Req 700 follow-up).
    depot = _write_depot(tmp_path / "d", INLINE_DEFINED)
    provider = IndexSurfaceProvider(depot)
    assert "Child.Inline" in provider.resolve({"Child.Inline"})
    assert not provider.resolve({"Child.Inline"})["Child.Inline"].startswith("unresolved:")
    assert index_dangling_mentions(depot) == []


def test_removing_an_inline_definition_drifts(tmp_path: Path) -> None:
    depot = _write_depot(tmp_path / "d", INLINE_REMOVED)
    findings = index_dangling_mentions(depot)
    assert ("dangling-mention", "Child.Inline") in {(f.kind, f.key) for f in findings}


def test_block_heading_is_not_shadowed_by_inline_pass(tmp_path: Path) -> None:
    # the block's own first [DF] names the heading; headings still resolve.
    depot = _write_depot(tmp_path / "d", INLINE_DEFINED)
    provider = IndexSurfaceProvider(depot)
    res = provider.resolve({"Parent.Block", "Other.Block"})
    assert all(not v.startswith("unresolved:") for v in res.values())


ALIASED = """# design

****

## Real.Concept

- [DF] `Real.Concept` is the thing that `Alt.Name` also names

### meta

- aliases: `Alt.Name`
"""


def test_declared_alias_resolves(tmp_path: Path) -> None:
    # a concept's `### meta / - aliases:` name resolves like the concept itself.
    depot = _write_depot(tmp_path / "d", ALIASED)
    provider = IndexSurfaceProvider(depot)
    res = provider.resolve({"Real.Concept", "Alt.Name"})
    assert not res["Alt.Name"].startswith("unresolved:")


def test_cross_depot_resolution(tmp_path: Path) -> None:
    # a mention resolving to a concept defined in another engaged depot is not
    # dangling once that depot is engaged.
    home = _write_depot(
        tmp_path / "home",
        "# design\n\n****\n\n## Home.Concept\n\n- [DF] `Home.Concept` leans on `Foreign.Concept`\n",
    )
    other = _write_depot(
        tmp_path / "other",
        "# design\n\n****\n\n## Foreign.Concept\n\n- [DF] `Foreign.Concept` is defined elsewhere\n",
    )
    assert index_dangling_mentions(home) != []  # dangling without the other depot
    findings = index_dangling_mentions(home, engaged_depots=(other,))
    assert "Foreign.Concept" not in {f.key for f in findings}
