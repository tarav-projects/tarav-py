# Record loading workflow — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: ready, 2026-10-18.
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
- Capture status: pending.

## Execution.Plan

Core data shape: `RecordLoadingConfig`, `RecordLoadingContext`,
`LoadedRecord(data, metadata: LoadingMetadata(source))`.

1. Performance/refactor — the parse step only. `parse_record` replaces
   `validate_record` (callers migrated); no copies or comparison on loading;
   Chatlas rows parsed once. Check: full suite; micro-benchmark before and
   after. Status: pending.
2. Feature — the loading pipeline. `tarav.l0.kernel.loading`; builders
   receive `LoadedRecord`; `source` through metadata. Check: new
   `tests/kernel/test_record_loading.py`; full suite. Status: pending.
3. Feature — check levels on `RecordLoadingConfig`. Check: tests for
   `none`, `default`, a Type-defined `lite`/`full`. Status: pending.
4. Refactor — `_record` removed. Types migrated to own state; the record
   contract test drives the list; architecture test forbids `._record`.
   Check: full suite. Status: pending.
5. Docs — ARCHITECTURE, AGENTS (Skillware source) if the contract text
   changes, Wiki capture. Status: pending.

Deviation triggers: a Type whose round trip cannot hold without the stored
record; consumers outside tarav-py reading `_record`.

## Impl.Log

- 2026-10-18: request written by the designing Agent in the session above.
