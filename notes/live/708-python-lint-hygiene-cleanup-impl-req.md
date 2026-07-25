# Python lint hygiene cleanup - impl-req

## Impl.Abstract

- **scope:** restore a clean full-project Ruff check by removing three dead imports, making one public re-export explicit, and relocating one module-level test import
- **status:** implemented and fully verified
- **source:** `hugentics-codebase-cleaner --AUTO --codebase agentos-py`
- **target project:** `agentos-py`

## Impl.Index

### Current.State

- `uv run ruff check src tests` reports exactly five findings
- four findings are imports Ruff considers unused; focused tests establish that one is an intentional public re-export
- one finding is a valid `REVIEWED_CITE_CLOSURE` import placed midway through `tests/test_index_linter.py`
- the findings are import hygiene only; no product behavior or public API needs to change

### Scope.Boundary

- remove only imports proven unused by Ruff and focused tests
- preserve `agentos.index.linter.check_selector` as an explicit public re-export
- move `REVIEWED_CITE_CLOSURE` into the existing top-level import group
- do not refactor index, Skillware, or Bloberia behavior
- do not add abstractions, dependencies, compatibility paths, or formatting churn

## Execution.Plan

### Slice 1 - Import hygiene

- confirm the existing five-finding Ruff baseline
- remove the unused `agentos_home_dir`, `pytest`, and `resolve_enabled_checks` imports
- preserve `check_selector` through an explicit same-name alias after focused tests establish the re-export contract
- relocate the late `REVIEWED_CITE_CLOSURE` import to the existing `agentos.index.linter` import group
- observable: `uv run ruff check src tests` passes
- status: completed

### Slice 2 - Regression verification

- run the focused index-dependency, index-linter, and Skillware check-selection tests
- run the full `agentos-py` test suite
- observable: tests pass without behavioral changes
- status: completed

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
- 2026-07-25: mandatory pre-execution checkpoint created at `fbd05de`
- 2026-07-25: initial removal of `check_selector` passed Ruff but failed six focused tests; restored it as an explicit re-export rather than changing the public contract
- 2026-07-25: full Ruff check passed, all 75 focused tests passed, and the complete suite passed with 512 tests
