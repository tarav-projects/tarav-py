# 740 — The grounded Blessing.Record

## Impl.Abstract

Replace the gate-based, project-local blessing with a **grounded `Blessing.Record`**: a free
`Index.Line` carrying an agent's one-line explanation plus a `User.Touched` support set, naming
the `POI.Instance` it accepts, stored in its own Bloberia depot beside the `LineRecord`s.

A blessing stops being *the user approved this* and becomes *the agent claims this, and here is
the touched evidence it rests on*. Nothing stores whether a blessing is valid; that is derived
from whether its support resolves and qualifies, exactly as `LineRecord` standing is derived.

This requirement also adds `POI.Test`: a summonable finding that makes the linter's own
behaviour — selection, targeting, reporting, and now blessing — exercisable against a real
corpus. It is a general linter-development facility, not a fixture for one test.

Scope excludes: record-level project ownership (parked by 739), blessing concentration
reporting, and any migration path — **zero blessings exist today**, verified across the whole
worktree, so the old format is deleted rather than carried.

## Impl.Index

- [DC] a blessing is an `Agent.Claim`, not a user review: the record carries the agent's own
  one-line explanation of why it blessed, plus a `User.Touched` `Support.Set`
- [CT] the `Blessing.Record` must carry everything the linter needs both to *read* the blessing
  and to *run checks on the blessing itself*
- [DC] the record stores no validity flag; whether a blessing silences its POI is derived from
  its support, the same rule that makes `LineRecord` carry no `head` or `reviewed` field
- [CT] a grounded blessing carries `Touched.Authority` and silences its POI; an ungrounded one
  is an `Index.Presumption`, silences nothing, and is itself a finding
- [DC] the explanation is a **free** `Index.Line` — it has no scope, and freeness is a property
  of the host rather than a field on the line
- [RJ] no `ScopeKind` for POI instances: a scope kind would make freeness a blessing-shaped
  special case instead of a general capability
- [CT] `Record.Unplaced` and every other surface check binds to its host, so a check that asks
  "is this line placed?" is simply never offered the blessing depot
- [DC] blessings live in their own Bloberia depot beside the record depot, carrying no project
  data: the POI identity is already global because its subject is a depot-global record id
- [CT] a `Support.Set` is never mechanically checked for *relevance* — that is the
  `Semantic.Assertion` the record exists to make auditable later, and it is true of every
  support set, not only a blessing's
- [PR] a finding about a blessing is not itself blessable, or the grounding requirement is
  answered by another ungrounded blessing and becomes decorative
- [DC] `POI.Test` is a general mechanism for working on and testing the linter, so it is a
  documented durable check with named probes rather than a fixture

### Presumptions

- [PR] the blessing depot is separate from the record depot rather than sharing it under a
  discriminator, because a shared depot would put blessings in front of every check that
  iterates records and make host-bound applicability a filter rather than a structure
- [PR] `bless` does not verify at write time that its POI occurs: the orphan is a derived
  condition like every other, and write-time verification would cost a full corpus lint

## Execution.Plan

### Slice 1 — `POI.Test`, the summonable finding — **done**

The instrument comes first: every later slice is verified with it.

- Add a marker constant and a `poi-test` check that scans the raw text of every discovered
  surface file for the marker, with an optional `#<tag>` suffix naming the probe.
- Subject is `<surface>#<tag>` — deliberately not `<scope>:<lineno>` like the other surface
  checks, because this POI must stay blessed while the file is edited around it.
- Assemble the marker from parts in its own module so the defining file never matches itself.
- Register it with `why` and `resolutions` like every other check.

**Check:** a fixture surface containing the marker yields exactly one finding; two distinct
tags yield two independent findings; the identity is unchanged after an unrelated edit to the
same file that moves the marker's line number.

### Slice 2 — `BlessingRecord` and its depot — **done**

- `record/blessing.py`: `BlessingRecord(id, poi, line, support)` on schema
  `tarav.index-blessing-record.v1`, reusing the existing `Line` and `SupportRef` primitives.
- `BlessingStore` over a Bloberia shards depot keyed by `id`, with `Geography.blessing_depot`
  following the same public-path-unless-overridden rule as `index_depot`.

**Check:** round-trips through the depot; a blessing written under a test `TARAV_INDEX_HOME`
never appears in the index record depot, and vice versa.

### Slice 3 — derived standing, and the checks on the blessing itself — **done**

- `blessing_standing()`: resolves each support ref and reports grounded / ungrounded /
  unresolved / untouched. No stored flag anywhere.
- `lint()` consults the blessing store instead of `blessed.json`; a grounded blessing moves its
  finding to the `blessed` lane, anything else leaves the finding standing and emits its own.
- New POI classes: `Blessing.Ungrounded`, `Blessing.Support.Unresolved`,
  `Blessing.Support.Untouched`, `Blessing.Orphaned`.
- Delete `_blessings_path`, `read_blessings`, `_blessing_holds`, the `GateRef` parameter on
  `bless`, and `Index.Linter/Blessing.Unevidenced`.
- Exclude every `Blessing.*` class from blessing application.

**Check (RED then GREEN per condition):** a blessing with resolving user-side support silences
its POI and no other; one with no support does not silence and reports `Blessing.Ungrounded`;
one whose ref does not resolve reports `Blessing.Support.Unresolved`; one grounded on an agent
turn reports `Blessing.Support.Untouched`; one naming an absent POI reports `Blessing.Orphaned`;
and a `Blessing.*` finding cannot itself be blessed.

### Slice 4 — the CLI — **done**

- `tarav index bless --poi-id --body [--type] --session --support ...` writes the record and
  immediately prints its derived standing, following `gate`'s report-don't-refuse shape.
- `bless` leaves `PROJECT_COMMANDS`: it writes to the depot, so the coupling 739's contract was
  removing is gone rather than satisfied.
- `tarav index blessings [--poi-id]` lists blessings with their derived standing.

**Check:** end-to-end through `POI.Test` on a fixture project — summon two probes, bless one,
confirm it is reported `blessed` while the other stays `failed`, and confirm the blessing
survives a re-run.

### Slice 5 — close the visited surfaces — **done**

- Update `AGENTS.md`, the architecture notes, and the CLI contract section.
- Run the focused Index/CLI suites, then the full suite and ruff.
- Audit changed product surfaces, mint the line-dossier batch for this artifact's `Impl.Index`,
  and backpropagate.

## Impl.Log

- [TS] Execution of Impl.Req 740 is authorized by the tarav-hugentics `--impl --dev --AUTO`
  invocation.
- [OBS] Verified before designing: no `blessed.json` exists anywhere in the worktree and the
  current corpus lint reports 0 blessed instances of 16,600. The old format has no data.
- [OBS] The worktree already contains concurrent Index work from 739 (report model, capture,
  linter resolution) plus this session's `--project` conversion. All of it is shared state and
  must be preserved.
- [OBS] `Finding.identity` is `sha256(poi_class, subject, surface)` and deliberately excludes
  `operands`, so a blessing already survives the accepted value drifting. Slice 1's subject
  choice extends that same intent to the marker's line number.
- [PR] The support-message addresses selected as grounding for `Impl.Index`, to be minted at
  slice close, all in session `9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5`:
  `f3822a678124f3a4` (bloberia, Stable Surface, Chat.Surface context, no project data),
  `270f6e0ef6222c6e` (agent claim, support set, like an Index Line, checks on the blessing),
  `5ed6bf744b083ebb` (free Index.Line, explanation indexes the explanation, later audit),
  `12809a93bbc1c381` (blessings can be free lines, other surfaces do not allow them),
  `8289ebbfa6696847` (create a POI that is a test),
  `57719fe142be2895` (a general mechanism for working and testing the linter).

- [TS] Slice 1 green: 4 probe tests plus a registry-order guard; `poi-test` reports clean on
  the live 92-surface corpus, confirming the marker never matches by accident.
- [OBS] **Deviation, corrected.** Building the probe exposed a defect in `select_checks`
  outside the plan: `--check <name>` did not select the structural tier, so the named check
  ran against an empty `LintContext` and reported clean. Measured on the live corpus,
  `--check line-typed` reported **0** where the full run reports **1,362**. This is the same
  failure the targeted branch already refuses two lines above, arriving by the other selector.
  Structural checks are now always selected; `test_a_dev_check_cannot_be_summoned_by_name`
  was restated to assert the dev check's absence from the selection rather than an empty one.
- [OBS] Registry order is load order, and only the ordering of `CHECK_REGISTRY` enforced it.
  `poi-test` first shipped finding nothing because it was registered above the structural
  check that fills `ctx.surface_lines`. The constraint is now asserted from `co_names` for
  every check, not patched for this one.

- [TS] Slice 2 green: `BlessingRecord` and `BlessingStore` on
  `tarav.index-blessing-record.v1`, in `~/Documents/bloberia/tarav-blessings`. The depot is
  lazy — a corpus lint with no blessings never creates it.
- [TS] Slice 3 green: seven behaviour tests over grounded, ungrounded, unresolved, untouched,
  orphaned, sibling-independence, and the recursion guard.
- [TS] Slice 4 green: the full loop through the real CLI and the **real** chat archive on an
  isolated depot — two probes summoned, one blessed on message
  `8289ebbf…` of this session, re-lint reporting `blessed` for it and `failed` for its
  sibling; the ungrounded case reporting `ungrounded` and `Blessing.Ungrounded`; and removing
  the blessed probe producing `Blessing.Orphaned`.
- [TS] Full suite 2,187 passed; ruff clean. Live corpus lint unchanged except for concurrent
  work by another agent (`Gate.Contradicted` renamed to `Gate.Evidence.Invalid` and three new
  records), both confirmed present in the pre-execution checkpoint rather than caused here.
- [OBS] **Deviation, corrected.** `explain` could not find the new POI classes: they were
  built by f-string, and class identities are read off `co_consts` as literals. Restructured
  to explicit literals. The same reading exposed a better home for orphan detection — see
  below — so the defect was worth more than its fix.
- [DC] `Blessing.Orphaned` became a real registered check rather than a post-loop pass in
  `lint`. `LintContext` gained `produced`, filled by the run as each check returns, and the
  check is registered last and reads it. This is the same load-order mechanism the structural
  checks already use, so the whole-run question needed no new machinery.
- [DC] The orphan check declares a gate and reports **blocked** on a narrowed run rather than
  answering. On `--check blessing-orphaned` almost nothing is produced, so every blessing
  would look orphaned; `blocked` is what the three-valued vocabulary exists to say.
- [OBS] Timing comparisons taken during this execution are unreliable: another agent was
  working the same tree throughout. The probe's own cost is bounded by the 0.46 MB of text
  across the corpus's 92 discovered surfaces.
- [OBS] A block replacement while rewriting `TestBlessingEvidence` silently deleted three
  test classes added earlier in the same session. Caught by inventorying test classes rather
  than by the suite, which stayed green because deleted tests do not fail. Restored.
- [TS] Product.Surface capture closed: two product claims on `record/blessing.py` minted as
  `^c20260821-35u` and `^c20260821-36u`, both resolving `MATCHED/user` against this session.
  Backpropagation applied with `audit.ok: True`, `missing_head: []`, `missing_delta: []`,
  `head_only_gaps: []`, and both lines placed on the Delta tape rather than head-only.
- [DC] The `[DF]` annotation on `tests/index/test_blessing.py` is left unanchored, matching
  its siblings: a file-description line is below the capture bar, and 55% of the product
  annotations in `src/` carry no anchor for the same reason.
- [TS] Final: 2,187 tests passed, ruff clean.

### Slice 6 — POI class catalog reconciliation — **done**

- [OBS] **Defect, found by review rather than by the suite.** POI class identity is the
  Wayfinder reference of its one managed `$kw` block in the codebase, and two of the classes
  this requirement emits had none: `Blessing.Support.Unresolved` and
  `Blessing.Support.Untouched` resolved to a `Wayfinder.Resolution.POI` instead of a block.
  The report builds the reference from the class name, so a dangling identity renders exactly
  like a good one until something resolves it — which is why nothing failed.
- [DC] Each class now has its own small emitter carrying its own `$kw` block, which is the
  convention every other multi-class check in the module already follows and the reason
  `_referenced_poi_classes` walks module-local callables transitively.
- [OBS] `Index.Linter/Blessing.Unevidenced` was left declared after its gate-era check was
  deleted — a block declaring a class nothing can emit. Removed.
- [TS] Two guards added and mutation-checked: every emitted class declares its managed block,
  and a *bare* declaration nothing emits is stale. The second holds only bare annotations to
  the rule, because one carrying a `--note` is a deliberate statement about a class agents
  raise (`Class.Review`) rather than a leftover — derived from the annotation instead of a
  maintained allowlist.
- [OBS] Two Skillware POIs on `record/blessing.py` were also mine and are fixed: a second
  file-header `$kw` with no host point (now one annotation with a `--note` continuation), and
  `--from Index.Line.Record`, which is dangling — the block is `Index.Line.Record.Model`. The
  same dangling name remains in `standing.py`, `record/model.py`, `record/__init__.py`, and
  `capture.py`; those are pre-existing and out of scope here.
- [TS] Project `skw check` POIs 216 → 214; none now touch this requirement's files except
  three `Annotation.NonSkw` on ordinary comments, of 174 project-wide.
- [TS] Final: 2,189 tests passed, ruff clean.

### Slice 7 — every POI class defined beside its code — **done**

- [DC] A POI class is defined by the managed `$kw` block beside the code that emits it, in
  every namespace. The markdown `poi/` chapter path stays discoverable but is not the
  executable definition, so a class defined there instead is not defined at all.
- [TS] Survey of all 135 POI classes across `Index.Linter`, `Skillware.Linter`,
  `Anchory.Linter`, `Bloberia.Linter`, `Canvas.Linter`, and `Tournament.Linter`: eight were
  undeclared — five Canvas, three Tournament — and both modules built their references with
  the package-skill form rather than `tarav_poi_class_reference`.
- [DC] Canvas's five moved out of `tarav-canvas-md/skills/tarav-canvas-pkg/poi/100-poi.md`
  into per-class emitters; the markdown definitions and their router entry are removed, and
  their `[DF]`/`[CT]` text is carried into the `$kw` notes verbatim. Canvas also had to
  compose `create_tarav_wayfinder`, since the index-block wayfinder cannot resolve a
  `managed.block`.
- [OBS] Keeping both copies was not neutral: with the class defined in markdown *and* in
  code, Wayfinder reported `resolves more than once` and the reference resolved to neither.
  A duplicate definition is an unresolvable identity, not redundant documentation.
- [OBS] Tournament's three resolved to nothing at all — `tarav-md/skills/tarav-pkg/poi/` is
  an empty directory, so its package-skill references had no target.
- [OBS] `Index.Linter/Class.Review` was annotated above `CHECK_REGISTRY`, a module-level
  constant, which is not one of the configured attachment points (`file`, `class`,
  `function`). It never resolved; nothing checked. Moved to the module's file point, text and
  anchor unchanged. (Restoring it after my own edit displaced it proved the placement, not
  the displacement, was the defect.)
- [TS] Two system-wide guards in `test_architecture.py`, both mutation-checked: every emitted
  class declares its block, and every declared class resolves to *exactly one* managed block.
  The second first shipped passing because `wayfinder.resolve` **returns** an unresolvable
  reference as a POI rather than raising — checking only for an exception asserted nothing.
- [DC] The Index-only version of the first guard is removed as subsumed; what stays in
  `test_linter.py` is the one thing only that registry can answer — a declaration outliving
  the check that emitted it.
- [TS] Final: 135/135 POI classes resolve to a managed block. 2,195 tests passed, ruff clean
  across every file this requirement touched.

### Slice 8 — `Current.Model.Only` applied to support resolution — **done**

- [DC] `Index.Linter/Support.LegacyCoordinate` is removed. `Current.Model.Only` `^c20260820-31u`
  says the checker names the mechanical failure and never its historical cause, and
  `^c20260820-35u` names this exact case: references addressing Chatlas1 turns "fail the
  current reference assertion exactly as any unresolvable address does" and are "not a
  category the linter knows".
- [RJ] The branch it hung on — `if ref.archive != CHAT_ARCHIVE` — is deleted rather than
  renamed. A legacy branch is a second model the checker would carry and keep correct forever
  (`^c20260820-32u`); the refs now flow through the one assertion.
- [DC] `Support.Mismatch` is renamed `Support.Unresolved`. "Mismatch" asserts the evidence
  *changed*, which the walk does not establish and which is false for every reference
  addressing a superseded model — and 3,632 of those were about to enter it. The archive the
  reference names is preserved in the operands, so the migration backlog stays legible
  without a class of its own.
- [TS] Live corpus, measured: `Support.LegacyCoordinate` 3,666 blocked → gone;
  `Support.Unresolved` **3,632 failed**; `Support.Unreachable` 47 blocked, those being the
  sessions the archive genuinely cannot read. Corpus blocked **3,666 → 47**, failed
  **12,958 → 16,614**. The non-conformant count is now the migration's progress measure
  (`^c20260820-33u`) instead of an excluded category.
- [TS] A guard in `test_architecture.py` refuses any POI class naming a superseded model,
  mutation-checked by reintroducing the old name.
- [OBS] It immediately found four more. Three (`Anchor.LegacySigil`, `Router.LegacyName`,
  `TypeStatement.LegacySigil`) live in `index/historical_poi.py`, whose whole purpose is
  keeping already-emitted instances resolvable and which produces nothing; the guard scopes
  to producers, derived from that module rather than an allowlist.
- [DC] The fourth, `Skillware.Linter/Callout.Legacy`, is a live producer and a real
  violation: renamed `Skillware.Linter/Callout.Inert`, which is what its own `[DF]` already
  said the parser found. Its producer finding *kind* `legacy-callout` is Skillware's separate
  vocabulary and is untouched, so that package's documented catalog and tests are unaffected.
- [TS] 2,196 tests passed, ruff clean.
