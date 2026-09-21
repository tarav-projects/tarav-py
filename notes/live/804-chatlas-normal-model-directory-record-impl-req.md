# 804 — Chatlas Normal Model directory record — implementation request

<!-- tarav.sessions
3dbc7074 = codex:01a0baed-f147-77e2-b298-ed15249a9410 @3dbc7074117a70b90f57c98b25690d3ea15a519f0da6e05043e59b8add00d3c4
-->

## Impl.Abstract

- **Status:** Complete.
- **Alignment.Mode:** Autonomous.
- **Objective:** promote the aggregate Chatlas Normal Model to a registered `DirectoryRecord` that owns its canonical directory representation, while moving cache mechanics outside the semantic Normal Model module.
- **Starting state:** `normal_model/cache.py` owns the directory reader, semantic header, JSONL serialization, cache freshness, locking, and atomic replacement. The canonical model header is nested inside cache-owned `metadata.json`.
- **Target representation:** `normal-model/<identity>/main.json`, `events.jsonl`, `messages.jsonl`, `turns.jsonl`, and `loaded-contexts.jsonl`; a cache-managed materialization may additionally contain `cache.json`.
- **Behavioral boundary:** preserve provider normalization, archive/current-source merging, stable Event/Message/Turn identities, lazy typed stream reads, Query, CLI projections, exact references, Breadcrumb resolution, freshness checks, locking, source-change detection, atomic replacement, and uncached `--include-raw` diagnostics.
- **Migration:** rebuild the disposable Normal Model cache in the new representation. Do not add a legacy cache reader or compatibility alias.
- **Out of scope:** arbitrary third-party files inside the cache-managed Normal Model directory and persistence of raw diagnostic fragments.

The invocation authorizes this bounded design and implementation.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Project Model:** `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Grounded View:** project-scoped View `3f54d0ca-8506-4978-a9b8-d51260310226`; synchronized with no content changes and one visible-line-budget POI
- **Semantic Block:** existing `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
- **Impl.Req.Collection:** `804.Impl.Req` — `0e6fc215-e9c2-4b2d-8006-d74baf76c5b9` (`Closed`)
- **Diagram.Draft:** `26b0202c-ea51-48b4-ab49-6a5001992704` (`Applied`)
- **Capture.Authorization.Gate:** `f23b2ae9-8c0e-47d6-8da9-6c3d1150e9ac`

## Execution.Plan

### Slice 1 — Semantic aggregate and canonical directory

- Add registered `ChatlasNormalModel(DirectoryRecord)` with Type `Chatlas.Normal.Model` and Type Ship `64389d49-e0fd-4c26-8343-abf4880b3e33`.
- Make `main.json` a complete independently loadable semantic header with session, sources, representation version, producer metadata, and collection counts.
- Move typed JSONL iteration, projection, full loading, validation, and canonical directory serialization from the cache reader to the aggregate class.
- Keep normalization responsible for producing semantic content and keep optional raw fragments in the uncached diagnostic path.
- **Observable:** the canonical directory loads through the runtime registry as `ChatlasNormalModel` and streams every existing collection without `cache.json`.
- **Check:** focused aggregate loading, serialization, row validation, projection, and provider-normalization tests.
- **Status:** Complete.

### Slice 2 — Cache decoration and public behavior

- Move cache mechanics to a Chatlas-level module outside `normal_model/`.
- Store only freshness and rebuild evidence in `cache.json`; missing or invalid cache metadata makes reuse stale without invalidating the Normal Model directory itself.
- Preserve per-identity locking, before/after source fingerprints, staged whole-directory replacement, rollback, stable cache paths, and `FRESH`/`STALE`/`MISSING` status.
- Return `ChatlasNormalModel` from the public reader provider and retain the existing `provide_normal_model`, `provide_normal_model_reader`, and `compute_normal_model` behaviors used by Query, CLI, references, Diagram, and Breadcrumbs.
- **Observable:** cached and uncached commands produce equivalent semantic projections, while direct record loading succeeds independently of cache state.
- **Check:** cache status/materialization tests plus Chatlas CLI, Query, reference, Diagram, and Breadcrumb tests.
- **Status:** Complete.

### Slice 3 — Architecture, migration, and closure

- Update architecture guidance and import-boundary checks for the semantic aggregate and external cache mechanics.
- Reinstall the editable CLI, rebuild the disposable local Normal Model materialization, and smoke the public current-session, Normal Model, and Query paths.
- Run focused checks, Ruff, architecture validation, and the complete maintained suite.
- Submit justified Product.Surface Breadcrumbs, close `804.Impl.Req`, check the final Draft overlay, and apply it once.
- **Observable:** installed Chatlas commands use the new materialization without consumer regressions.
- **Check:** complete suite and installed CLI smoke tests.
- **Status:** Complete.

## Risks and deviation triggers

- If aggregate typing changes established Event, Message, or Turn address/hash preimages, preserve the existing identity computation and record the deviation.
- If `main.json` cannot independently validate the directory without reading cache state, stop and correct the ownership boundary.
- The cache owns lifecycle of directories under its managed root. Do not promise preservation of unknown auxiliary files during atomic replacement.
- If a consumer depends on `NormalModelCacheReader` as a concrete class rather than the public reader protocol, migrate the consumer directly; do not retain a compatibility alias.
- Existing Diagram assertion, Archive-grounding, Model-staleness, legacy type, and View-budget POIs do not block product mutation.

## Acceptance signals

- `Chatlas.Normal.Model` is registered and loads as a `DirectoryRecord` from `main.json`.
- Canonical streams are semantic model files; `cache.json` is optional cache evidence.
- Direct loading remains valid when cache metadata is absent or invalid.
- Existing normalization, streaming, query, CLI, reference, Breadcrumb, freshness, locking, atomicity, and raw-diagnostic behavior remains available.
- Focused checks, Ruff, architecture validation, and the complete suite pass.

## Impl.Log

- The current implementation confirms that the proposed folder shape already exists operationally; the refactor changes ownership and the entry record rather than the normalized data train.
- Autonomous design selected the existing `Tarav.Record` Block because the request extends the aggregate Record semantics established by request 803.
- Initial Draft check is structurally writable and reports 408 POIs: six request-local unasserted/archive-grounding findings plus the Model's existing POIs.
- Fresh View creation exposed a View-tooling race while a second process listed the repository. The two workflow-created partial directories were removed, both builders were stopped, and the existing project View was synchronized sequentially.
- Checkpoint commit `d89ef26` retained all pre-existing request-803 work before product mutation.
- Added `ChatlasNormalModel(DirectoryRecord)` and made `main.json` the independently loadable semantic entry. The class now owns typed JSONL iteration, projections, full loading, count validation, and canonical serialization; raw diagnostic fragments are explicitly excluded from persistence.
- Moved freshness, fingerprinting, locking, source-change detection, staging, rollback, and replacement to Chatlas-level `normal_model_cache.py`. Its optional `cache.json` advanced to schema 4; absence or corruption makes the cache stale without invalidating the semantic directory.
- The maintained Normal Model envelope moved from ordinary schema 2 to registered Type `Chatlas.Normal.Model` representation schema 1. Existing Event, Message, and Turn identity computations were unchanged.
- Focused Chatlas, Breadcrumb, Diagram, and architecture validation passed (`194 passed`), Ruff passed, and the final complete maintained suite passed (`1176 passed`).
- Reinstalled the editable CLI and rebuilt the current session. The live directory contains `main.json`, four JSONL streams, and `cache.json`; its counts are 3,009 Events, 121 Messages, 414 Turns, and 583 loaded contexts. Runtime loading returned `ChatlasNormalModel`, and Query resolved the functionality-preservation User turn.
- Submitted and exactly resolved Product.Surface Breadcrumbs `fbcaa106132b41dfa0beda40d4dd1bf512c0dbe8ae3a8392a45aaec0037950e7` and `0221441d98de41950b96fa7dae8da102cbfbba80964204c02c362cbc6946a248` without findings.
- Closed `804.Impl.Req`, checked the final overlay, and applied Draft `26b0202c-ea51-48b4-ab49-6a5001992704` once. Receipt commit `59bbf4c92e3b5ca2670d1b3e091450152b647efd` retains 409 POIs: seven request-local unasserted/archive-grounding findings and the Model's existing assertion, staleness, grounding, and legacy-type findings.
