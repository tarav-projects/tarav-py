# 749 — IndexLab POI.Linter reimplementation

## Impl.Abstract

- **Goal:** replace the ad-hoc IndexLab lint traversal with a faithful `POI.Linter` realization
  shaped after `src/tarav/index/linter.py`, integrated with context-attached `Index.Record`s,
  `Index.Workspace`, semantic projection, and `UserTouchSource`.
- **Status:** completed, including the read-only `POI.Tripwire` continuation slice.
- **Scope:** shared POI verdict/runtime primitives where the semantics are already proven,
  `tarav.indexlab` lint context/checks/report/CLI, focused tests, the retained development
  workspace, and the IndexLab developer guide.
- **Out of scope:** migrating the production `tarav.index` check corpus, inventing semantic
  assertion scoring, implementing blessings before the new Index blessing record is designed,
  and defining label/isoline/isoblock narrowing without a settled subject-selection rule.
- **Design authority:** `tarav-pkg/references/poi-linter.md`, the production
  `src/tarav/index/linter.py` realization, and the current user correction.
- **User support:** Chatlas session
  `c9d44ac37e655c397de8ea8322baeffa87469c1ec55ae98532144bc5ff50ddb5`, especially message
  `1d7140d0…49a529` (the IndexLab linter must follow the established POI.Linter design rather
  than form a new linter) and `3c0088d2…d20c45d` (autonomous develop authorization).

## Impl.Index

### Runtime.Algebra

- [DC] One IndexLab lint run resolves one `LintContext`, selects named checks, executes them in
  registry order, and returns one report carrying every check verdict. Support:
  `1d7140d0…49a529`.
- [DC] `passed`, `failed`, and `blocked` remain distinct per check and per finding; `clean` means
  no failures, while `verified` additionally requires no blocked finding or check. Support:
  `1d7140d0…49a529`.
- [DC] Structural checks are never deselectable and short-circuit when their findings make later
  checks meaningless. Reportable checks accumulate POIs without mutation.
- [DC] A finding carries class, subject, operands, status, evaluator, surface, tier, and computed
  check source. Its stable identity excludes operands; it carries neither semantic severity nor a
  prescribed remedy.

### Domain.Integration

- [DC] `IndexLabLintContext` owns the explicitly selected workspace/store, normalized touch
  source, complete record corpus, current subject selection, cached touch resolutions, semantic
  projection, and projection errors.
- [DC] Narrowing changes which records are examined, never the complete corpus available as
  context. The first supported subject selector is exact `Record.Id`; unresolved selectors fail
  closed instead of producing a clean run.
- [DC] Existing POI classes and their managed `$kw` blocks remain domain-owned beside the checks.
  The current mechanics are reorganized into named checks rather than discarded.
- [DR] The initial registry contains `records-loadable`, `context-resolves`, `support-present`,
  `support-resolves`, `support-roles`, `support-visible`, and `projection-valid`; one check may
  emit several POI classes when those classes are outcomes of one mechanical evaluation.
- [DR] Mock workspaces remain ordinary explicit `UserTouchSource` configurations. A future relaxed
  assertion belongs in a `dev` check that replaces its strict counterpart; mock selection itself
  does not silently activate the dev lane.

### Shared.POI.Foundation

- [DC] Shared POI machinery owns the common three-valued verdict, tier, check execution, stable
  finding, selection, run report, and renderer contracts; IndexLab owns its context, checks, gates,
  POI class blocks, and execution metadata.
- [DC] The experimental namespace does not import production `tarav.index.linter`; the proven
  algebra is placed below both domains so the new implementation does not depend on the old Index
  model.
- [DR] Production Index migration onto the shared runner is deferred. This slice may relocate
  already-identical verdict/tier vocabulary to the shared POI namespace and update production
  imports, but does not rewrite its checks.

### Report.And.CLI

- [DC] One JSON-serializable `IndexLab.Linter.Run` document is built before rendering. Text and JSON
  consume the same document; filters and limits affect presentation, never execution or class
  completeness.
- [DC] The document separates execution metadata, check results, POI class aggregates, and POI
  instances. It reports the selected workspace and record counts instead of old Index surface
  metrics.
- [DC] `tarav indexlab lint` exposes the live check catalog, check inclusion/exclusion, exact
  record narrowing, instance filters, deterministic limits, and a dev lane using the production
  linter's operational semantics.
- [DC] The CLI exits zero only for `verified`. The production command's current blocked-only zero
  exit is not copied because it contradicts the accepted three-valued contract.

## Execution.Plan

### Slice 1 — shared POI runtime

- **Status:** completed.
- **RED:** focused tests require stable operand-independent identity, failed-over-blocked-over-passed
  check verdicts, structural short-circuiting, forced structural selection, dev replacement, and
  targeted record-scoped selection.
- **GREEN:** add the minimal shared runtime beneath domain linters and use the shared verdict/tier
  vocabulary without changing the production Index check corpus.
- **Check:** focused POI runtime and existing production Index linter/report tests.

### Slice 2 — IndexLab context and check registry

- **Status:** completed.
- **RED:** existing IndexLab scenarios must expose named check results; unloadable cargo must stop
  the registry; blocked touch resolution must block its check; exact record targeting must retain
  the full corpus as context while examining one record.
- **GREEN:** replace the flat `lint_records` traversal with `IndexLabLintContext`, cached resolution
  helpers, the seven-check registry, and the shared executor.
- **Check:** `tests/indexlab/test_touch_and_linter.py` and usage scenarios.

### Slice 3 — canonical report and CLI surface

- **Status:** completed.
- **RED:** text and JSON must consume one run document; check/class/instance sections remain
  distinct; limits preserve complete class summaries; unresolved record selectors fail closed;
  blocked-only runs exit nonzero.
- **GREEN:** add the IndexLab run-document projection and renderer, then expose catalog, selection,
  narrowing, filtering, limit, lane, and JSON flags through `tarav indexlab lint`.
- **Check:** focused report and IndexLab CLI tests plus installed CLI smoke runs.

### Slice 4 — playground and closure

- **Status:** completed.
- Run the new linter over `var/indexlab/dev-library/main` through the real Chatlas adapter and
  inspect the named check results and class summaries.
- Update `746-indexlab-dev-guide.md` and this artifact with the landed architecture, deferred
  blessing/semantic work, deviations, and verification.
- Run focused POI/IndexLab/architecture tests, Ruff, `git diff --check`, and the proportionate full
  suite. Audit product surfaces; add no annotation that merely restates self-evident code.

### Slice 5 — read-only `POI.Tripwire`

- **Status:** completed.
- **RED:** a supplied literal substring must trigger one `IndexLab.Linter/Tripwire.Hit` for every
  occurrence in every string leaf of selected records; overlapping occurrences, several needles,
  automatic check activation, exact-record narrowing, and operand-independent identity must be
  protected; missing or empty tripwires fail closed.
- **GREEN:** replace the record-assertion probe with a default-off, reportable, record-scoped
  `tripwire` check and repeatable `--tripwire`. Each subject carries record id, JSON-pointer field
  path, tripwire, and occurrence number; offset and bounded excerpt remain operands.
- **Check:** focused registry/finding tests, CLI catalog and JSON rendering, architecture guards,
  then the relevant IndexLab suite.

## Impl.Log

- **Execution authority:** `$tarav-hugentics --impl --dev --AUTO` at Chatlas message
  `3c0088d2…d20c45d`.
- **Pre-execution checkpoint:** `d7c16d7` (`chore: checkpoint indexlab linter development`).
- **Design correction:** the existing IndexLab check semantics are retained, but its private
  report/traversal runtime is superseded by the established POI.Linter algebra.
- **Implemented:** `tarav.poi.runtime` now owns the reusable algebra; IndexLab supplies a cached
  domain context, seven named checks, dependency gates, exact record narrowing, execution
  metadata, and the canonical `IndexLab.Linter.Run` text/JSON surface.
- **Playground:** `var/indexlab/dev-library/current-chat` loaded six records through Chatlas and
  passed all seven checks; a one-record narrowed run retained six loaded records and selected one.
- **Verification:** focused POI/IndexLab/production-Index/architecture tests passed; the complete
  suite passed (`2262 passed`); Ruff and `git diff --check` passed.
- **Product capture:** managed `$kw` blocks define each IndexLab POI class and the shared runtime
  decision. No production Index capture was landed: this isolated lab slice changed implementation
  and its maintained developer/Impl.Req surfaces without introducing a new accepted product claim.
- **Open design boundary:** blessings and non-record selectors remain deliberately deferred because
  the new Index model has not yet defined their record operations or subject expansion semantics.
- **Continuation authority:** the user requested that the earlier linter's `POI.Test` mechanism be
  checked and, if absent, implemented for IndexLab. The old implementation was confirmed at
  `src/tarav/index/linter.py`; IndexLab had no corresponding check.
- **Superseded attempt:** `index.poi.test` record assertions worked mechanically, but required
  mutating the Index merely to test its reader. The user rejected that carrier before commit; no
  compatibility path is retained.
- **Tripwire decision:** the probe is runtime input over the existing read-only record corpus.
  Literal, case-sensitive matching keeps the query cheap and reproducible; raw Chatlas support
  message bodies remain outside “everywhere” because they are not part of the Index.Record surface.
- **Slice 5 result:** repeatable `--tripwire` automatically activates the otherwise-off,
  record-scoped check; each overlapping occurrence is addressed by record, JSON-pointer field,
  literal, and occurrence number, while offset and excerpt remain operands. `--check tripwire`
  without a substring and empty substrings fail closed.
- **Slice 5 verification:** the live six-record Chatlas workspace produced two read-only hits for
  `block.create`; 167 focused tests and the complete suite (`2264 passed`) passed; Ruff and
  `git diff --check` passed.
