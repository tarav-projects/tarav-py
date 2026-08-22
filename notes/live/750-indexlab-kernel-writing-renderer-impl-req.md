# 750 — IndexLab Kernel.Writing renderer

## Impl.Abstract

- **Goal:** add a read-only IndexLab consumer that renders the current semantic projection as
  directly readable `Kernel.Writing` Markdown, with exact block selection.
- **Status:** ready for execution.
- **Scope:** projection retention of opaque line assertions, a pure renderer, the namespaced
  `tarav indexlab render` CLI, focused tests, the retained `dev-library/main` playground, and the
  IndexLab developer guide.
- **Out of scope:** writing a secondary surface, rendering record/support metadata into conceptual
  blocks, fuzzy search, label selection, a general assertion framework, or production `tarav index`
  migration.
- **Design authority:** the current user request and accepted proposal, `Kernel.Writing`,
  `Kernel.Block`, `Index.Block`, and the recording-kernel design recorded in notes 642 and 745.
- **User support:** Chatlas session
  `c9d44ac37e655c397de8ea8322baeffa87469c1ec55ae98532144bc5ff50ddb5`;
  message `fcd5f302…644406` requests general block/Index printing in Kernel.Writing format, and
  message `5eeda162…54688` authorizes autonomous development.

## Impl.Index

### Render.Boundary

- [DC] `Index.Record` remains the authoritative maintained surface; rendering never writes or
  changes records. Support: `fcd5f302…644406`.
- [DC] `SemanticProjection` remains the current block/line view; the renderer consumes that view
  rather than reimplementing record-fold semantics.
- [DC] the default rendering is Markdown-shaped `Kernel.Writing`: `****`, an `##` dotted-name
  heading, then ordered typed lines with their public labels.
- [CT] default output contains conceptual fundamentals only; record ids, support neighborhoods,
  Isoline/Isoblock ids, and assertions remain available through machine-readable commands.

### Assertion.Rendering

- [DC] a projected line retains the opaque assertions carried by its creating `line.capture`
  record so downstream consumers can interpret registered assertion types without making the
  recording kernel own their semantics.
- [DC] the renderer recognizes `index.line.type` as presentation sugar: one usable value renders
  as `[XX]`, absence as `[--]`, and conflicting values as `[??]` so malformed WIP state remains
  visible rather than invented or hidden.
- [RJ] the renderer does not infer a line type from wording and does not introduce a general
  assertion evaluator.

### CLI.Surface

- [DC] `tarav indexlab render --library <root> --workspace <selector>` renders every active block
  in deterministic projection order.
- [DC] `--block <name-or-id>` renders one exact active block; an absent or ambiguous selector
  fails closed.
- [DC] `tarav indexlab project` remains the machine-readable projection and `records` remains the
  authoritative record listing; `render` adds no parallel JSON contract.

## Execution.Plan

### Slice 1 — projection-backed renderer

- **Status:** planned.
- **RED:** tests require exact Kernel.Writing separators, headings, line order, type sugar, labels,
  empty-block behavior, and visible missing/conflicting type assertions.
- **GREEN:** retain opaque capture assertions on `ProjectedLine` and add a pure renderer over
  `SemanticProjection`.
- **Check:** focused projection/renderer tests.

### Slice 2 — CLI selection

- **Status:** planned.
- **RED:** CLI tests require whole-index rendering, exact name and Block.Id selection, and
  fail-closed absent/ambiguous selectors.
- **GREEN:** register `tarav indexlab render` using the same explicit library/workspace resolution
  as every other IndexLab reader.
- **Check:** focused IndexLab CLI tests and installed-command smoke runs against
  `var/indexlab/dev-library/main`.

### Slice 3 — closure

- **Status:** planned.
- Update the developer guide and this artifact with the landed surface and verification.
- Run focused IndexLab tests, architecture tests, Ruff, `git diff --check`, and the proportionate
  complete suite.
- Audit changed product surfaces; add no SKW annotation that merely restates self-evident code.

## Impl.Log

- **Execution authority:** `$tarav-hugentics --impl --dev --AUTO` at Chatlas message
  `5eeda162…54688`.
- **Pre-execution checkpoint:** pending.
- **Open-space decision:** initial scope deliberately stops at `render` plus `--block`; label
  selection and richer metadata views can be added when a concrete consumer requires them.
