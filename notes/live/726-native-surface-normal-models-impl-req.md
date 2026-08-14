# Native Surface Normal Models — Impl.Req

## Impl.Abstract

- Status: implemented and verified.
- Scope: introduce deliberately small Python and Markdown normal models, adapt them into one shared Skillware carrier model, and migrate existing Skillware parsing and code-policy consumers onto those layers.
- Source authority: implement the layered surface-normalization system authorized by ^c20260812-0u.
- Baseline checkpoint: `1f31411`.
- Core constraint: a native normal model grows only when at least one current subsystem needs the new fact.
- Out of scope: general-purpose language parsers, semantic Python AST modeling, Markdown rendering, and native models that know Skillware concepts.

## Impl.Index

### Native.Surface.Model

- `agentos.surfaces` owns host-language normalization and tiny shared location/diagnostic primitives.
- Python normalization owns tokenizer-confirmed comments, recognized external directives, and scanner diagnostics.
- Markdown normalization owns source lines, headings, and fenced regions needed by current consumers.
- Native models never import or recognize Skillware.

### Skw.Surface.Model

- Skillware adapters consume native normal models and emit a common carrier model.
- Shared Skillware parsing consumes that model rather than raw Python or Markdown text.
- Existing raw-text parser entrypoints remain composition facades over native normalization, adaptation, and shared parsing.

### Comment.Leak.Policy

- Recognized Python directives for external tools are classified by a conservative, named allowlist in the Python normalizer.
- External directives are not `Non.Skw.Annotation` and require no Skillware blessing.
- Every other tokenizer-confirmed Python comment outside Skillware machinery remains a strict `Non.Skw.Annotation` POI.
- Exact blessings remain available for exceptional comments, but obsolete directive blessings are removed.

## Impl.Agendix

- touched: ^c20260812-0u — execution authority and architecture acceptance.
- touched: `index://tarav-pkg/Floor.Model` — consumers operate on normalized models.
- touched: `index://tarav-pkg/Normalization.Pipeline` — raw surfaces become native normal models before subsystem adaptation.
- touched: `index://tarav-pkg/Skw.Backend` — host-specific adapters produce the common Skillware carrier representation.
- touched: `index://tarav-pkg/Non.Skw.Annotation` — only unclassified host comments become leak-policy POIs.

## Execution.Plan

### Slice 1 — Native surface layer

- Status: completed.
- Add shared spans and diagnostics.
- Add minimal Python and Markdown models and normalizers with isolated tests.

### Slice 2 — Common Skillware carrier

- Status: completed.
- Add a common carrier model plus Python and Markdown adapters.
- Refactor the shared parser to consume the carrier model while retaining public text entrypoints.

### Slice 3 — Strict checker migration

- Status: completed.
- Make the Python code backend consume the Python native model.
- Exclude recognized external directives from `Non.Skw.Annotation` and remove their obsolete blessings.
- Update architecture documentation and dependency guards.

### Slice 4 — Closure

- Status: completed.
- Run focused tests, project Skillware checks, the full test suite, Ruff, and diff validation.

## Impl.Log

- 2026-08-12 — Execution authority registered as ^c20260812-0u.
- 2026-08-12 — The implementation boundary preserves separate native models and one shared downstream Skillware model; it deliberately does not introduce a universal host-language model.
- 2026-08-12 — The approved requirement was checkpointed as `1f31411` before implementation edits.
- 2026-08-12 — Added shared source primitives, Python comment/directive normalization, and Markdown line/heading/fence normalization under `agentos.surfaces`; the namespace has no Skillware dependency.
- 2026-08-12 — Added `SkwSurfaceModel` plus Python and Markdown adapters; the shared parser now consumes this common model, while public raw-text entrypoints compose the layers.
- 2026-08-12 — Migrated the strict Python checker to common annotation classifications. All 28 exact directive blessings became obsolete and `.skw/lock.json` now has no blessings.
- 2026-08-12 — Verification passed: 1,822 tests, Ruff, zero code POIs across 366 configured Python files, `git diff --check`, and wheel/sdist build. The repository-wide formatter check remains outside the gate because 335 pre-existing files are not Ruff-formatted; every changed or added Python file is formatted.
- 2026-08-12 — Added `agentos surfaces normalize --file ...`: it infers supported extensions, accepts an explicit `--language` override, errors when inference is unresolved, and serializes the complete native model with `--json`.
