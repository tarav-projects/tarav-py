# 904 — A link is declared; its Type checks the prose — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

A block of a Skillware source declares the links it holds, and the reading
graph uses only those declarations. Today the graph also parses the prose of
every block and raises `Tarav.SKW.POI.UnannotatedOutputLink` for each
Markdown link without a declaration, and a link declaration also writes its
own prose through a `{{skw:link-N}}` slot. Both go.

1. The reading graph never reads prose. The parsing and the Type
   `UnannotatedOutputLink` are deleted.
2. A link declaration (`Tarav.SKW.Reading.Link` and its subtypes) loses
   `slot` and `caption`: it no longer writes prose.
3. A link may hold a typed prose part, `prose`, which says how the link
   appears in the block's text and owns the checks of that. A link without
   one checks nothing. The first part is `Tarav.SKW.Reading.MarkdownProse`: the
   block's text holds a Markdown link to the declared target.
4. One check, `Tarav.SKW.Check.LinkProse`, runs the prose parts of a package
   and raises `Tarav.SKW.POI.MissingMarkdownLink` where the text lacks the
   link.
5. The 65 link slots of `tarav-md/skills/tarav-hugentics` and
   `tarav-md/skills/tarav-pkg` become the literal Markdown they compiled to,
   and each of those links gets a `MarkdownProse` part.

Non-goals: `SkillLink` and the `slot` of `IncludesBlock` (blocks inside
blocks: another way to build output, not decided); links to targets outside
the package; the packaging checks `UnbundledLink` and
`UndeclaredConsumerLink`, which read the compiled files for what the package
ships, not for the reading graph.

## Design narrative

### User decisions

The user pasted an open `UnannotatedOutputLink` action of `tarav-hugentics`
and asked for an explanation from first principles.
<!-- tarav.breadcrumb d044e0f35e81 -->

The user did not like the model of two kinds of link, declared and authored,
and asked for its grounding in user input.
<!-- tarav.breadcrumb 38df70dbc6f4 -->

A link is declared only: the block declares that it contains a link. Links
can be typed, and a link Type can carry a check that validates part of that
on the prose. The base Type tests nothing; a specific Type does. The SKW
system does not care about the prose and trusts the declaration; the
maintainers care about the prose actually holding the link.
<!-- tarav.breadcrumb 1eae22b407b7 -->

Most relationships between SKW blocks are declared, to keep the model
simple: a block declares, the system checks that the declarations make sense
with each other, and other mechanisms may later check or score the
declarations.
<!-- tarav.breadcrumb 5c58f87c5650 -->

The user confirmed the three layers below. How a link interacts with the
prose is the link's concern; it works by declaring checks and raising POIs.
There can be several link Types, each with its own mechanism, starting with
one that checks that `[text](target)` exists in the prose.
<!-- tarav.breadcrumb f2e6a596ff9b -->

`SkillLink`, a block whose whole purpose is to be a link, is another way to
build output, like blocks inside blocks in LaTeX. It is not decided; keep the
declare-only model for now.
<!-- tarav.breadcrumb b1959e36a841 -->

Composition, not subtypes, for the prose part; keep `SkillLink`; write the
request and execute it.
<!-- tarav.breadcrumb 866d400ed2e9 -->

### The three layers

1. Declarations: a block states its relations to other blocks. They are
   claims.
2. Consistency: the SKW system checks only that the declarations fit
   together: targets exist, required context is delivered on every path, no
   cycles, no unreachable blocks.
3. Verification: separate checks of whether a declaration matches the prose.
   Layers 1 and 2 never depend on it. A prose part belongs here.

### Current behavior (inspected)

- `SkillReadingGraph.__init__` (`l1/skw/loading.py`) parses the content of
  every bound block with `markdown_it` and reports `UnannotatedOutputLink`
  for each link, declared or not; the comment says "Conformance signal only.
  Parsed links never become edges."
- `ReadingLink.RecordInterface` (`l1/skw/code/reading.py`) has `entry`,
  `slot` and `caption`. `render_block()` replaces `{{skw:<slot>}}` with
  `[caption](path)`, where the path is the target's product relative to the
  block's product, plus `#skw-<Ship>` when the target is not the first block
  of its file. `IncludesBlock` uses the same slot to insert a block.
- `render_block()` also writes `<a id="skw-<Ship>">` before a block that a
  declared link targets. That anchor stays: it is generated from a
  declaration, not read from prose.
- The grounding found: request 828 ("consume explicit declarations
  uniformly, without inferring semantics from headings or prose"; targets
  require only a `TaravEntity`). No user turn grounds the prose parsing or
  the slot; both predate request 825.
- The open action of this discussion is a link to
  `../../tarav-pkg/tarav-diagram.md` typed into the `introduction` block of
  `references/capture.skw.json`. After this request nothing reports it.

### Proposals of the agent

**Prose part.** `ReadingLink.prose` holds one `LinkProse` record, or none.
`LinkProse` (`Tarav.SKW.Reading.LinkProse`) is the base and checks nothing.
`MarkdownProse` (`Tarav.SKW.Reading.MarkdownProse`) has no fields. Given the
block's text and the expected href, it reports a finding when no Markdown
link in the text has that href.

**Expected href.** The graph computes it as the slot rendering did: the
target's product relative to the block's product, plus the anchor when the
target is not the first block of its file. The destination is the link's
entry when it has one, otherwise the target block. Hrefs compare after
percent-decoding.

**Check and POI.** `Tarav.SKW.Check.LinkProse` (`l2/skw/reading_checks.py`)
joins the package's reading checks. `MissingMarkdownLink` states "A declared
Markdown link is missing from the text of its block". Its situation is what
the check uses: `{"project": <package root>, "block": <block Ship>,
"href": <expected href>}`. No package snapshot. It is not blessable: the
declaration or the text is wrong.

**Migration.** A one-off script, run once with the current code before the
change, replaces each slot with the text it compiled to and moves the
declaration from `slot`/`caption` to `prose: MarkdownProse`. Every product
then compiles byte for byte the same.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `skillware.md`, `batchy-skills.md`,
`daily/2026-10-14.md`. Supporting chat: session `abd0372d` above.
Capture status: done (`skillware.md`, section "Links are declared; a prose
part checks the text (904)"; daily 2026-10-14).

## Execution.Plan

1. Migrate the sources of `tarav-hugentics` and `tarav-pkg` with the current
   code: slots become literal links; `slot`/`caption` become `prose`.
2. `l1/skw/code/reading.py`: `LinkProse`, `MarkdownProse`, `ReadingLink.prose`;
   `slot` and `caption` removed.
3. `l1/skw/loading.py`: no prose parsing; link slots no longer rendered;
   `prose_findings()`. `l1/skw/pois.py`: `UnannotatedOutputLink` deleted,
   `MissingMarkdownLink` added.
4. `l2/skw/reading_checks.py`: `LinkProseCheck`.
5. Tests; `tarav-hugentics/AGENTS.md` link guidance; compile both packages;
   whole `tests/`, Ruff, a real status run.
6. Breadcrumbs on the implemented surfaces; Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-14.
- Migration: 48 links in `tarav-hugentics` and 17 in `tarav-pkg` (14 and 3
  source files) became literal Markdown with a `MarkdownProse` part; the one
  remaining slot is an `IncludesBlock` that inserts the `SkillLink` block
  into `SKILL.md`, a non-goal. No compiled file changed.
- A trial on a copy of the skills first suggested that several
  `OutputChanged` and `StaleContext` would disappear. That copy skipped the
  freshness checks; the real run shows otherwise (below).
- Code as planned. `LinkProse` and `MarkdownProse` are registered with the
  other reading record Types (`LINK_PROSE_TYPES`, in the SKW registry and the
  runtime). `SkillReadingGraph.href()` is shared by `prose_findings()` and
  `SkillLink`. Anchors are still written before a block a declared link
  targets, only for packages with a loading file, as before.
- Test: `test_a_declared_link_is_checked_only_by_its_prose_part`.
- Checks: Ruff clean; default run 296 passed; the whole `tests/` folder 438
  passed, 1 failed (`test_scoped_lines`, another agent's area).
- Real run, `tarav status --project .` at the root: both
  `UnannotatedOutputLink` actions closed as gone; no `MissingMarkdownLink`,
  so all 65 migrated links are found in their text. One new `OutputChanged`:
  `wiki-capture.skw.json: introduction`, whose recorded generation output
  still holds its slot. The `StaleContext` and `OutputChanged` actions closed
  and reopened, because their situation holds the package snapshot. Open:
  19 (14 `StaleContext`, 5 `OutputChanged`), was 20. A second run changed
  nothing. A closed action of the deleted Type still opens with
  `tarav context`.
- Docs: `tarav-md/skills/tarav-hugentics/AGENTS.md` link guidance.
- Breadcrumbs: submitted and audited ok on `l1/skw/code/reading.py`,
  `l1/skw/loading.py`, `l1/skw/pois.py`, `l2/skw/reading_checks.py`,
  `tests/test_skw_poi.py`, the hugentics `AGENTS.md` and this note.
- Not done: scoped evidence commits; the user commits on their word, and
  these files share hunks with other uncommitted work.
