# Agentos Bloberia v1 - impl-req

## Impl.Abstract

- **scope:** implement the first `Agentos.Bloberia` vertical slice as an importable Python library and thin `agentos bloberia ...` CLI
- **status:** ready for implementation
- **source:** reviewed `Agentos.Bloberia` index block plus the current `--design` and `exec` requests
- **support set:** `Agentos.Bloberia` and its accepted contract ^c20260724-31u
- **target projects:** `agentos-py` owns the library and command-domain registration; `agentos-cli` aggregates the command

## Impl.Agendix

- **touched (index):** `Agentos.Bloberia` - query:value storage, importable-library boundary, record envelope, structural queries, application-owned values, and explicit depot scope ^c20260724-31u
- **touched (chat):** no legacy format or compatibility path ^c20260724-31u
- **touched (chat):** Bloberia is independent of application payload mutability and dataflow ^c20260724-31u
- **structural:** `agentos-cli` depends on `agentos-py` and imports its command registrar
- **open space:** internal helper decomposition remains agent-owned; no index surface fixes a Python file layout below the public `agentos.bloberia` boundary

## Impl.Index

### Current.Implementation

- `agentos-py/src/agentos/` contains reusable depot-scoped subsystems but no `agentos.bloberia` package
- `agentos-cli/src/agentos_cli/cli.py` aggregates command registrars from feature packages but has no Bloberia registration
- `agentos-py/src/agentos/_core/json_input.py` already provides JSON argument and file loading primitives
- `agentos-py/src/agentos/_core/ids.py` and `_core/clock.py` already provide UUID and UTC timestamp primitives
- `agentos-py/src/agentos/anchory/core.py` demonstrates the repository's `fcntl` locking and atomic temporary-file replacement patterns; Bloberia may reuse the mechanical pattern without inheriting anchor semantics
- `agentos-py` already depends on `jmespath`, but v1 structural query does not require a query-language dependency
- the `agentos-py` worktree already contains unrelated edits in `src/agentos/index/linter.py` and `tests/test_index_linter.py`; execution must preserve them

### Bloberia.Record.Contract

- a canonical record is `{"_bloberia": <envelope>, "value": <application JSON>}`
- the reserved `_bloberia` envelope contains `id`, `created_at`, `updated_at`, and `revision`
- `id` is an opaque generated UUID string and never changes
- `created_at` is fixed at creation; `updated_at` advances on edit
- `revision` starts at `1` and increments by one on every successful edit
- callers supply and mutate only `value`; the library owns and validates the envelope
- `value` may be any JSON-serializable value, including object, array, scalar, or null
- public reads return detached data so caller mutation cannot modify persisted state implicitly

### Bloberia.Structural.Query

- a query is a JSON object matched recursively against the complete canonical record
- object members use subset semantics: every query key must exist and its value must match recursively
- non-object values, including arrays, match by JSON equality
- `{}` selects every valid record
- query results are deterministic, ordered by record identity
- v1 exposes no textual query DSL, predicates, projections, or application-specific indexes

### Bloberia.Depot

- `BloberiaDepot` receives one exact explicit root and resolves it once
- records live as one JSON file per identity under `<depot>/records/`
- every mutation holds one depot-wide exclusive lock and writes through flush, fsync, and atomic replace
- reads and queries hold a shared depot lock
- create rejects the vanishingly unlikely generated-ID collision rather than overwriting
- get/edit distinguish missing identity from corrupt storage
- edit atomically replaces the full application value; partial patch and merge semantics are out of scope
- `check` scans without mutation and reports malformed JSON, invalid canonical record shape, invalid identity filenames, and envelope/filename identity mismatch

### Bloberia.Library.Surface

- public package: `agentos.bloberia`
- primary object: `BloberiaDepot`
- primary operations: create, get, edit, query, and check
- typed immutable result objects carry canonical records and check findings
- domain-specific errors distinguish invalid input, missing records, identity collision, and corrupt depots
- library operations accept Python JSON values and return normalized JSON-compatible values

### Bloberia.CLI.Surface

- `agentos bloberia create --depot <path> (--value-json <json> | --value-file <path>)`
- `agentos bloberia get --depot <path> --id <record-id>`
- `agentos bloberia edit --depot <path> --id <record-id> (--value-json <json> | --value-file <path>)`
- `agentos bloberia query --depot <path> [--query-json <object> | --query-file <path>]`
- `agentos bloberia check --depot <path>`
- all successful commands emit deterministic JSON envelopes including the resolved depot
- missing records and invalid/corrupt input cross the CLI boundary as concise `CliError`s
- `check` returns nonzero only when error findings exist

### Scope.Boundary

- no delete operation
- no partial patch or merge operation
- no implicit, discovered, configured, or global depot
- no namespaces, application schema registry, secondary indexes, or retention policy
- no Skillware edition-history consumer
- no Anchory integration or shared persistence refactor
- no legacy storage format or compatibility path

## Execution.Plan

### Slice 1 - Record model and create/get persistence

- add `agentos.bloberia` public models, errors, JSON normalization, explicit depot, locking, record paths, and atomic writes
- implement record creation and identity lookup with the canonical envelope
- RED: library tests cover arbitrary JSON values, envelope ownership, UUID identity, timestamps/revision, detached reads, missing IDs, serialization rejection, collision rejection, and atomic-write failure preservation
- observable: a fresh `BloberiaDepot` can create and retrieve the same canonical record from disk
- check: `cd agentos-py && uv run pytest tests/test_bloberia.py`
- status: not started

### Slice 2 - Edit and structural query

- implement full-value atomic edit with stable identity/creation time and advancing update/revision metadata
- implement recursive subset matching over canonical records with deterministic result ordering
- RED: tests cover object-subset recursion, exact array/scalar matching, empty-query selection, envelope queries, nonmatching records, edit invariants, and concurrent mutation safety
- observable: callers can replace values and select records without application-specific storage code
- check: `cd agentos-py && uv run pytest tests/test_bloberia.py`
- status: not started

### Slice 3 - Depot check

- implement a read-only structural audit returning typed findings and an `ok` verdict
- RED: tests introduce malformed JSON, invalid record shape, invalid filename identity, and identity mismatch, then verify deterministic findings and zero mutation
- observable: a consumer can distinguish a valid depot from corrupt storage without reading internal files itself
- check: `cd agentos-py && uv run pytest tests/test_bloberia.py`
- status: not started

### Slice 4 - Thin CLI and umbrella registration

- add Bloberia command handlers in `agentos-py`, reusing `_core.json_input`
- export the registrar and register it in `agentos-cli`
- add focused end-to-end tests for command discovery, create/get/edit/query/check, JSON-file inputs, explicit depot requirement, and error exits
- observable: `agentos bloberia ...` exposes the library contract without a second implementation
- check: `cd agentos-cli && uv run pytest tests/test_e2e_bloberia.py`
- status: not started

### Slice 5 - Documentation and full verification

- update `agentos-py/AGENTS.md` because the change adds a subsystem and CLI surface
- keep `agentos-cli/AGENTS.md` unchanged unless execution reveals that its aggregation contract needs clarification
- run `cd agentos-py && uv run pytest`
- run `cd agentos-py && uv run ruff check src tests`
- run `cd agentos-cli && uv run pytest`
- run `cd agentos-cli && uv run ruff check src tests`
- reinstall the executable from `agentos-cli` with `uv tool install --reinstall --editable .`
- smoke a scratch explicit depot through installed create/get/edit/query/check commands
- observable: library and CLI suites pass, documentation matches reality, and the installed executable serves the new command
- status: not started

## Risks And Deviation Triggers

- stop if arbitrary JSON values cannot be normalized without narrowing the reviewed contract
- stop if the chosen filesystem layout cannot make individual record replacement atomic under the existing platform assumptions
- stop if structural subset semantics conflict with a current repository-wide query contract discovered during implementation
- stop before coupling to Anchory, adding discovery, or introducing compatibility behavior
- preserve all pre-existing unrelated worktree changes

## Acceptance Signals

- `from agentos.bloberia import BloberiaDepot` is a supported import
- library and CLI round trips preserve arbitrary JSON application values
- reserved metadata is library-owned, stable where required, and revisioned on edit
- recursive structural queries return deterministic matching records
- corrupt storage is reported without mutation
- every CLI operation uses an explicit depot
- the installed `agentos bloberia --help` exposes only the v1 surface
- all focused and full verification commands pass

## Impl.Log

- 2026-07-25: designed from the reviewed `Agentos.Bloberia` block and current implementation inspection
- 2026-07-25: readiness checkpoint approved; exact CLI verbs, envelope fields, subset-query semantics, full-value edit, UUID identity, and one-file-per-record layout accepted as implementation decisions
- 2026-07-25: latest Chatlas turns were not yet materialized at artifact creation; no unresolved anchor was written
- no execution deviations or blockers
