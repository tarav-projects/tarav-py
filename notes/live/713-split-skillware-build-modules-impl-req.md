# Split Skillware build modules - impl-req

## Impl.Abstract

- **scope:** split the 1,846-line Skillware build module into cohesive source-expansion and build/check operation modules behind the stable `agentos.skillware.build` facade
- **status:** implemented and fully verified
- **source:** continuation of `hugentics-codebase-cleaner --AUTO --codebase agentos-py`, focused on long files
- **target project:** `agentos-py`

## Impl.Index

### Current.State

- `src/agentos/skillware/build.py` is the longest remaining production module at 1,846 lines
- its existing `# --- build + lock + check ---` boundary separates configuration, source loading, locator resolution, and expansion from build, POI check, project check, and blessing operations
- commands and tests import through `agentos.skillware.build`; tests also exercise `_resolve_locator`, `_SkwSurfaceProvider`, and `_code_surface_pois`
- the focused baseline is green: 126 Skillware tests pass

### Scope.Boundary

- retain `agentos.skillware.build` as the stable public facade and keep its line-1 Skillware annotation intact
- move configuration, depot resolution, source loading, locator resolution, and expansion to one private core module
- move build, lock, check, project-check, POI, and blessing behavior to one private operations module
- preserve existing public names and the three test-backed private hooks
- preserve lock format, POI identities, check ordering, filesystem behavior, and command behavior
- update `AGENTS.md` only enough to document the resulting Skillware module ownership
- do not alter Skillware grammar, policies, generated content, dependencies, or CLI arguments

## Execution.Plan

### Slice 1 - Expansion core extraction

- extract configuration models/loaders, depot and package resolution, source expansion, and locator helpers
- keep expansion behavior and `_resolve_locator` reachable through the facade
- observable: focused expansion/configuration tests pass
- status: completed

### Slice 2 - Build/check operations extraction

- extract lock management, build/check reports, POI checks, project checks, and blessing operations
- keep `_SkwSurfaceProvider` and `_code_surface_pois` reachable through the facade
- observable: focused build/check/unlock tests pass with unchanged POI and lock behavior
- status: completed

### Slice 3 - Facade and repository verification

- make `build.py` an explicit compatibility-free facade over the two ownership modules
- document module ownership and audit defined public symbol parity against the checkpoint
- run focused tests, full Ruff, focused formatting, Skillware project check, and the full test suite
- observable: no implementation module remains comparably oversized or mixed-concern, and all verification passes
- status: completed

## Risks And Deviation Triggers

- preserve the line-1 `$kw` annotation on `build.py`; stop if the split causes a managed-surface or Skillware self-check regression
- preserve re-exported `extract_mentions` and all names directly imported by commands or tests
- stop rather than redesign core/operations dependencies if the existing boundary cannot be extracted without behavioral changes
- do not broaden this slice into Skillware grammar, parser, command, or edition-history refactors

## Acceptance Signals

- `src/agentos/skillware/build.py` becomes a small stable facade
- source expansion and build/check behavior live in separate cohesive private modules, each materially smaller than the original
- all originally defined public symbols and test-backed private hooks remain reachable through `agentos.skillware.build`
- full Ruff and focused formatting checks pass
- the 126-test focused Skillware suite passes
- `agentos skw check --project .` or the locally supported equivalent completes without a new split-induced finding
- the full test suite passes
- the diff contains only the planned Skillware split, required guidance, and this execution record

## Impl.Log

- 2026-07-29: selected `skillware/build.py` after the post-linter inventory; its existing build/check section boundary provides the strongest next split
- 2026-07-29: focused baseline passed with 126 tests
- 2026-07-29: mandatory pre-execution checkpoint created at `56122c5`
- 2026-07-29: extracted configuration/expansion and build/check operations behind the stable `agentos.skillware.build` facade
- 2026-07-29: all 126 focused Skillware tests and focused Ruff passed after extraction
- 2026-07-29: facade audit preserved all 43 defined public symbols, the exact ordered 25-name `__all__`, and the three test-backed private hooks
- 2026-07-29: project-scope `agentos skw check --json` loaded both packages with zero package POIs; its 11 project POIs are existing edition-history data findings targeting unrelated records, `commands.py`, and `edition_history.py`
- 2026-07-29: full Ruff, focused formatting, all 126 focused tests, and all 551 repository tests passed
