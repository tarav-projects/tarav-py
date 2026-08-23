# 760 — Disconnecting the code from the Markdown Index surface

Session `9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5`.

**Goal.** The Index is a collection of `Index.Record`s. Markdown is a
`Index.Secondary.Surface`, disconnected now and reconnected later. Every line we
see as an Index line lives in the proper workspace, and all tarav code reads
records and nothing else.

Constraint carried through the whole pass: **no legacy code, no regression
tests.** Where a thing was superseded it was deleted, not adapted beside its
replacement. Where a test pinned removed behaviour it went with the behaviour.

## The corpus is a superset of the surface

`754` read the frozen archive so it could not drift, which also froze it at one
moment while other agents kept landing lines. Two catch-up passes closed that:

- `758-index-corpus-delta.py` — 412 lines / 98 blocks written after the freeze.
  All 412 are ungrounded and carry an empty `Support.Set`; that is honest rather
  than a lookup failure, because none of them carries an anchor at all, which is
  what the grounding freeze predicts. Content identity is `(block address, line
  text)`: a surface line number moves whenever anyone edits the file above it,
  so an ordinal-keyed delta would report churn as drift.
- `759-capture-index-aliases.py` — the one family the migration could not see.
  The `754` line test required a `Line.Type` code or an anchor, and an
  `- aliases:` meta-line carries neither, while `Dotted.Name` locator resolution
  reads exactly those lines. They sit under a `### meta` subsection inside a
  `##` block, so they attribute to the enclosing block heading. 19 of the 52
  found belong to a real Index block; the other 33 are Batchy router rows and
  notes whose blocks were never Index blocks.

Corpus now: **1,170 blocks / 4,406 lines / 5,576 records.** Re-running the delta
reports zero.

## One reader

`tarav.indexlab.IndexResolver` folds the record stream once and answers the
three questions consumers actually asked Markdown: what blocks exist, what does
this block say, what does this citation refer to. A consumer that folded for
itself would hold a private projection able to disagree with the linter's.

`.tarav/project.json` names the library and workspace. Every repo hosting
skills now carries that pointer.

Decisions worth keeping:

- A bare `Dotted.Name` prefers a chapter block over one written on a product
  surface — the chapter block is the concept's declared home.
- An alias colliding with a canonical concept loses to it: a name that resolves
  two ways is worse than an alias that does not resolve.
- A citation carries no `~n` occurrence suffix, so it resolves to the isoline
  and returns *every* projection of that one semantic line.
- An alias declaration states a name *for* a block, not content *of* it, so it
  stays in the corpus and out of any materialized body.
- `Line.Type` lives on a record assertion. Two shapes existed; the renderer's
  `index.line.type` had zero records behind it and the migration's `line_type`
  had all of them, so they unified on the one carrying the data — keeping the
  renderer's absent (`--`) / conflicting (`??`) distinction.

## What was deleted

| | LOC |
|---|---|
| `tarav.index` — the production Index runtime and CLI | 7,498 |
| the `Chat.Index` projection family (both lossless halves, reconciliation) | ~4,200 |
| `index_model`'s Markdown parser, nodes, anchors, stats | ~840 |
| `index_depot_deps` and the depot-visibility layer | ~120 |

Also gone: the `depots` key in `skw.json`. Concept resolution is no longer
configured, because one workspace holds the Index whole — so a name defined by
two blocks is a *reported collision*, never a lookup order.

`index_model` drops from 36 call sites across 7 subsystems to 10, and every
survivor is line grammar: the written form of an Index line and the identity
hashes Chatlas dossiers assert over the `Line.Type + body + anchor` triplet. A
line still has a syntax wherever one is written or cited. That is not the Index.

## Repointed, not adapted

Wayfinder `index.block` resolution, Skillware managed-block discovery, the
`Dotted.Name` locator, POI class discovery (`<depot>/poi#<Class>` blocks), the
`IndexSurfaceProvider` behind every `$kw --from`, and Chatlas anchor
reattachment — which was the last Markdown scan in the tree, and now resolves a
citation to records and reconstitutes each line's written form from its
`Line.Type` and text.

An Index block resolves to record coordinates and carries no path or line range:
the record stream is the `Index.Primary.Surface`, and a file offset would name a
projection instead of the thing itself.

## The layering had to move

Pointing three subsystems at the kernel closed three import cycles, all tracing
to IndexLab depending on things that should depend on it. The kernel now
declares ports and other subsystems provide adapters:

- `indexlab/touch.py` keeps the `UserTouchSource` port; `ChatlasTouchSource`
  moved to `chatlas.lossless`, the layer that owns reading the chat store.
- The IndexLab CLI takes a touch-source factory injected by the composition root.
- `poi/discovery.py` and `wayfinder/index_blocks.py` moved to `skillware`, the
  one subsystem already sitting on all three.

Resulting edges: `wayfinder -> _core`; `indexlab -> _core, bloberia, poi`;
`poi -> _core, bloberia, index_model, wayfinder`; `skillware -> all three`.

## State

- **1,973 tests pass**, ruff clean, `skw check` 0 diagnostics in both projects.
- `skw check` runs entirely off records: 467 advisories in `tarav-py`, of which
  **235 are `--from` targets naming a concept the corpus does not declare.**
  That is the finding the migration existed to expose, not a defect in the cut.
- Conservation holds. The 753 freeze had captured only files carrying Index
  lines, so the deleted tests and two historical dossier-migration scripts were
  archived into `index-archive-2208` *before* leaving the tree.

## Blocked, and named as blocked

Hugentics no longer routes through `tarav index ...`. Where a record equivalent
exists the workflow names it. Where none exists the skill says so:

> Landing is blocked. The `Capture.Manifest` pipeline ran on the Markdown
> realization and was removed with it. The kernel captures records but has no
> equivalent for anchor registration, gate evidence, or the landing audit.

Instructing an agent to run a dead command, or to hand-substitute the missing
steps, is worse than naming the gap.

## Open

1. **Record-side capture** — anchor registration, gate evidence, landing audit.
   Until it lands, every write workflow stops at an approved manifest.
2. **Land the 642 model into the index.** `Index.Primary.Surface` resolves only
   to a block in note 642; ten kernel terms are declared nowhere. This is why
   235 `--from` targets dangle.
3. **The migration horizon is unresolvable by construction** — 5,576 blocked
   `context-resolves` checks. The kernel needs a way to say "this context is a
   migration, not a chat turn."
4. Reconnecting Markdown as a real `Index.Secondary.Surface` — a renderer exists
   (`render_kernel_writing`); a writer does not.
