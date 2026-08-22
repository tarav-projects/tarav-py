# 751 — POI check classes

## Impl.Abstract

- **Goal:** replace the shared POI runtime's function-wrapper checks with instantiated `Check`
  classes whose `run()` method contains the executable computation, then express every IndexLab
  check through that model.
- **Status:** ready for execution.
- **Scope:** `tarav.poi.runtime`, the IndexLab check corpus and registry, their public exports,
  focused tests, POI explanation behavior, and the IndexLab developer guide.
- **Out of scope:** migrating the production `tarav.index` private runner, implementing distributed
  SKW continuations, changing Index records or projections, or introducing a fixture framework.
- **Design authority:** the current user direction: a general pytest-like `POI.Linter` whose
  checks are instantiated with their data, execute through `check.run()`, and use the check class
  as the productive POI documentation attachment point.

## Impl.Index

### POI.Check

- [DC] `Check` is an executable class, not a registry row wrapping a free function.
- [DC] a linter run resolves one domain context, selects check classes, instantiates each selected
  class with that context, calls `run()`, and aggregates the resulting findings.
- [CT] `run()` is the sole check lifecycle method; the general runtime has no privileged `gate()`
  hook.
- [DC] check metadata needed for selection remains class-level and inspectable without executing
  the check.
- [DC] `POI.Class` remains a signal category emitted by a check; one check may emit several POI
  classes and one POI class need not define the check's identity.

### Check.Dependency

- [DC] a precondition is represented by the result of another ordinary check, not by a separate
  gate function.
- [DC] a check may declare ordered check dependencies; a blocked dependency blocks the dependent
  check once, while a failed dependency does not necessarily prevent further evaluation.
- [CT] dependencies must refer to earlier registered checks so execution remains deterministic and
  does not become an implicit recursive scheduler.

### POI.Documentation

- [DC] IndexLab POI annotations attach to the check classes containing the meaningful computation,
  replacing class-name helper functions that made `POI.Explain` uninformative.
- [CT] finding `source` continues to point to the executing `run()` body, while Wayfinder resolves
  POI documentation to the containing check class.

## Execution.Plan

### Slice 1 — shared runtime algebra

- **Status:** pending.
- **RED:** runtime tests require class selection, per-run instantiation, `run()` execution, blocked
  dependency propagation, structural short-circuiting, and metadata introspection.
- **GREEN:** replace callable/gate rows with a focused `Check` base class and check-class registry;
  remove `GateResult` from the shared public runtime.
- **Check:** `tests/test_poi_runtime.py`.

### Slice 2 — IndexLab check corpus

- **Status:** pending.
- **RED:** existing IndexLab behavior tests plus source/documentation assertions require the same
  POI instances and verdicts from class-based checks.
- **GREEN:** move every check computation into a named `Check` subclass, express support/context
  prerequisites as check dependencies, and register the classes in execution order.
- **Check:** `tests/indexlab/test_touch_and_linter.py` and `tests/indexlab/test_cli.py`.

### Slice 3 — closure

- **Status:** pending.
- Update the developer guide and this artifact.
- Reinstall the editable CLI if the public import surface changes.
- Run focused IndexLab/shared-runtime tests, architecture tests, Ruff, `git diff --check`, the
  retained workspace linter/POI-explain smoke checks, and the proportionate complete suite.
- Audit changed product surfaces; add no annotation that merely restates self-evident code.

## Impl.Log

- **Execution authority:** `$tarav-hugentics --impl --dev --AUTO` in the current conversation.
- **Initial state:** the completed Kernel.Writing renderer slice is present but uncommitted and will
  be preserved by the workflow checkpoint before this implementation begins.
