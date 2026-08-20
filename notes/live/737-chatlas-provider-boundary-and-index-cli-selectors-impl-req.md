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

**Status.** Slices 1–3 not started.

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

### Slice 1 — close the Normal Model provider boundary

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

### Slice 2 — Index CLI selectors, point lookup, presentation-only `--json`

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

### Slice 3 — retire Anchory's importers

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

## Impl.Log

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
