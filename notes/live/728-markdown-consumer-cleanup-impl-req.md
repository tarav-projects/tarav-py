# Markdown Consumer Cleanup — Impl.Req

## Impl.Abstract

- Status: implemented and verified.
- Scope: simplify the state-heavy Index and Markdown Blocks consumers introduced around native Markdown normalization, and make repository-wide Ruff commands target only maintained code.
- Source authority: autonomous `agentos-py` cleanup authorized by ^c20260812-8u.
- Preparation checkpoint: `7fcaae3`, which committed the completed native-surface consumer migration before cleanup selection.
- Constraints: stay module-local, preserve public models and CLI payloads, add no framework, and do not broaden into unrelated large modules or historical source repair.
- Out of scope: parser grammar changes, new lint policy, splitting packages, removing `_DEPRECATED`, resolving edition-history POIs, or repo-wide complexity reduction.

## Impl.Index

### Stateful.Parser.Decomposition

- `index.model._parse_index_surface` currently mixes native fence projection, mutable block state, and domain-node construction in one decision-heavy function.
- `stdlib.mdblocks._parse_file_blocks` currently mixes scan-window resolution, block state transitions, parent projection, and payload rendering.
- Cleanup should expose these existing phases as private module-local helpers or state objects while retaining the same public `IndexDocument` and Markdown Blocks payloads.

### Maintained.Tooling.Boundary

- `_DEPRECATED/` is a tracked historical source archive, not part of the maintained Python distribution.
- Repository-wide Ruff currently enters that archive and reports hundreds of irrelevant errors even though maintained `src` and `tests` pass.
- Ruff configuration should extend its exclusion set with `_DEPRECATED` so `ruff check .` becomes a meaningful maintained-tree command without deleting history.

### Acceptance.Boundary

- Existing parser and CLI fixtures remain the behavior oracle; this cleanup intentionally changes no external behavior, so RED-first tests are not required.
- The two targeted state-heavy functions must stop triggering `C901`, `PLR0912`, or `PLR0915`.
- Repository-wide Ruff lint, touched-file Ruff formatting, the focused suites, and the full test suite must pass.

## Impl.Agendix

- touched: ^c20260812-8u — cleanup scope and autonomous execution authority.
- touched: `index://agentos-pkg/Floor.Model` — decomposition must preserve the dependable domain models consumed downstream.
- touched: `index://agentos-pkg/Normalization.Pipeline` — native Markdown remains the input boundary; cleanup changes organization, not topology.
- touched: `index://agentos-pkg/Agent.Navigable.Codebase` — private phases and ownership should remain legible to later agents.

## Execution.Plan

### Slice 1 — Index parser state

- Status: completed.
- Extract native-fence node projection and ordinary-line domain parsing from `_parse_index_surface`.
- Keep mutable block/meta state explicit in one private module-local carrier.
- Check: Index parser, linter, Wayfinder, architecture tests, and targeted complexity rules pass.

### Slice 2 — Markdown Blocks state

- Status: completed.
- Extract scan-window resolution and the separator/heading block state machine from `_parse_file_blocks`.
- Keep separator policy, parent assignment, and output schema inside `stdlib.mdblocks`.
- Check: Markdown Blocks CLI, Index structure integration, POI adapter tests, and targeted complexity rules pass.

### Slice 3 — Maintained Ruff boundary

- Status: completed.
- Extend Ruff exclusion with `_DEPRECATED` and document that historical snapshots are outside maintained tooling checks.
- Check: `uv run ruff check .` passes and touched-file format checks do not enter `_DEPRECATED`.

### Slice 4 — Closure

- Status: completed.
- Run the focused integration set, full pytest suite, repository-wide Ruff, Skillware code-surface check, and diff validation.
- Record unrelated pre-existing operational POIs without expanding cleanup scope.

## Impl.Log

- 2026-08-12 — Cleanup preparation committed the prior implementation as `7fcaae3`.
- 2026-08-12 — Autonomous cleanup and boundary confirmation registered as ^c20260812-8u.
- 2026-08-12 — Selection was limited to two adjacent state machines plus the concrete maintained-tooling boundary; broader complexity findings remain outside this cleanup.
- 2026-08-12 — Repository-wide format checking exposed 324 pre-existing maintained files outside Ruff's formatter baseline. Formatting them would broaden cleanup into a repository rewrite, so closure keeps repository-wide Ruff lint and touched-file format checks.
- 2026-08-12 — The executable cleanup request was checkpointed as `f17824f` before implementation edits.
- 2026-08-12 — Index surface parsing now separates native fence projection from explicit block/meta state and ordinary domain-node construction; `_parse_index_surface` no longer triggers the selected complexity rules.
- 2026-08-12 — Markdown Blocks now separates scan-window resolution, separator/heading state transitions, parent projection, and payload assembly; `_parse_file_blocks` no longer triggers the selected complexity rules.
- 2026-08-12 — Ruff excludes tracked `_DEPRECATED` history, making `ruff check .` a maintained-tree check. Historical snapshots remain intact.
- 2026-08-12 — Verification passed: 63 focused tests, 1,830 full tests, repository-wide Ruff lint, touched-file formatting, and diff validation. Skillware reported zero diagnostics and no new code-annotation POIs; its 11 pre-existing edition-history POIs remain outside scope.
- 2026-08-12 — One older `lint_markdown_blocks` complexity score of 11 remains outside the selected state-machine cleanup.
