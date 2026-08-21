# 737 — Chatlas Normal Model provider boundary and Index CLI selectors

## Impl.Abstract

**Scope.** Three executable slices, in order:

1. Close the Chatlas Normal Model provider boundary. `build_normal_model` becomes internal;
   every consumer outside `chatlas/lossless/` reaches the layer through its package surface,
   and an architecture test holds that closed.
2. Convert the `tarav index` CLI to explicit named selectors, make `resolve` a point lookup,
   add targeted `linter` selection, and make `--json` presentation-only.
3. Retire Anchory's importers now that nothing reads Anchory records.

**Out of scope, deliberately.** Retiring the v1 `chatlas/` session model and flattening
`chatlas/lossless/` up into `chatlas/`. That work is real and wanted — the `lossless` name is
`chatlas2`-migration debt and the two directories hold five duplicated concepts — but it needs
a subcommand-by-subcommand equivalence mapping first, and deleting 13,179 lines of live model
before that mapping exists is the data-conservation failure this migration exists to avoid.
It gets its own `Impl.Req`. Slice 3 here removes its single largest piece.

**Status.** Slices 1 and 2 **done**. Slice 3 **blocked on a decision** — its premise does not hold; see below.

**Source context.** Continues the 641 migration. Slice 1 fixes the root cause of the
50-minute `tarav index resolve`; slice 2 fixes the corpus-wide lint on a point lookup that the
same investigation exposed.

## Impl.Index

The index is frozen (638 Invariant 1: no new grounding minted while the system converges), so
these lines carry no anchors. They are plan constraints, not landed product state.

- [CT] a consumer of `chatlas/lossless/` imports the package surface, never a submodule; the
  submodule split is layer-internal and reaching past `__init__` binds a consumer to it
- [DC] `provide_normal_model` is the canonical Normal Model read path — it reuses a fresh
  cache or transparently rebuilds a stale one; `compute_normal_model` is the diagnostic path
  that neither reads nor writes the cache
- [CT] the cache is disposable and per-session on disk, so it survives across processes; an
  in-process memo cannot substitute for asking the provider
- [DC] `LineRecord.id` is immutable record identity, `line.label` is the mutable store-unique
  public citation, `trace` is semantic lineage — a CLI selector names exactly one of these
- [CT] `--json` selects presentation, never execution; a flag that changes which checks run is
  two commands wearing one name
- [CT] a point lookup runs the checks whose subject is the selected record, not the corpus
  linter with a filter applied afterwards
- [DC] a check is record-scoped when its findings' subject is a record id; corpus-scoped
  checks read surfaces, routers, and depot structure and have no per-record subject
- [CT] positional data arguments are not used in the Index CLI; every input is a named option
- [EX] the `tarav index` CLI currently has zero test coverage — no test in `tests/` invokes it

### Hard.Evidence

Measured against the live depot (3,994 records) during design:

| fact | evidence |
|---|---|
| `index/chatlas.py:25` imports `lossless.pipeline` directly | source |
| `lossless/__init__.py` exports `provide_normal_model` and *not* `build_normal_model` | source |
| `normal_model.py:50` — `compute_normal_model` is documented as the no-cache diagnostic path | docstring |
| the wrong binding predates the rename | `856a15d` changed only `tarav.chatlas2.pipeline` → `tarav.chatlas.lossless.pipeline` |
| `test_architecture.py:131` guards direction, not depth | source |
| `linter.py:463` calls `load_session` uncached, bypassing `_SessionCache` at `linter.py:385` | source |
| 1,676 such calls per corpus lint, over 22 distinct sessions | depot scan |
| `gates.py:108` `verify_gate` calls `load_session` uncached, once per gate | source; 2,527 gates |
| `cli.py:419` calls `load_session` once per support ref, inside the print loop | source |
| `cli.py:408` returns before `_derive` (411) and `_verdicts` (425) | source |
| `_verdicts` → `lint(geo)` → `ctx.records = list(ctx.store.all())` then filters by id | `linter.py:259` |
| ten positional data arguments | `cli.py:624,628,661,671,675,685,694,698,705,715` |
| zero internal call sites use them | `grep main(["index"` over `src tests dev` → 0 |
| `tarav-hugentics/references/check.md:7` already documents `linter --depot … --anchor …` with repeated selectors | that surface prescribes targeted linting that was never implemented; it says `--anchor`, and this plan uses `--label` per the accepted selector vocabulary, so that reference is updated in slice 2 |

### Selector vocabulary

Fixed for the whole Index CLI. Precise names only — no generic `--record` or `--selector`.

| selector | names |
|---|---|
| `--label` | the mutable public citation (`^c20260820-0u`) |
| `--record-id` | the immutable record edition (`ln_…`) |
| `--trace-id` | the semantic lineage (`tr_…`) |
| `--scope` | the semantic attachment (`depot/chapter#Concept` or `@file/region`) |
| `--session` | a chat session: native id, URI, or identity hash |
| `--poi-class` / `--poi-id` | a POI class, and one POI occurrence |

## Execution.Plan

### Slice 1 — close the Normal Model provider boundary — **done**

**Do.**

- `chatlas/lossless/pipeline.py`: rename `build_normal_model` → `_build_normal_model`.
  Leave `build_normal_model_from_row` alone; it is the row-taking variant three in-layer
  callers use, and renaming it is not the minimum change. The architecture rule below covers
  it from the outside.
- `chatlas/lossless/normal_model.py`: `compute_normal_model` calls `_build_normal_model`.
- `index/chatlas.py`: import `chat_message_at`, `list_chat_messages`, `provide_normal_model`
  from `tarav.chatlas.lossless` — the package, not its submodules. Replace the
  `build_normal_model(**{selector: session_id})` call with `provide_normal_model`. Keep the
  two-selector loop (`session_id`, then `identity_hash`): a `SupportRef` may name a session
  either way and that is unchanged. Update the module docstring, which names
  `tarav.chatlas.lossless.build_normal_model`.
- `tests/test_architecture.py`: extend
  `test_the_lossless_layer_sits_on_chatlas_and_not_the_other_way` — or add a sibling — so that
  no module under `src/tarav/` outside `chatlas/lossless/` imports `tarav.chatlas.lossless.<submodule>`.
  Scope the rule to `src/`: `tests/chatlas_lossless/` legitimately tests internals.

**Check.** `provide_normal_model` returns the same `JsonObject` shape `list_chat_messages`
reads (`load_normal_model` populates `annotations.chat_messages`; verified at
`cache.py:305`). The suite stays green. `tarav index resolve` on a record with support
completes in seconds rather than minutes on the second run, once the cache is warm.

**Test (RED first).** The architecture test must fail on today's tree — write it, watch it
name `src/tarav/index/chatlas.py`, then fix the import. That is the constraint the defect
proved: not "this one import was wrong" but "a consumer must not bind to a submodule of the
layer." Stated that way, the next violation fails too.

**Risk.** First call per session materializes a cache directory under
`~/Documents/chatlas/chatlas2/model-cache/`. That is 22 sessions of one-time cost, and the
cache is disposable by design. Not a data risk.

**Deviation trigger.** If `provide_normal_model` raises where `build_normal_model` did not —
for instance on a session whose cache cannot be materialized — do not fall back to the
pipeline. Record it in `Impl.Log` and stop; a silent fallback would rebuild the bug.

### Slice 2 — Index CLI selectors, point lookup, presentation-only `--json` — **done**

**Do.**

1. **Options-only conversion.** All ten positionals become named options. None is used by any
   internal call site, so this is a pure surface change. No hidden positional compatibility.

   | command | was | becomes |
   |---|---|---|
   | `session` | `session` | `--session` (required) |
   | `messages` | `session` | `--session` (required) |
   | `record` | `--line` | `--record-id` |
   | `revise` | `line` | `--record-id` (required) |
   | `trace` | `trace` | `--trace-id` (required) |
   | `remove` | `line` | `--record-id` (required) |
   | `gate` | `line` | `--record-id` (required) |
   | `resolve` | `label` | `--label` (required) |
   | `import` | `depot_root` | `--depot-root` (required) |
   | `linter` | `lane` | `--lane dev` |
   | `bless` | `identity` | `--poi-id` (required) |
   | `explain` | `poi_class` | `--poi-class` (required) |

   `record --line`, `revise`, `remove` and `gate` all resolve through `store.get()`, which is
   keyed by record id — so `--record-id` is the accurate name and `--line` was not.

2. **`resolve --label` becomes a point lookup.** Drop `_verdicts()` from the path. It may load
   the record and derive its standing; it must not invoke the corpus linter. Its support loop
   (`cli.py:419`) resolves each session once, not once per ref.

3. **`--json` becomes presentation-only.** Text and JSON perform the same work and differ only
   in rendering. Concretely: JSON mode stops returning before `_derive`.

4. **Targeted linting.** `linter --label`/`--record-id` (both repeatable) run the checks whose
   findings are subject to the selected records, against a `LintContext` whose `records` is
   the selected subset — not the full run filtered afterwards. This needs `Check` to declare
   its scope; a `record_scoped: bool` earns its place on two independent grounds: it selects
   checks for targeted runs, and it documents which checks can produce a per-record subject at
   all. Corpus-scoped checks (surface readability, alias/block collisions, router structure)
   are not run for a targeted selection. `tarav index linter` with no selector is unchanged
   and remains the full corpus validation.

   Reject incompatible combinations explicitly: a selector on a command that does not take
   one, or `--label` together with `--record-id` naming different records, fails with a
   message that names both.

5. **Documentation.** Update `AGENTS.md` (its CLI surface notes), the Hugentics
   `references/check.md` and its `.skw/src` source — which document `--anchor` for a surface
   that never existed — and any help text or example carrying the old syntax.

**Check.** `tarav index resolve --label <L>` and `tarav index linter --label <L>` both return
in well under a second on the 3,994-record depot. `tarav index linter` alone still reports the
same verdict as before.

**Test (RED first).** The Index CLI has no tests at all today, which is why both defects
survived. Add `tests/cli/test_e2e_index.py` following the existing `test_e2e_*.py` pattern,
asserting the constraints rather than the incidents:

- every index subcommand rejects a positional data argument (exit 2) and accepts its named
  selector — the rule, iterated over the command table, so a future positional fails too;
- `--json` and text mode perform the same work: for one record, the findings reported in JSON
  equal the findings reported in text;
- **targeted lint equals filtered corpus lint.** For a sample of records,
  `linter --record-id X` returns exactly the findings a full run reports with subject X. This
  is the check that makes "do not run everything and filter" safe to assert: the fast path is
  required to agree with the slow one.

**Risk.** The targeted/corpus agreement test is the load-bearing one. If a check turns out to
need corpus context to produce a correct per-record finding, marking it record-scoped would
make the fast path disagree with the slow one — and the test catches exactly that. Resolve by
marking the check corpus-scoped, not by weakening the test.

**Deviation trigger.** If a check cannot be classified as cleanly record- or corpus-scoped,
record it in `Impl.Log` with the reason and classify it corpus-scoped. Correct and slow beats
fast and wrong.

### Slice 3 — retire Anchory's importers — **blocked**

**Do.** Nothing reads Anchory records since the 641 migration converted all 3,956 anchors to
`LineRecord`s. Retire the importers, walking outward from the leaves:

`index/record/store.py`, `chatlas/lossless/{anchory,grounding,line_manifest,chat_index,commands,__init__}.py`,
`chatlas/{anchory,anchory_batch,chat_index_apply,chat_index_audit,chat_index_render,project_index_reconciliation,commands,_command_support,__init__}.py`,
`anchory/{core,registry,commands,poi,__init__}.py`, `testing.py`, `runtime.py`.

**Check.** The suite is green with no Anchory import remaining outside the Anchory package
itself, and `tarav --help` still composes. Removing `chatlas/anchory.py` (1,671 lines) and
`chatlas/anchory_batch.py` (340) also removes the largest v1/v2 duplicated pair, which is the
prerequisite this slice contributes to the deferred flatten.

**Test.** An architecture assertion that no module outside `src/tarav/anchory/` imports it.
Same shape as slice 1's rule and for the same reason: assert the constraint, not the incident.

**Deviation trigger.** If a module turns out to still *need* Anchory — a live command with no
`LineRecord` equivalent — stop and record it. That is a migration gap, not a cleanup blocker,
and it is resolved by finishing the migration rather than by keeping the import.

#### The trigger fired. What is actually there

The "22 importers" in the plan came from grepping for the *word* `anchory`. That over-counted:
inside `src/tarav/index/`, every occurrence is a **comment** recording migration history, and
each is still true. **The index imports Anchory nowhere.** That part of the retirement is
already complete and needs no work.

What remains is not a set of stale importers. It is the Anchory subsystem and its two Chatlas
integrations, and all three back **live command trees**:

```
tarav anchory          register | resolve | query | amend | check | scan | namespace
tarav chatlas anchory  preview | register | support | resolve | batch
tarav chatlas2 anchory (the lossless dossier path)
```

Ten real imports across `runtime.py`, `chatlas/`, and `chatlas/lossless/`, over
`src/tarav/anchory/` (1,565 lines) plus `chatlas/anchory.py` (1,671),
`chatlas/anchory_batch.py` (340) and `chatlas/lossless/anchory.py` (1,072).

**Why this needs a decision rather than a corrective action.** `tarav chatlas2 anchory` is how
Hugentic capture mints grounding dossiers — `references/check.md` step 3 resolves them, and the
real-time grounding module writes them. Capture is *frozen*, not retired: no new grounding is
being minted while the index converges. Retiring Anchory now removes the writing path before
its replacement exists, and "nothing reads it today" is true only because the system is paused.

Anchory is obsolete **as a design** — that was settled, and its data is migrated. It is not yet
obsolete **as the capture path**. Closing that gap is what unfreezes the index, and it is a
larger piece of the migration than a cleanup slice.

Nothing was deleted. The three modules are still there, still reachable, still tested.

## Impl.Log

### Slice 1 result

Landed as planned, plus one thing the plan did not anticipate.

The architecture rule went RED naming three offenders, not one: `index/chatlas.py` on both
`lossless.messages` and `lossless.pipeline`, and `chatlas/commands.py` on `lossless.commands`.
All three now import the package surface, which already exported everything they needed.

**Measured, and the first measurement was misleading.** A cold pass showed the cached path
*slower* than the uncached one — because that pass was paying the one-time cache
materialization. Warm, on the three hottest gate sessions:

| | uncached (`compute_normal_model`) | cached (`provide_normal_model`) |
|---|---|---|
| `4d13d871` | 0.54s | 0.09s |
| `c9c843d6` | 0.62s | 0.10s |
| `29bf3344` | 0.49s | 0.08s |

About 6–7x, once per session rather than once per call.

**A second defect, found while verifying.** With the model load down to 0.09s, `load_session`
still took 0.50s. `chat_message_at` walks the whole event tape per message — 791 messages
against 8,463 events. Added `chat_message_times(model)` beside it in the layer, which indexes
the tape once; `load_session` asks once per session. `load_session` on the hottest session:
0.50s → 0.47s, and 0.36s → 0.26s on the next. Smaller than expected — the remaining cost is
`list_chat_messages`' deepcopy, not the scan — so this is a real but modest win, recorded here
rather than claimed as the fix.

Its test asserts the constraint rather than the incident: the batched form must agree with the
single form for *every* message, absent times included. Writing it caught a collision in the
existing fixture, where `chr(100 + index)` already claims the address the orphan case wanted.

**Not done, deliberately.** `provide_normal_model_reader(...).iter_chat_message_records()` is
another 2x over the full model load (0.04s vs 0.09s), but `load_session` needs event times too,
so using it means resolving `at` a different way. Out of the minimum change; noted.

### Slice 2 result

Measured on the live corpus (3,993 records, 2,527 gates):

| | before | after |
|---|---|---|
| `resolve --label` | over two minutes | **1.23s** |
| `linter --label` (targeted) | did not exist | **1.22s**, 16 of 31 checks, 1 record |
| `linter` (full corpus) | ~50 min | **38s** |

The corpus run producing **the identical 14,964 findings** before and after, and a targeted
run agreeing with it on **30 randomly sampled live records**, are what make the speed
meaningful rather than merely faster.

**The design changed under measurement, twice, and both times the live check found it.**

The plan proposed a declared `record_scoped: bool` on each catalog entry. Deriving it instead
from which iterator the body uses is better — the check declares its scope by how it is
written, and there is no second copy to drift. But reading only the top-level body was wrong
in two ways the synthetic fixture could not see:

1. `gate-verifies` and its dev counterpart are two-line wrappers over one shared body, so both
   read as corpus-scoped. Every `Gate.Evidence.Invalid` finding — 2,143 of them — vanished from
   targeted runs. Found by comparing against the live corpus, not by the unit test.
2. `line-drift`, `scope-kind` and `review-closure` reach records *sideways*, through a surface
   line's label or a trace's members, so they never iterate records at all. Found by adding a
   gated record to the fixture.

Fixed by following the derivation through module-local helpers, and by giving the sideways
checks `ctx.is_selected()`. 19 of 31 checks are now record-scoped.

The general form is now asserted structurally: **no corpus-scoped check may name a record as
its finding subject**, because such a finding is one a targeted run can never produce. That
test would have caught both defects, and will catch the third.

**A third thing the slice needed that the plan did not name.** The structural tier has to run
in every mode: it is what reads the surfaces and loads the records. Excluded, a targeted run
examined an empty corpus and reported it clean — the exact failure the whole design exists to
avoid, reached by trying to avoid it.

**Where the time actually went.** Not the corpus scan. `_check_review_covers_support` and
`_gate_findings` each asked the archive per record for sessions the corpus names only 22 of.
Routing both through the existing `_SessionCache` — which sat 70 lines above one of them,
written for this — is most of the 50-minutes-to-38-seconds. `verify_gate` gained a `load`
parameter so a caller verifying thousands of gates can supply the read.

**Also landed:** `record --json` and `resolve --json` now report the standing and error bars
text mode reports. `write --trace` became `--trace-id` for one vocabulary. An unmatched
selector fails rather than reporting a clean run. `tarav-hugentics/references/check.md` and its
`.skw` source documented `linter --depot … --anchor …`, a surface that never existed; both now
say `--label`, and `skillware check` reports the file clean.

**Presumption (`Index.Presumption`, not touched authority).** Slice 2's split of checks into
record- and corpus-scoped is my classification, derived from reading each check body for
whether it consumes `ctx.records`. It is agent judgment over the current code, not a user
decision. The targeted-equals-filtered test exists precisely because that judgment needs a
check standing next to it.

**Correction carried in from design.** An earlier statement in this session said
`tarav index resolve` writes records. It does not — the whole path is read-only. The depot
growth from 3,974 to 3,994 was a parallel actor deliberately landing 19 index lines
(`9baec00`) plus one probe record (`c3325ab`). The performance cost is real; the write claim
was not.

**Open, not scheduled here.** `c3325ab`'s probe record `ln_35847d29536ae8f7` was later
overwritten with a real body and now duplicates `ln_ef2f22abe8c03c5a` under label
`^c20260820-0u`. Also, that actor writes shards as compact single-line JSON while every
migrated record is indented — two serializers on one depot. Both are noted for the migration
queue, neither is touched by this artifact.

**Deferred with its rationale.** The `lossless` → flatten work is out of scope above. The six
colliding filenames between `chatlas/` and `chatlas/lossless/` (`anchory`, `chat_index`,
`chat_index_plan`, `commands`, `event_ref`, `query`) are not an obstacle to the flatten — they
are five concepts implemented twice plus the composition point. Retire v1 and the flatten
needs no invented name. What it needs first is the equivalence mapping.
