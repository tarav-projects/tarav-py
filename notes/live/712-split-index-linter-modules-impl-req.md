# Split index linter modules - impl-req

## Impl.Abstract

- **scope:** split the 1,868-line index linter into cohesive orchestration, shared-model, structural-check, and parser-check modules without changing its public API or behavior
- **status:** ready for execution
- **source:** `hugentics-codebase-cleaner --AUTO --codebase agentos-py`, focused on long files
- **target project:** `agentos-py`

## Impl.Index

### Current.State

- `src/agentos/index/linter.py` is 1,868 lines and owns four distinct concerns: public orchestration/configuration, state and result models, filesystem/router checks, and parser-backed semantic checks
- the check groups already communicate through `LinterState` and `LinterCheck`, so they have a natural module boundary without needing a new framework or runtime abstraction
- callers and tests import the stable `agentos.index.linter` module, including selected check constants and extension types
- the focused baseline is green: `uv run pytest -q tests/test_index_linter.py` passes 57 tests

### Scope.Boundary

- retain `agentos.index.linter` as the public facade and preserve existing import names
- preserve check codes, check order, selection metadata, gates, findings, rendering, coverage accounting, and exit behavior
- move shared dataclasses and type aliases to one private model module
- move filesystem, Markdown-block, router, appendix, and depot checks to one private structural-check module
- move parser-backed line, anchor, grounding, and reviewed-cite checks to one private parser-check module
- update `AGENTS.md` only enough to document the resulting index-linter ownership boundary
- do not change linter policy, CLI arguments, parser behavior, dependencies, or test expectations

## Execution.Plan

### Slice 1 - Shared linter models

- extract shared state, finding, gate, check, and coverage models into a private index-linter module
- re-export the existing public model names from `agentos.index.linter`
- observable: public imports continue to resolve and focused tests pass
- status: pending

### Slice 2 - Structural checks

- extract surface discovery, Markdown-block, depot, concept, appendix, and router checks into a private structural-check module
- expose one ordered structural check tuple for composition by the facade
- observable: structural check order and focused linter results remain unchanged
- status: pending

### Slice 3 - Parser-backed checks and verification

- extract parsed-document loading and semantic line/anchor/grounding checks into a private parser-check module
- compose the complete public `CHECKS` tuple in the original order and re-export existing check constants
- update the local architecture guidance, run focused tests, Ruff, and the complete test suite
- observable: the original file is materially smaller and all repository verification passes
- status: pending

## Risks And Deviation Triggers

- preserve the exact `CHECKS` ordering because later gates and coverage reporting depend on earlier structural mutation
- stop rather than redesign check state or policy if extraction exposes a behavioral coupling that cannot be represented by the existing `LinterState` boundary
- stop rather than broaden cleanup into other long files, parser changes, or CLI redesign

## Acceptance Signals

- `src/agentos/index/linter.py` is reduced to a focused public orchestration/reporting facade
- no extracted module simply replaces the original with another comparably oversized mixed-concern file
- all imports currently supported from `agentos.index.linter` continue to work
- `uv run ruff check src tests` passes
- `uv run pytest -q tests/test_index_linter.py` passes
- the full `uv run pytest -q` suite passes
- the diff contains only the planned linter split, the required guidance update, and this execution record

## Impl.Log

- 2026-07-29: selected the index linter after a maintained-source inventory; it is the longest production module and has clear existing state/check seams
- 2026-07-29: focused baseline passed with 57 tests
