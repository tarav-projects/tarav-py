# POI Check Replacement Dependencies — Impl.Req

## Impl.Abstract

- **Goal:** make shared-runtime check dependencies honor active dev replacements instead of restoring and executing the displaced production check.
- **Status:** completed and verified.
- **Scope:** `tarav.poi.runtime` selection/execution semantics, focused runtime tests, and the shared POI runtime guidance affected by the correction.
- **Out of scope:** production `tarav.index` migration, new dependency syntax, replacement chains, and IndexLab domain behavior.
- **Source:** review of the class-based POI check implementation at checkpoint `2d5e534`.

## Impl.Index

### POI.Check.Replacement.Dependency

- [DF] an active dev replacement is the effective implementation of the check name it replaces for both selection and dependency evaluation.
- [CO] dependency closure must not restore a production check displaced by the active dev lane.
- [CO] blocked-result propagation must read the effective replacement result rather than the absent displaced result.
- [CT] ambiguous active replacements and replacements of unknown checks fail during registry selection instead of producing order-dependent execution.

## Execution.Plan

### Slice 1 — effective dependency resolution

- **Status:** completed.
- Add a boundary test where a selected check requires a production check that an active dev check replaces; first prove the current selector returns both implementations.
- Centralize active replacement resolution inside the shared runtime.
- Use the resolved dependency for closure, ordering validation, skip conflicts, and blocked-result propagation.
- Preserve existing non-dev, targeted, structural, and explicit-selection behavior.
- Verify with `tests/test_poi_runtime.py`, the focused IndexLab/architecture suites, Ruff, `git diff --check`, and the complete test suite.

### Acceptance

- The dev run selects the replacement and dependent, never the displaced production check.
- A blocked replacement blocks its dependent once.
- Invalid or ambiguous replacement declarations fail deterministically.
- Existing IndexLab behavior and POI explanation remain unchanged.

## Impl.Log

- [IP] The correction treats `replaces` as a logical substitution rather than presentation-only selection metadata; this follows from the existing replacement behavior and dependency algebra.
- [EX] Autonomous cleanup execution was authorized by the user's `$tarav-hugentics --impl --clear` followed by `--AUTO` invocation in the current chat.
- [LG] Active replacement resolution is shared by selection and execution; dependencies resolve to the replacement for closure, ordering, skip conflicts, and blocked-result propagation.
- [LG] Ambiguous replacements, unknown replacement targets, and replacement chains now fail deterministically rather than producing an order-dependent run.
- [LG] RED reproduced both implementations being selected; GREEN selects only the replacement and dependent, with a blocked replacement blocking the dependent once.
- [LG] Verification passed: 47 focused tests, an exact `dev-library/main` IndexLab lint (`VERIFIED`, 25 records, 7/7 checks), the complete suite (`2272 passed`), Ruff, and `git diff --check`.
- [LG] Final Product.Surface capture audit found no qualifying new product annotation: the correction is directly expressed by runtime behavior and boundary tests.
