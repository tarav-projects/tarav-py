# 696 — skw Dependency Resolution Integrity (dangling-dependency POI)

## Impl.Abstract

- **Scope**: add a resolution-integrity check to the skw dependency-sync lint (`agentos skillware check`): a *declared* dependency (`depends` / `copy` / `derived` with a `--from <Dotted.Name>`) whose target no longer resolves in the configured depots emits a new advisory, suppressible POI kind — `dangling-dependency`. Realizes the `Skw.Network` pointer-binding integrity check named in the 591 reconciliation. ^c20260720-2u
- **Status**: designed under `/agentos-hugentics-impl --dev --AUTO`; ready to execute.
- **Source context**: 591 design session close-out. The reconciliation pass observed that a renamed/retired index concept can drift silently into a skw-managed skill because nothing enforces that a declared cross-surface name still resolves. Empirically confirmed in `agentos-py/src/agentos/skillware/build.py`: `_dependency_sync_pois` computes `declared_resolutions` (line ~681) but never emits a POI for the `unresolved:` case — a declared `--from` target that stops resolving falls through silently.
- **Out of scope** (recorded, not built): (a) alias-divergence blind spot — compiled prose mentions one name while the declaration uses a kept-alias of it, so neither `undeclared` nor `unhonored` fires; (b) flagging *unresolved bare prose mentions* (not declared) — deliberately rejected as a noise flood, the opt-in declaration is the design; (c) any new declaration syntax — `pointer` binding already exists via `depends`.

## Impl.Index

- **[DF] the gap**: the dependency-sync check has two directions today — `undeclared-dependency` (a mention that resolves but isn't declared) and `unhonored-dependency` (a declared dep not mentioned in compiled text). Missing: a declared dep whose target *fails to resolve*. That is the exact silent channel a rename/retirement escapes through.
- **[CT] the fix is opt-in by construction**: only *declared* dependencies are checked, so no prose-mention noise. Declaring `depends --from Index.Ontology` is the act that binds the name; the new check makes that binding enforce resolution. This is `Constraint.Steering` made real for cross-surface names — the binding breaks loudly when its target renames-without-alias or retires.
- **[CT] value survives aliases**: aliases are a courtesy, not guaranteed. Retirements (e.g. `Derivation.Rule`, `State.Point`, `Judgement.Bank`) drop the name as a resolvable block entirely — a lingering `--from` to them would dangle and now be caught. The check's payoff is precisely at un-aliased-rename / retirement time.
- **[DC] current code**: `src/agentos/skillware/build.py`
  - `_dependency_sync_pois(skillware, target_rel, source, expansion)` — lines ~660-709; the extension point.
  - `_poi(kind, target, key, payload, detail)` — POI constructor with identity hash (line ~480).
  - `SUPPRESSIBLE_KINDS = ("undeclared-dependency", "unhonored-dependency")` — line ~476; new kind joins it (blessable-as-suppressible so a deliberately-retained dangling ref can be accepted).
  - `_resolved_dotted_names` returns `unresolved:<detail>` strings for names that don't resolve; `declared_resolutions` already holds them.
  - dependency froms come from `source.dependencies[*].froms` and `source.recipes[*].froms`, filtered by `_is_dotted_name_locator`.
- **[DC] check module & prescriptions**: the agentos-index skill's `references/check.skw.md` documents POI kinds and prescriptions; the new kind needs a one-line prescription there (re-derive/rebuild not applicable — prescription is *fix the declaration or bless*). Also the 107 `Drift.POI` block enumerates kinds — a follow-up doc-sync line, not code.

## Execution.Plan

### Slice 1 — emit `dangling-dependency` for unresolved declared targets
- **Change**: in `_dependency_sync_pois`, after collecting `declared` dotted-name targets (from both `dependencies` and `recipes`), resolve *all* of them (not just `declared_from_depends`), and for any whose resolution starts with `unresolved:`, append a `dangling-dependency` POI keyed by the name, payload = the resolution string, detail = ``declared dependency `<name>` no longer resolves in the configured depots``.
- **Ordering vs existing kinds**: a name that is unresolved must NOT also produce a spurious `unhonored-dependency` (it can't be "mentioned-and-resolved" if it doesn't resolve). Ensure the unhonored branch and the dangling branch are mutually exclusive per name — dangling takes precedence; skip the unhonored append when the name is unresolved.
- **Check**: unit test — a skill fixture with a `depends --from Nonexistent.Name` (or a recipe `derived --from Gone.Block`) over a depot lacking that block yields exactly one `dangling-dependency` POI for that name and no `unhonored-dependency` for it.
- **Observable**: `agentos skillware check --skill <fixture>` lists the new POI kind.

### Slice 2 — register the kind as suppressible/blessable
- **Change**: add `"dangling-dependency"` to `SUPPRESSIBLE_KINDS`.
- **Check**: unit test — `agentos skillware bless --skill <fixture> --poi <hash>` (or by-kind bless) records the blessing and the POI is suppressed on the next check; a subsequent change to the situation re-surfaces it (identity-hash discipline, mirrors existing suppressible-kind tests).
- **Observable**: blessed dangling POI disappears from the report until its key/payload changes.

### Slice 3 — RED→GREEN behavior test for the drift scenario
- **Change**: add a test that reproduces the session's failure shape: fixture declares `--from Old.Name`, depot has `Old.Name`; assert 0 POIs (GREEN baseline). Rename the depot block to `New.Name` **without** an alias; re-run check; assert exactly one `dangling-dependency` for `Old.Name` (RED caught). Add the alias back; assert it resolves again and the POI clears (GREEN). This is the regression guard proving the silent channel is now closed.
- **Check**: the test transitions RED→GREEN exactly as described; run `pytest tests/test_skillware.py -k dangling`.

### Slice 4 — check-module prescription doc
- **Change**: in `agentos-md/skills/agentos-index/.skillware/src/references/check.skw.md`, add the `dangling-dependency` kind to the POI-kinds/prescriptions list (prescription: fix or remove the stale `--from`, restore an alias on the target, or bless if the dangling reference is deliberate). Rebuild the skill surface (`agentos skillware build --skill skills/agentos-index`); resolve any resulting derived-stale POI on the touched module.
- **Check**: `agentos skillware check --skill skills/agentos-index` returns to 0 POIs after rebuild/bless; the compiled `references/check.md` shows the new kind.

### Risks / deviation triggers
- If `source.dependencies` and `source.recipes` overlap a name across binding modes, dedupe by name so a single POI fires. Deviation: if dedup interacts badly with the existing `declared` set logic, prefer the smallest change that keeps one POI per unresolved name and record it in Impl.Log.
- If adding the kind to `SUPPRESSIBLE_KINDS` changes existing test snapshots (kind ordering in reports), update snapshots faithfully.

### Acceptance signals
- New `dangling-dependency` POI fires for an unresolved declared `--from`, is suppressible/blessable, and the RED→GREEN regression test guards the drift scenario.
- `pytest tests/test_skillware.py` green; `agentos skillware check --skill skills/agentos-index` back to 0 POIs; depot linter unaffected.

## Impl.Log

- 2026-07-20 — artifact created under `--dev --AUTO`. Architectural decision (autonomous): extend the existing `_dependency_sync_pois` rather than add a new command or move the check into the index linter — the gap is precisely this function's silent skip of the unresolved-declared case, and the user's framing was "smallest change highest payoff." Rejected flagging unresolved bare mentions (noise flood); the opt-in `--from` declaration is the intended binding act. Grounding: `^c20260720-2u` (invocation gate, Autonomous).
- 2026-07-20 — EXECUTED. All four slices landed:
  - Slice 1: `dangling-dependency` POI emitted for any declared dotted-name `--from` whose target resolves to `unresolved:` (`build.py` `_dependency_sync_pois`); dangling and unhonored made mutually exclusive per name (dangling takes precedence).
  - Slice 2: kind added to `SUPPRESSIBLE_KINDS` — blessable like its siblings.
  - Slice 3: RED→GREEN regression test `test_dangling_dependency_catches_unaliased_rename` guards the exact silent-drift scenario (declared→rename-without-alias→dangling→restore-alias→clears).
  - Slice 4: check module (`agentos-skillware` `check.skw.md`) gained a "Dependency sync" prescription group covering all three kinds (the two siblings were previously undocumented — closed that gap too); rebuilt, `check.md` `[ok]`.
  - **Deviation 1** (recorded): the existing test `test_dependency_sync_pois_and_hashes` asserted `unhonored-dependency` for `Concept.Missing`, which is unresolved. Under the corrected semantics that is now `dangling-dependency`; updated the assertion faithfully — the old test conflated declared-but-missing with declared-but-unmentioned.
  - **Deviation 2** (recorded): planned slice-3 sibling test for `derived --from` dangling proved the premise wrong — an unresolved recipe `--from` cannot materialize and is caught upstream, louder, as an `unresolvable` build failure. `dangling-dependency`'s unique domain is therefore the `depends`/pointer binding (target never materialized, previously unchecked). Retargeted the test to assert that layering (`test_unresolved_recipe_from_is_caught_as_unresolvable`).
  - Verification: `pytest tests/test_skillware.py` 65 passed; `agentos skillware check --skill skills/agentos-skillware` back to the pre-existing 19 undeclared-dependency backlog (no new drift, `check.md` `[ok]`); depot linter 0/0/21.
