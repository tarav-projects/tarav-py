# Native Surface Consumers — Impl.Req

## Impl.Abstract

- Status: ready for execution.
- Scope: complete the first Markdown-native normalization adoption pass by removing residual Skillware scans, strengthening fenced-region facts, and making Markdown Blocks, Index parsing, and the Chatlas Index audit consume the native Markdown model at their parser or adapter boundaries.
- Source authority: the autonomous implementation sequence authorized by ^c20260812-7u.
- Baseline: the uncommitted completed native-surface implementation represented by `notes/live/726-native-surface-normal-models-impl-req.md` and the current worktree.
- Core constraint: `agentos.surfaces` owns only host-native facts required by current consumers; subsystem syntax and lint policy remain in subsystem models.
- Out of scope: generic Markdown sections, YAML frontmatter, a universal parser, Python AST expansion, direct native-model dependencies from linters, and unrelated raw-text operations.

## Impl.Index

### Markdown.Fence.Facts

- The native Markdown normalizer must distinguish a valid opener from a valid closer using marker character, opening run length, closing run length, and trailing-content rules.
- A fenced region retains its source span even when unclosed, allowing consumers to identify inert lines and diagnose incomplete input without reimplementing fence state.
- Heading recognition occurs only outside fenced regions and preserves source coordinates suitable for domain adapters.

### Surface.Consumer.Boundary

- A subsystem parser or adapter may consume `MarkdownNormalModel` and produce its existing domain model.
- Linters, Wayfinder, and reconciliation code continue consuming their domain `Floor.Model`; they do not depend directly on native Markdown details.
- Subsystem-only syntax such as Index kernel lines, Markdown block separators, Skillware callouts, and Chatlas anchors stays outside `agentos.surfaces`.

### Incremental.Model.Growth

- Add only fence and heading behavior required by the consumers in this request.
- Do not add section or frontmatter models until a concrete migration needs them.
- Preserve existing public subsystem output and POI identities while replacing duplicated raw scanning.

## Impl.Agendix

- touched: ^c20260812-7u — autonomous design and execution authority for the ordered migration.
- touched: `index://agentos-pkg/Floor.Model` — downstream tools consume a dependable model rather than the mechanism that produced it.
- touched: `index://agentos-pkg/Normalization.Pipeline` — raw Markdown is normalized once before subsystem interpretation.
- touched: `index://agentos-pkg/Skw.Backend` — Skillware remains an adapter-backed consumer rather than leaking its syntax into the native model.

## Execution.Plan

### Slice 1 — Accurate native Markdown facts

- Status: pending.
- Add boundary tests for mismatched, short, and trailing-content fence candidates plus normalized ATX heading text.
- Enrich the minimal fence representation only enough to express correct region boundaries.
- Check: native-surface and Skillware adapter/parser tests pass.

### Slice 2 — Complete Skillware adoption

- Status: pending.
- Replace `_region_body` and legacy-callout fence toggles with native Markdown normalization while leaving region and callout semantics in Skillware.
- Check: focused Skillware parser and build-operation tests pass.

### Slice 3 — Migrate Markdown Blocks

- Status: pending.
- Normalize each scanned Markdown file once and derive headings, fenced exclusion, and unclosed-fence state from the native model.
- Keep separator, block, preamble, and lint semantics within `agentos.stdlib.mdblocks`.
- Check: Markdown Blocks and POI adapter tests preserve their public results.

### Slice 4 — Adapt Index parsing

- Status: pending.
- Make the Index parser consume native lines, headings, and fenced regions while retaining all Index-specific node construction.
- Keep `IndexDocument` as the model consumed by linters, Wayfinder, Skillware resolution, and Chatlas reconciliation.
- Check: Index parser, linter, Wayfinder, and reconciliation tests pass.

### Slice 5 — Remove the remaining relevant Chatlas fence scan

- Status: pending.
- Make Chatlas Index-audit line extraction use the native fenced-region facts without moving anchor semantics into `agentos.surfaces`.
- Check: focused Chatlas Index-audit tests pass.

### Slice 6 — Closure

- Status: pending.
- Update architecture guidance for the new consumers.
- Confirm section/frontmatter work remains deferred.
- Run focused tests, the full suite, Ruff, Skillware checks, and diff validation.

## Impl.Log

- 2026-08-12 — Autonomous design and execution authority registered as ^c20260812-7u.
- 2026-08-12 — The migration targets parser and adapter boundaries; direct linter coupling to native models is explicitly rejected.
- 2026-08-12 — Sections and frontmatter remain deferred because this execution has no concrete consumer requiring those native facts.
