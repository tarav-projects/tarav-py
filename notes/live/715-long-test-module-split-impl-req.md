# Long Test Module Split - impl-req

## Impl.Abstract

- **Scope:** split the two oversized `agentos-py` test modules into behavior-owned modules with private shared fixture helpers.
- **Status:** approved for autonomous execution.
- **Source:** codebase-cleaner scan at checkpoint `607e356` and direct user authorization ^c20260731-5u
- **Out of scope:** production behavior, assertion changes, AGENTS.md architecture changes, broad formatting, and splitting cohesive modules below the outlier tier.

## Impl.Agendix

- `tests/test_skillware.py` is 2,102 lines and mixes parser grammar, build/check lifecycle, configuration, CLI, blessing, and cross-package resolution.
- `tests/test_index_linter.py` is 1,591 lines and mixes depot structure, line grounding/coverage, check selection, CLI selection, and agendix closure.
- Both files have stable behavioral seams and repeated fixture construction suitable for private non-test helpers.
- Autonomous cleanup authority: ^c20260731-5u

## Impl.Index

### Skillware.Test.Domains

- Separate parser grammar from filesystem-backed build/check behavior.
- Separate project/config/CLI and cross-package integration from single-package lifecycle tests.
- Keep fixture writers private and avoid imports between `test_*.py` modules.

### Index.Linter.Test.Domains

- Separate depot/surface structure checks from line grounding and coverage checks.
- Separate check-selection and CLI-selection behavior from agendix closure checks.
- Centralize only generic depot writers and linter runners in a private helper.

## Execution.Plan

### Slice 1 - Split Skillware tests

- Extract reusable Skillware source/depot writers into `tests/_skillware_helpers.py`.
- Create focused parser and project/CLI modules; retain build/check lifecycle in the original module.
- Preserve every test function and fixture payload.

### Slice 2 - Split Index linter tests

- Extract generic index/depot writers and the linter runner into `tests/_index_linter_helpers.py`.
- Create line/coverage, selector/CLI, and agendix-closure modules; retain structural checks in the original module.
- Preserve every test function and fixture payload.

### Slice 3 - Regression verification

- Compare sorted test-function inventories before and after each split.
- Confirm the repository still collects 592 tests.
- Run the split modules directly, Ruff over `src/` and `tests/`, and the full suite.

## Risks And Deviation Triggers

- Do not import one test module from another; move only the minimum shared fixture into a private helper.
- If a test requires assertion or production changes to move, leave it in its original module.
- Do not split files merely to satisfy a numeric line threshold.

## Acceptance Signals

- Neither original outlier remains a mixed-domain monolith.
- Skillware and Index linter test-function inventories are unchanged.
- The full suite collects 592 tests and passes.
- `uv run ruff check src tests` passes.

## Impl.Log

- Cleanup preparation checkpoint: `607e356` (`feat: support application-owned anchor amendment validation`).
- Execution authority: ^c20260731-5u
