# Anchory Scan Command Cleanup - impl-req

## Impl.Abstract

- **scope:** tighten the fresh Anchory scan implementation by removing untyped renderer payload indexing, centralizing scan match payload construction, and simplifying line/column lookup.
- **status:** implemented
- **source:** `hugentics-codebase-cleaner --AUTO` after the Anchory source-query implementation.
- **current state:** `agentos.anchory.commands._print_scan_human` indexes a mixed `dict[str, object]` payload and uses `# type: ignore`; `core._line_column` manually scans line-start offsets for every match.
- **out of scope:** changing the `agentos anchory scan` CLI contract, adding new scan features, changing existing JSON payload shape, or touching unrelated Anchory storage behavior.

## Impl.Index

### Anchory.Scan.Rendering.Typed

- scan rendering should not depend on untyped nested payload indexing.
- the command can keep deterministic JSON output while deriving it from typed local values.
- human rendering should consume the same typed resolved matches used for JSON output.
- `# type: ignore` should not be needed for normal scan rendering.
- the cleanup stays module-local; no broad utility layer is justified.

### Anchory.Source.Location.Lookup

- source match line/column lookup is a pure offset-to-location operation.
- line starts are already precomputed before match iteration.
- `bisect_right` expresses “last line start before this offset” directly.
- replacing the manual loop improves clarity without changing location semantics.

## Execution.Plan

### Slice 1 - Typed scan rendering

- introduce a small module-local typed structure for resolved scan matches or equivalent typed helper flow in `agentos.anchory.commands`.
- build JSON match payloads through one helper.
- render human output from typed resolved matches rather than a nested `dict[str, object]`.
- preserve the current JSON shape exactly.
- RED: add/adjust a focused assertion that scan human and JSON outputs still cover resolved and missing records.
- GREEN: remove scan-rendering `# type: ignore` comments while existing e2e behavior remains green.
- check: `cd agentos-py && uv run pytest tests/test_anchory.py`
- status: complete

### Slice 2 - Location lookup simplification

- replace the manual `_line_column` loop with `bisect_right`.
- keep 1-based line and column semantics unchanged.
- check: `cd agentos-py && uv run pytest tests/test_anchory.py`
- status: complete

### Slice 3 - Verification

- run Ruff on touched Anchory files.
- run the focused Anchory tests.
- inspect diff for no CLI contract drift.
- status: complete

## Acceptance.Signals

- `agentos.anchory.commands` has no scan-rendering `# type: ignore` comments.
- scan JSON payload shape remains unchanged.
- human output remains unchanged in substance.
- missing anchors still render as missing/null.
- source locations remain the same for existing named-group, first-group, and whole-match tests.
- focused tests and Ruff pass.

## Deviation.Triggers

- stop if removing type ignores requires broad command framework changes.
- stop if typed rendering would make the simple command harder to read than the current local payload.
- stop if preserving JSON shape conflicts with the refactor.

## Impl.Log

- 2026-07-07: Cleanup request created. Pre-cleanup checkpoint for existing Anchory work: `dbcaf48`.
- 2026-07-07: Executed in `Alignment.Mode:Autonomous`; execution checkpoint: `c532d4e`. Cleanup kept scope to Anchory scan internals: typed resolved scan matches replaced mixed-payload human rendering, JSON match payload construction is centralized, and `_line_column` now uses `bisect_right`. Verification: `uv run pytest tests/test_anchory.py` passed (11), `uv run ruff check src/agentos/anchory/core.py src/agentos/anchory/commands.py tests/test_anchory.py` passed, and cross-package `agentos-cli` `uv run pytest tests/test_e2e_anchory.py` passed (5).
