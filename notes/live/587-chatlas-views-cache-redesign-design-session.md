# Chatlas Views Cache Redesign - design-session

## Session.Abstract

Design session for reworking `Chatlas.Views` in `agentos-py` after the Chatlas index-first rebuild.

The source context is the earlier `agentos-md` views cache design:

- `agentos-md/notes/live/520-chatlas-views-cache-design-summary.md`
- `agentos-md/notes/live/521-chatlas-views-cache-core-design.md`

This session should migrate the fundamental design intent from those artifacts while adapting it to the current `agentos-py` Chatlas architecture:

```text
index selection -> copied Chatlas raw artifacts -> session model/export views -> cached derived views
```

The first motivating use case remains an agent-produced compressed transcript summary view that other agents can reuse without repeating the computation.

## Design.Index

### Chatlas.Views

`Chatlas.Views` are cached dataflow products:

```text
parameters[] -> view production -> artifact files
```

The view name selects the registered view class. The `parameters[]` vector is the public input identity for one requested derivation.

Chatlas owns the storage, lookup, staging, commit, and freshness-reporting surfaces. Each view workflow owns its source resolution, dependency declarations, cache-key logic, artifact contract, and freshness semantics.

### View.Identity.And.CacheKey

A view cache identity is the registered view name plus canonical `parameters[]`.

```text
view_identity = view.name + parameters[]
cache_key = sha256(canonical_json(view_identity))
```

View names must be unique among registered view classes. Parameters must be canonical and stable. For ordered views, parameter order is significant. For unordered views, the registered workflow must canonicalize parameter order before cache-key computation.

Freshness fingerprints, artifact hashes, timestamps, producer identities, and observed dependency fingerprints do not belong in the cache key. They belong in the committed manifest and freshness metadata.

The cache key answers which derivation slot this artifact occupies. Freshness answers whether the artifact currently occupying that slot is valid.

Example identity:

```json
{
  "schema": "chatlas-view-cache-key-v1",
  "view": "zip-transcript-agent-summary",
  "parameters": [
    {
      "type": "session",
      "id": "019e18f1-45ea-7043-9ec1-6285cb4d7d08"
    }
  ]
}
```

### Single.Session.View.Scope

Current implementation work should focus on single-session views.

For the first implemented view workflows, the canonical parameters are expected to look like:

```text
parameters[] has exactly one item
parameters[0].type == "session"
parameters[0].id == canonical Chatlas indexed session id
```

Consumer and lifecycle commands for these first workflows may accept the same selector options as `agentos chatlas index query`, resolving those options to one indexed session before building the view parameters.

For single-session workflows, a selector that resolves zero sessions should report a missing selection error. A selector that resolves multiple sessions should report an ambiguous selection error.

Workflows receive a canonical session parameter, not raw CLI selector options.

The `parameters[]` vector remains the base model. Multi-session views are simply not part of the immediate implementation focus.

### Chatlas.Views.Storage

Committed view artifacts should live under Chatlas-owned storage, not project-local `notes/live/`, so artifacts can be reused across projects and future sessions.

Every Chatlas view is materialized as file artifacts when available.

Initial committed storage shape:

```text
~/Documents/chatlas/views/<view-name>/<cache-key>/manifest.json
~/Documents/chatlas/views/<view-name>/<cache-key>/<artifact-files>
```

The earlier design used `artifact.md` as the first markdown artifact file. This remains a good first default, but the artifact contract belongs to each view workflow.

For each `view.name + parameters[]` cache slot, Chatlas keeps one current committed artifact set. When a new valid artifact is committed for the same slot, it replaces the current artifact atomically by default.

For externally produced views, stale artifacts remain available until a replacement candidate is registered and committed. Chatlas reports the stale state, but does not delete or hide the previous artifact while waiting for external reproduction.

View workflows define their own artifact contracts, including filenames, primary artifact, content types, and required files.

### View.Workflow.Registry

Generic `agentos chatlas views` commands should dispatch through a static workflow registry at first.

The registry maps a view name to a workflow implementation. Generic code may share primitives such as session selection, manifest I/O, staging directory creation, artifact hashing, and atomic commit, but it must not hardcode per-view behavior outside the registry.

Dynamic third-party view plugins remain out of scope for the first redesign.

### View.Dependency.Freshness

Freshness is view-owned and dependency-based.

Each view declares dependencies with observed fingerprints when it is committed. A view is fresh when its committed dependency fingerprints match the current fingerprints for those dependencies.

If a dependency is another Chatlas view, freshness is computed recursively by asking that dependency view for its freshness/status. A parent view must not inspect or reimplement a child view's dependency logic.

For example, if `view2` depends on `view1`, `view2` asks `view1` whether it is fresh. `view1` owns checking its own raw dependencies. `view2` may compare its committed dependency fingerprint for `view1`, but it does not check `view1`'s raw source itself.

Freshness diagnostics should explain the dependency tree and identify the direct or nested dependency that made a view stale.

### View.External.Workflow

External views are produced outside Chatlas, usually by an agent.

Chatlas should not silently trigger external production. When a fresh committed artifact exists, Chatlas returns a query/status result pointing to the artifact. When the artifact is missing or stale, Chatlas returns a result that reports production is required and includes production instructions.

The external producer stages the view through Chatlas, writes the expected artifact files into the staging location, and commits through Chatlas. Commit validates the staged artifacts, writes the committed manifest, and moves artifacts into canonical storage.

Stage creation records the intended `view + parameters` identity. The cache key can be generated from that identity. Staging metadata should contain enough information for commit to validate and move the candidate into the correct canonical storage slot.

### View.Internal.Workflow

Internal views are deterministic views that Chatlas can produce programmatically from Chatlas-owned data and registered dependencies.

Internal views may skip staging and use an internal `produce` hook. At consumer time, if a committed internal view is missing or stale, Chatlas may produce it before returning the consumer result when the workflow is configured for automatic production.

Automatic internal production must remain separate from external agent-produced views.

### View.Consumer.And.Lifecycle.Surface

The first `agentos chatlas views` surface should include both consumer commands and lifecycle commands.

Consumer commands answer whether a view exists, where it is, and whether it is fresh:

```sh
agentos chatlas views get --view <view-name> ...
agentos chatlas views status --view <view-name> ...
agentos chatlas views path --view <view-name> ...
agentos chatlas views list ...
```

Lifecycle commands let producers create and publish candidates:

```sh
agentos chatlas views stage --view <view-name> ...
agentos chatlas views commit --stage-id <stage-id>
```

At consumer time, if a cache entry is missing or stale:

- internal view: by default, Chatlas may call the workflow `produce` hook when automatic production is enabled, then return the fresh view result
- external view: Chatlas reports the missing or stale state and returns production-required instructions for an external producer, which stages a candidate and commits it through Chatlas

This preserves a single consumer surface while keeping production authority explicit by workflow type.

Freshness diagnostics are always computed internally as needed for correctness. Published recursive diagnostics should be returned only when requested, for example through an explain flag or status mode, so normal agent consumers can request paths or artifacts without receiving a large dependency tree.

### View.Consumer.Result.Contract

Consumer command results should use a small generic base envelope plus view-owned extension fields.

The base envelope is responsible for command status, view cache identity, parameters, artifact pointers, freshness state, and production requirements. View-specific semantics belong under `fields`, which is owned by the registered view workflow.

Initial result shape:

```json
{
  "status": "ok",
  "view": {
    "name": "agents-summary-zip-transcripts",
    "cache_key": "...",
    "state": "fresh",
    "workflow_type": "external",
    "schema_version": "chatlas-view-result-v1"
  },
  "parameters": [
    {
      "type": "session",
      "id": "019e18f1-45ea-7043-9ec1-6285cb4d7d08"
    }
  ],
  "artifact": {
    "path": "...",
    "content_type": "text/markdown",
    "sha256": "..."
  },
  "freshness": {
    "state": "fresh",
    "dependencies": []
  },
  "production": {
    "required": false
  },
  "fields": {}
}
```

Top-level `status` describes command/runtime execution. `view.state` describes the cache/view state, such as `fresh`, `missing`, `stale`, `produced`, `production_required`, or `invalid`.

The `parameters` field is a typed vector so the same envelope can represent one session, many sessions, another view, a provider/home shard, a time range, or another future view input type.

The `parameters` vector is the public call identity of the view. The `freshness.dependencies` tree is the internal production and validation graph used by the workflow. A view can depend on other views without exposing those dependency views as part of its public identity.

For example, `zip-transcript-agent-summary(parameters=[session])` can internally depend on `zip-transcript(parameters=[session])`, but its cache key is still based on `zip-transcript-agent-summary + parameters=[session]`.

Generic Chatlas code may read, write, and validate the base fields. Only the registered view workflow owns the meaning and validation of `fields`.

### AgentsSummaryZipTranscripts

The first motivating view is `agents-summary-zip-transcripts`.

It is an agent-produced markdown artifact derived from a selected Chatlas session and the materialized `zip-transcript` view.

It should be reusable across future sessions and report stale when at least one of these changes:

- source session/content fingerprint
- upstream materialized `zip-transcript` view fingerprint
- producer workflow version
- compression or summary policy version

### Determinism.Boundary

Chatlas should remain deterministic at first.

Chatlas provides the cache lifecycle and validation interface. Internal deterministic views can be produced by Chatlas and committed as files. External agents or tools produce non-deterministic artifact content and register it through `views stage` / `views commit`.

Automatic `ensure` generation is deferred because it would imply Chatlas invoking an LLM agent.

The first implementation should add the new `agentos chatlas views ...` surface and make `zip-transcript` a materialized internal view there. The existing `agentos chatlas export --view zip-transcript` path should remain stable while the new views path is introduced; whether export later becomes a print/render surface or is retired is a separate decision.

## Session.Notes

Current active `agentos-py` Chatlas surfaces relevant to this design:

- `agentos chatlas index query` is the cheap selector over `index/sessions/**/*.jsonl`.
- `agentos chatlas export --view zip-transcript` currently produces the deterministic compact transcript view from copied Chatlas raw artifacts. In the redesigned views system, `zip-transcript` should become a materialized Chatlas view artifact.
- `agentos chatlas query` remains the future richer query surface and should not be the default selector for view workflows.
- `agentos chatlas stats` is index-only and should not become a derived-content stats surface.

Open design questions:

1. What is the exact manifest schema for committed dependencies, current fingerprints, artifact metadata, and producer policy versions?
2. What is the exact recursive dependency diagnostic shape inside `freshness.dependencies`?
3. What exact production-instruction JSON should external views return from consumer commands when production is required?

## Session.Log

- 2026-05-13: Started artifact-backed design session in `agentos-py` for redesigning Chatlas view caching. Migrated fundamentals from `agentos-md` 520 and 521 into the current Chatlas index-first context.
- 2026-05-13: Captured alignment that the first `agentos chatlas views` surface should include both consumer commands and lifecycle commands. Consumer commands may auto-produce internal views when configured, while external views return production-required instructions and use stage/commit for producer candidates.
- 2026-05-13: Consolidated the consumer result contract around a small generic base envelope plus view-owned `fields`. Top-level `status` is command/runtime status; `view.state` is cache state.
- 2026-05-14: Captured that every view is materialized as file artifacts when available. Recursive freshness asks dependency views for status instead of inspecting their internals.
- 2026-05-14: Consolidated the view dataflow identity model: `parameters[] -> view production -> artifact files`. Cache keys are computed from registered view name plus canonical `parameters[]`; dependencies remain the workflow-owned production/freshness graph.
- 2026-05-14: Narrowed immediate implementation focus to single-session views, while keeping `parameters[]` as the general base model.
- 2026-05-14: Consolidated remaining general design decisions: current cache slot replacement is atomic by default, stale external artifacts remain until replacement commit, stages record `view + parameters`, workflow owns artifact contracts, internal views auto-produce by default, external views request reproduction, recursive diagnostics are published only on request, and `zip-transcript` should enter the new views surface while existing export remains stable.
