# Record loading workflow — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: complete, 2026-10-18.
Knowledge.Surface: wiki.
Alignment.Mode: autonomous.

Make loading an instance from a record one standard kernel pipeline, and stop
treating the record as runtime state. Runtime checking keeps only pydantic's
strict parse; the "validation changed nothing" comparison and the defensive
copies go. The pipeline carries a `RecordLoadingContext` (configuration and
partial state) and hands the Type's builder a `LoadedRecord` (the parsed
pydantic model plus typed loading metadata). Check levels exist only inside
loading. `_record` is removed: Types keep their own state.

Non-goals: default pytests about pydantic features (dropped by the User),
configuration set for a block of code, a mirrored write pipeline beyond the
write check, faster Chatlas stream reads through check levels (follow-up).
<!-- tarav.breadcrumb 51a88542d026 -->
<!-- tarav.breadcrumb f48ff8e6ab86 -->

## Design

### Why

Reading one large cached Chat.Turn cost 1,623 µs against 54 µs for its
`json.loads`. `validate_record` makes two deep copies, a strict pydantic
validation, a dump, and two sorted serializations compared for equality; the
Normal Model reads ran it twice per row (`from_record` then `to_record`). Only
the pydantic step (about 130 µs) is wanted at runtime.

The "RecordInterface must not transform or discard supplied data" runtime
check has no User grounding. On 2026-09-19 the User asked for a test, "json0
-> class -> json1 -> class -> json3 … for all registered class", "a minimum
default test" (codex session `01a0af61-72e2-7bd2-94a3-26529d6914ec`, turns
`d13375746bf42765` and `f7163a36d8e7eaec`); request 800 recorded it as "not a
runtime startup check". Commit `7430d48` added that test and, unrequested,
the same idea inside every `validate_record`.
<!-- tarav.breadcrumb faf60648b15d -->

### Decisions (User)

- On loading, JSON-ness needs no check: the parser already produced JSON. The
  shape is what validation means. The no-transformation check goes.
  <!-- tarav.breadcrumb 9f857fa1cd95 -->
- Keep only the pydantic step at runtime, used in a limiting fashion; pydantic
  as an accept/reject gate on the original dict, avoiding copying and
  allocating data.
  <!-- tarav.breadcrumb 951210cfc133 -->
  <!-- tarav.breadcrumb 425f710f8cce -->
- The step is parsing, from the raw JSON dict to typed data, not only
  validation. The record data is not the runtime source of truth: instances
  can exist without ever producing a record; the record is only for loading
  and creating an instance.
  <!-- tarav.breadcrumb f47a195ff8ab -->
- Loading from a record is a standard pipeline up to the Type's constructor:
  record → pydantic → a standardized loaded object → instance. It is the
  official road from a record, not the only way to build an instance.
  <!-- tarav.breadcrumb e511957545e5 -->
  <!-- tarav.breadcrumb 8411c090baed -->
- The pipeline fills one object step by step (read the JSON from disk or take
  it directly, the pydantic model, …) and carries configuration the steps
  react to.
  <!-- tarav.breadcrumb 0e6bcd477124 -->
- An internal, non-raising path returns that object; the public path raises,
  so instances never recheck. The carried object is `RecordLoadingContext`;
  the constructor receives a `LoadedRecord`, always valid, produced from the
  context when all is good.
  <!-- tarav.breadcrumb a852bd94bab3 -->
  <!-- tarav.breadcrumb e37d5291fa11 -->
- Check levels (lite, default, full, and none) are defined by Types, all the
  same by default, and configured on the loading machinery. They do not pass
  the loading phase: no rechecking, no level on `LoadedRecord`; whoever
  disables checks is responsible. A separate guard sits on writing, not on
  construction.
  <!-- tarav.breadcrumb ef26490dfa85 -->
  <!-- tarav.breadcrumb 7307870d8a00 -->
- `LoadedRecord` keeps the typed data, directly the pydantic model, not
  copied; constructors populate fields from it. It also keeps loading
  metadata, by default `source`, injected and controlled by the loading
  system and its configuration. An instance errors itself if something it
  requires is missing.
  <!-- tarav.breadcrumb 9fa9e40ee5e2 -->
  <!-- tarav.breadcrumb 73b3b33df324 -->
  <!-- tarav.breadcrumb eef1ee84c4cd -->
- The metadata is a small typed object; sharing without copying is fine; no
  freezing: those objects belong to the loading workflow and nobody touches
  them outside a constructor.
  <!-- tarav.breadcrumb 803995bde5a5 -->
- Writing: the Type provides a record dict and a similar check runs.
  `_record` is removed; the `.records` namespace and the hooks stay: the
  builder, the record provider, the record example provider. Types are full
  classes; their state does not live on a record because that is how they are
  loaded or stored.
  <!-- tarav.breadcrumb 22456e35d639 -->
  <!-- tarav.breadcrumb 308e2a7cc2d2 -->
- Configuration lives on the loading context object; connecting it to
  callers is allowed when needed. No configuration for a block of code, and
  no default pytests about pydantic features.
  <!-- tarav.breadcrumb 6033856d9952 -->

### Agent decisions

- Module: `tarav.l0.kernel.loading` holds `RecordLoadingConfig` (frozen:
  `level`, `source`), `LoadingMetadata` (frozen: `source: Path | None`),
  `LoadedRecord` (frozen: `data`, `metadata`), `RecordLoadingContext`
  (mutable: `config`, `path`, `record`, `record_type`, `data`, `instance`,
  `stage`, `error`) and the steps: read, resolve the Type, check the Type
  reference, parse, build. `RecordLoadingContext` is discarded after the
  build.
- Public loading (`Type.records.from_record`, `TypeRegistry.from_record`,
  `TypeRegistry.load`) raises the original exception, so callers' `except`
  clauses keep working, with a note naming the failed step and source. The
  internal path returns the context with `error` set.
- `validate_record` becomes `parse_record`: one strict `model_validate` of
  the original dict, returning the model. Writing (`to_record`) keeps the
  JSON copy of the provided dict (detaching it from instance state) and parses
  it at `default`.
- The builder hook keeps its name, `_from_record`, and now receives a
  `LoadedRecord`; overrides read `loaded.data`. The kernel loader no longer
  assigns `source`; `DirectoryRecord` and other Types that need it take it
  from `loaded.metadata.source` in their builder. `TaravObject` keeps its
  `source` attribute, which non-loading code also sets.
- Levels: `none` uses `RecordInterface.model_construct` (nested values stay
  raw; the caller's responsibility), `default` the strict parse; `lite` and
  `full` call the Type's `Records._parse_lite` / `_parse_full`, which default
  to the strict parse.
- Types whose whole state is their record data (Chat.Turn, Chat.Message,
  events, skw code nodes, scoring records, …) keep the parsed model as their
  state through a kernel helper, and write it back with
  `model_dump(mode="json", exclude_unset=True, by_alias=True)`. Types with
  real attributes write those.
- An architecture test forbids `._record` anywhere in `src`.
- Chatlas Normal Model streams parse each row once with `parse_record` and
  return the original row.

## Current implementation observations

Inspected 2026-10-18:

- `src/tarav/l0/kernel/records.py`: `TaravObject.Records.validate_record`,
  `from_record` (keeps `result._record`), `to_record`, `_from_record`,
  default `_to_record` (echoes `_record`; its docstring: "serves only Types
  not yet migrated to state"), `_json_object`, `_json_load_record`,
  `_load_record` (assigns `result.source`), `DirectoryRecord.directory`.
- `src/tarav/l0/kernel/types.py`: `TypeRegistry.load`, `from_record`,
  `_construct`.
- 59 `_from_record` overrides in 40 files; 69 `validate_record` callers;
  144 `._record` reads outside the kernel (`l2/lines/records.py` 54,
  `l1/skw/document.py` 16, `l2/unsorted/records.py` 12,
  `l2/unsorted/authorization.py` 12, …); 53 registered Types with fields rely
  on the `_record` echo when writing.
- `tests/kernel/test_object_record_contract.py`: example → instance →
  `to_record` == example for every registered Type; two tests assert
  `_record` behavior that this request removes.
- Measured: `validate_record` 680 µs, strict `model_validate` 133 µs,
  `json.loads` 54 µs on a 40 KB turn.

## Impl.Req.Wiki

- Product project: `tarav-py`. Wiki owner: `tarav-md` (`notes/wiki/`).
- Relevant note: `tarav-py/notes/wiki/record-interfaces.md` (Record
  interfaces), `tarav-md/notes/wiki/chatlas-normal-model.md`.
- Supporting chat: `claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479`.
- Capture status: see Impl.Log.

## Execution.Plan

Core data shape: `RecordLoadingConfig`, `RecordLoadingContext`,
`LoadedRecord(data, metadata: LoadingMetadata(source))`.

1. Performance/refactor — the parse step only. `parse_record` replaces
   `validate_record` (callers migrated); no copies or comparison on loading;
   Chatlas rows parsed once. Check: full suite; micro-benchmark before and
   after. Status: done (cbf7d60).
2. Feature — the loading pipeline. `tarav.l0.kernel.loading`; builders
   receive `LoadedRecord`; `source` through metadata. Check: new
   `tests/kernel/test_record_loading.py`; full suite. Status: done (d0f6845, 9e4cf79).
3. Feature — check levels on `RecordLoadingConfig`. Check: tests for
   `none`, `default`, a Type-defined `lite`/`full`. Status: done (bb64f64).
4. Refactor — `_record` removed. Types migrated to own state; the record
   contract test drives the list; architecture test forbids `._record`.
   Check: full suite. Status: done (ba5d9d6).
5. Docs — ARCHITECTURE, AGENTS (Skillware source) if the contract text
   changes, Wiki capture. Status: done.

Deviation triggers: a Type whose round trip cannot hold without the stored
record; consumers outside tarav-py reading `_record`.

## Impl.Log

- 2026-10-18: request written by the designing Agent in the session above.
- 2026-10-18, Execute (same session, cold reload). Start checkpoints:
  tarav-py c91b595, tarav-md 2089246 (empty).
- Slice 1: `parse_record` replaces `validate_record` (15 files);
  assertions of the removed transformation check dropped from
  `test_entity.py`, `test_record_interface.py`. Normal Model rows parsed once.
  A 40 KB turn row read: 1,623 µs before, 230 µs after (machine slower that
  run: `json.loads` 94 µs against 54 µs). Real search: messages 30.6 s →
  12.9 s, turns 88.3 s → 24.8 s. Suite 349 passed. Commit cbf7d60.
- Slice 2: `tarav.l0.kernel.loading`; 53 files' builders migrated to
  `loaded.data` by script. Removing the loader's `source` injection broke 24
  tests: DirectoryRecords whose `TaravEntity` builder skips `super()`, and
  Projects. Deviation: instead of a `DirectoryRecord` builder, storage-shaped
  Types declare `keeps_source` (`FileRecord`, `DirectoryRecord`,
  `TaravProject`) and the build step gives them the metadata source.
  `tests/kernel/test_record_loading.py` 4 passed. Commit d0f6845.
- Found: `pyproject.toml` `testpaths` lists test files explicitly, so the
  tests added by requests 919–921 had not run in the default suite (they had
  been run separately each time). Added; the Search runtime test now checks
  independence instead of an empty engine registry (broken by request 920's
  registration, found with a worktree bisect). Two `test_project_dev.py`
  failures and three `tests/scoring/test_assertion_objects.py` failures come
  from other commits (2a5eab5 and earlier) and are outside `testpaths`.
  Commit 9e4cf79; suite 373 passed.
- Slice 3: `RecordLoadingConfig.level`; 3 level tests failed first, then 7
  passed. Commit bb64f64; suite 376 passed.
- Slice 4: kernel stops keeping `_record` and echoing it. A round-trip
  script listed 73 failing Types, then 0 after the migration; a scan of all
  `TaravObject` subclasses found 9 unregistered Diagram Types relying on the
  echo too. Patterns: `TypedState` (Chatlas records, Normal Model,
  breadcrumbs, decisions, Skillware annotations and reading entries, Archive
  artifact records, scoring details and cases, Diagram capture, view and
  draft records); own JSON document as `_fields` (`SkwBlock`, `ScoringRecord`,
  the `Reference` family, `TypedShip`/`TypedAnnotation`), keeping References
  constructible from unchecked input as before; attributes with an explicit
  writer (`GitRepository`, `RankingScore`). The test-suite ratchet
  `RECORD_STATE_DEBT` was paid off and replaced by "no object keeps its
  Record"; an architecture test forbids `._record` in `src`. Another
  session's unsubmitted marker in `tests/test_architecture.py` was registered
  with its own session (`473c89a0`). Whole test tree: 520 passed, the 5
  failures above remaining. Commit ba5d9d6.
- Side request 922 (cached Turns in the chatlas-context audit): commits
  ad89cc7, 1a92ab5.
- Slice 5: ARCHITECTURE describes the loading workflow (3 Breadcrumbs; the
  ARCHITECTURE.md audit with position refresh took 2.27 s, the 922 check);
  Wiki `notes/wiki/record-interfaces.md` (Loading a Record — 921) and
  `notes/wiki/daily/2026-10-18.md`. AGENTS.md needed no change.
