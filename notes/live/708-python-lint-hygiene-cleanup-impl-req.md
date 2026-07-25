# Python lint hygiene cleanup - impl-req

## Impl.Abstract

- **scope:** restore a clean full-project Ruff check by removing four dead imports and relocating one module-level test import
- **status:** ready for autonomous execution
- **source:** `hugentics-codebase-cleaner --AUTO --codebase agentos-py`
- **target project:** `agentos-py`

## Impl.Index

### Current.State

- `uv run ruff check src tests` reports exactly five findings
- four findings are unused imports in index or Skillware modules and tests
- one finding is a valid `REVIEWED_CITE_CLOSURE` import placed midway through `tests/test_index_linter.py`
- the findings are import hygiene only; no product behavior or public API needs to change

### Scope.Boundary

- remove only imports proven unused by Ruff
- move `REVIEWED_CITE_CLOSURE` into the existing top-level import group
- do not refactor index, Skillware, or Bloberia behavior
- do not add abstractions, dependencies, compatibility paths, or formatting churn

## Execution.Plan

### Slice 1 - Import hygiene

- confirm the existing five-finding Ruff baseline
- remove the unused `agentos_home_dir`, `check_selector`, `pytest`, and `resolve_enabled_checks` imports
- relocate the late `REVIEWED_CITE_CLOSURE` import to the existing `agentos.index.linter` import group
- observable: `uv run ruff check src tests` passes
- status: pending

### Slice 2 - Regression verification

- run the focused index-dependency, index-linter, and Skillware check-selection tests
- run the full `agentos-py` test suite
- observable: tests pass without behavioral changes
- status: pending

## Risks And Deviation Triggers

- stop rather than change behavior if any import is used dynamically or required for test collection side effects
- stop rather than broaden the cleanup if Ruff reveals new findings outside these five after the edits

## Acceptance Signals

- full-project Ruff passes with no findings
- focused affected tests pass
- the full `agentos-py` suite passes
- the diff contains only the planned import edits and this execution record

## Impl.Log

- 2026-07-25: pre-cleanup repository state checkpointed at `206645f`
- 2026-07-25: scan confirmed five bounded import-hygiene findings and no broader Ruff residue
