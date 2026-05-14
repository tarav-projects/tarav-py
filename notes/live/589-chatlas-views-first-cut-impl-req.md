# Chatlas Views First Cut - impl-req

## Impl.Abstract

- **scope:** implement the first `agentos chatlas views ...` surface for materialized Chatlas views, starting with single-session view workflows
- **status:** ready for implementation
- **source:** `notes/live/587-chatlas-views-cache-redesign-design-session.md`
- **supporting context:** `agentos-md/notes/live/520-chatlas-views-cache-design-summary.md`, `agentos-md/notes/live/521-chatlas-views-cache-core-design.md`

The implementation must introduce the new views system cleanly in `src/agentos/chatlas/` without reviving deprecated Chatlas query/update behavior. Existing `agentos chatlas export --view zip-transcript` should remain stable while `zip-transcript` is also introduced as a materialized internal view under the new views surface.

## Impl.Index

### View.Dataflow.Model

- a Chatlas view is a cached dataflow product: `parameters[] -> view production -> artifact files`
- the registered view name selects the workflow class
- `parameters[]` is the public input identity for one requested derivation
- immediate implementation work focuses on single-session workflows, where CLI selectors resolve through the existing index selector to one canonical indexed session parameter
- workflows receive canonical parameters, not raw CLI options

### View.Identity.CacheKey

- cache identity is `view.name + canonical parameters[]`
- `cache_key = sha256(canonical_json(view_identity))`
- view names must be unique in the static registry
- freshness fingerprints, artifact hashes, timestamps, producer identities, and observed dependency fingerprints must not influence the cache key
- cache key chooses the storage slot; freshness decides whether the artifact in that slot is current

### View.Storage.Manifest

- committed artifacts live under Chatlas-owned storage:

```text
~/Documents/chatlas/views/<view-name>/<cache-key>/manifest.json
~/Documents/chatlas/views/<view-name>/<cache-key>/<artifact-files>
```

- every available view is materialized as file artifacts
- each cache slot has one current committed artifact set
- new valid commits replace the current slot atomically by default
- stale external artifacts remain available until a replacement candidate is committed
- workflow definitions own artifact contract: required files, primary artifact, filenames, content types, and field metadata

### View.Registry.Boundary

- generic command code dispatches through a static workflow registry
- generic Chatlas code may own common primitives: parameter resolution, cache-key generation, storage paths, manifest I/O, staging directories, artifact hashing, atomic commit, and result-envelope formatting
- workflow-specific logic belongs behind the registered workflow boundary
- dynamic third-party plugins are out of scope

### Internal.View.ZipTranscript

- `zip-transcript` must become a materialized internal Chatlas view
- it should reuse the existing copied-raw normalization/export pipeline rather than duplicating provider parsing
- missing or stale internal views auto-produce by default when requested through `views get/path/status`
- the existing `agentos chatlas export --view zip-transcript` command must keep working during this slice

### External.View.AgentSummary

- first external view target is the agent-produced lower-token transcript derived from a materialized `zip-transcript`
- registered name: `zip-transcript-agent-summary`
- primary artifact: `summary.json`
- content type: `application/json`
- artifact class: `agentos.chatlas.zip_transcript_agent_summary`
- artifact shape mirrors `zip-transcript`: `session` plus ordered `turns`
- user turns must be copied verbatim, in full, and in chronological order
- assistant turns remain aligned in place but are summarized aggressively
- assistant summaries must preserve decisions, accepted plans, constraints, commands, paths, identifiers, test results, failures, warnings, unresolved issues, and enough context for later user references to remain intelligible
- assistant summaries should remove progress chatter, repeated framing, obvious restatement, speculative narration, apology/filler, and verbose output that does not change state
- external views do not silently invoke an LLM or external agent
- missing or stale external views return state plus production instructions
- external producers stage a candidate, write artifacts, then commit through Chatlas validation

### Freshness.Recursion

- freshness is workflow-owned and dependency-based
- committed manifests record observed dependencies
- if a dependency is another view, the parent asks that dependency view for freshness/status
- parent workflows must not inspect or reimplement child dependency internals
- recursive diagnostics are computed internally as needed for correctness
- published recursive diagnostics are returned only when requested, such as with an explain flag or status mode

### Consumer.Result.Contract

- consumer commands return a generic base envelope plus workflow-owned `fields`
- top-level `status` is command/runtime status
- `view.state` is cache state: `fresh`, `missing`, `stale`, `produced`, `production_required`, or `invalid`
- base fields should include `view`, `parameters`, `artifact`, `freshness`, `production`, and `fields`
- normal agent consumers should be able to get a path/artifact without receiving a large dependency tree unless requested

### Command.Surface

- add `agentos chatlas views ...`
- first consumer commands:
  - `agentos chatlas views get --view <name> <index-selector-options>`
  - `agentos chatlas views status --view <name> <index-selector-options>`
  - `agentos chatlas views path --view <name> <index-selector-options>`
  - `agentos chatlas views list`
- first lifecycle commands:
  - `agentos chatlas views stage --view <name> <index-selector-options>`
  - `agentos chatlas views commit --stage-id <stage-id>`
- use option-based selectors only; no positional session arguments
- reuse the shared Chatlas index selector options from `commands.py`

## Execution.Plan

### Slice 1 - Core views primitives

- add a small `agentos.chatlas.views` module/package for cache identity, canonical JSON hashing, storage path resolution, result envelopes, manifest I/O, artifact hashing, and atomic slot replacement
- path: `commands.py` -> `core.py` or direct views facade -> views primitives
- observable: code can compute a deterministic cache key and storage path from `view + parameters[]`
- check: focused unit tests for canonical cache-key stability, no freshness data in identity, and path layout
- status: not started

### Slice 2 - Static workflow registry

- add a static registry mapping view names to workflow implementations
- define a narrow workflow protocol for parameter canonicalization, artifact contract, freshness/status, optional internal production, and external production instructions
- path: `views registry` -> workflow lookup -> result envelope
- observable: unknown view names produce a clear CLI error; known names expose workflow metadata through `views list`
- check: tests for registry lookup, unique names, and `views list`
- status: not started

### Slice 3 - Single-session parameter resolution

- reuse existing `select_one_chatlas_index_row` and selector CLI helpers to resolve command options to one canonical session parameter
- path: `agentos chatlas views get/status/path/stage` -> index selector -> canonical `parameters[]`
- observable: zero-match and multi-match selectors return the same clear behavior style as export/raw commands
- check: command tests for `--session-id`, missing selector, zero match, and ambiguous match
- status: not started

### Slice 4 - Materialized internal `zip-transcript`

- implement `zip-transcript` as an internal workflow that materializes a primary artifact file from the current export projection
- reuse existing session model normalization and zip-transcript projection instead of copying provider-specific parsing logic
- store the artifact and manifest under `views/zip-transcript/<cache-key>/`
- path: selector -> canonical session parameter -> internal produce -> committed artifact -> result envelope/path
- observable: `agentos chatlas views get --view zip-transcript --session-id ...` returns a committed artifact result; `views path` prints or returns its path
- check: tests with fixture copied raw artifacts; verify artifact file exists, manifest exists, result has `view.state=produced` or `fresh`, and existing `chatlas export --view zip-transcript` still passes
- status: not started

### Slice 5 - External summary stage/commit path

- implement external workflow for `zip-transcript-agent-summary`
- its required staged artifact is `summary.json`, not markdown
- `summary.json` is a lower-token, turn-aligned copy of `zip-transcript` where user turns are verbatim and assistant turns are summarized
- `views status/get/path` reports `production_required` when missing or stale and includes production instructions
- `views stage` creates a staging directory with intended `view + parameters` metadata and generated cache key
- `views commit --stage-id ...` validates required artifacts, hashes them, writes the manifest, and atomically replaces the current cache slot
- path: stage -> external producer writes artifact -> commit -> consumer get/path/status
- observable: a staged `summary.json` artifact can be committed and then resolved by consumer commands as the current artifact
- check: tests for stage metadata, commit validation failure for missing artifact, successful commit, stale artifact remaining available until replacement, and atomic replacement
- status: not started

### Slice 6 - Freshness and explain output

- implement initial freshness checks for internal `zip-transcript` and external summary dependencies
- internal `zip-transcript` should become stale when the source session/content fingerprint changes
- external summary should depend on materialized `zip-transcript` and workflow/policy metadata
- default output should include summary freshness only; explain output should include recursive diagnostics
- path: consumer status/get/path -> workflow freshness -> dependency view status -> optional recursive diagnostics
- observable: stale states are reported without deleting artifacts; explain output identifies the stale dependency path
- check: tests for fresh, missing, stale, production-required, and explain/no-explain output differences
- status: not started

### Slice 7 - CLI integration and install verification

- register the `views` command group in `src/agentos/chatlas/commands.py`
- keep all arguments option-based
- after CLI changes, run `uv tool install --reinstall --editable .`
- path: installed `agentos` -> `chatlas views ...`
- observable: local CLI exposes the new command group and existing Chatlas commands remain stable
- check: focused Ruff, focused pytest for Chatlas commands/views, then broader relevant tests if time permits
- status: not started

## Impl.Log

- 2026-05-14: Created implementation request from the accepted Chatlas views redesign session. Execution has not started.
- 2026-05-14: Implemented first-cut Chatlas views surface:
  - added materialized view primitives and registry under `src/agentos/chatlas/views/`
  - added `agentos chatlas views list|get|status|path|stage|commit`
  - materialized internal `zip-transcript` view while keeping `agentos chatlas export --view zip-transcript` stable
  - added external `zip-transcript-agent-summary` stage/commit flow with stale-artifact retention
  - added focused tests in `tests/test_chatlas_views.py`
  - verification: `uv run pytest tests/test_chatlas_views.py tests/test_chatlas_commands.py tests/test_chatlas_session_hashes.py -q`, touched-file Ruff, and editable CLI reinstall
- 2026-05-14: Updated the external `zip-transcript-agent-summary` design contract to JSON `summary.json`. The view is now explicitly a lower-token, turn-aligned replacement for `zip-transcript`: user turns are verbatim, assistant turns are summarized in place, and later-user-reference intelligibility is part of the producer contract.
- 2026-05-14: Implemented the `summary.json` contract in `src/agentos/chatlas/views/`: the external workflow now requires `summary.json`, advertises `application/json`, validates the staged JSON base shape/class/view/source_view/session/turns before commit, and records JSON artifact metadata. Updated focused tests and refreshed the installed CLI.
