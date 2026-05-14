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

`Chatlas.Views` are cached derived data products produced from Chatlas session content and/or other Chatlas views.

Chatlas owns the storage, lookup, staging, commit, and freshness-reporting surfaces. Each view workflow owns its source resolution, dependency declarations, cache-key logic, artifact contract, and freshness semantics.

### Chatlas.Views.Storage

Committed view artifacts should live under Chatlas-owned storage, not project-local `notes/live/`, so artifacts can be reused across projects and future sessions.

Initial committed storage shape:

```text
~/Documents/chatlas/views/<view-name>/<cache-key>/manifest.json
~/Documents/chatlas/views/<view-name>/<cache-key>/<artifact-files>
```

The earlier design used `artifact.md` as the first markdown artifact file. This remains a good first default, but the artifact contract belongs to each view workflow.

### View.Workflow.Registry

Generic `agentos chatlas views` commands should dispatch through a static workflow registry at first.

The registry maps a view name to a workflow implementation. Generic code may share primitives such as session selection, manifest I/O, staging directory creation, artifact hashing, and atomic commit, but it must not hardcode per-view behavior outside the registry.

Dynamic third-party view plugins remain out of scope for the first redesign.

### View.Dependency.Freshness

Freshness is view-owned and dependency-based.

Each view declares dependencies with observed fingerprints when it is committed. A view is fresh when its committed dependency fingerprints match the current fingerprints for those dependencies.

If a dependency is another Chatlas view, freshness is computed recursively. Freshness diagnostics should explain the dependency tree and identify the direct or nested dependency that made a view stale.

### View.External.Workflow

External views are produced outside Chatlas, usually by an agent.

Chatlas should not silently trigger external production. When a fresh committed artifact exists, Chatlas returns a query/status result pointing to the artifact. When the artifact is missing or stale, Chatlas returns a result that reports production is required and includes production instructions.

The external producer stages the view through Chatlas, writes the expected artifact files into the staging location, and commits through Chatlas. Commit validates the staged artifacts, writes the committed manifest, and moves artifacts into canonical storage.

### View.Internal.Workflow

Internal views are deterministic views that Chatlas can produce programmatically from Chatlas-owned data and registered dependencies.

Internal views may eventually skip staging and use an internal `produce` hook, but automatic production policy is unresolved. This redesign should keep internal production separate from external agent-produced views.

### AgentsSummaryZipTranscripts

The first motivating view is `agents-summary-zip-transcripts`.

It is an agent-produced markdown artifact derived from a selected Chatlas session and likely from the deterministic `zip-transcript` export view.

It should be reusable across future sessions and report stale when at least one of these changes:

- source session/content fingerprint
- upstream deterministic `zip-transcript` view fingerprint, if modeled as a dependency
- producer workflow version
- compression or summary policy version

### Determinism.Boundary

Chatlas should remain deterministic at first.

Chatlas provides the cache lifecycle and validation interface. External agents or tools produce non-deterministic artifact content and register it through `views stage` / `views commit`.

Automatic `ensure` generation is deferred because it would imply Chatlas invoking an LLM agent.

## Session.Notes

Current active `agentos-py` Chatlas surfaces relevant to this design:

- `agentos chatlas index query` is the cheap selector over `index/sessions/**/*.jsonl`.
- `agentos chatlas export --view zip-transcript` produces the deterministic compact transcript view from copied Chatlas raw artifacts.
- `agentos chatlas query` remains the future richer query surface and should not be the default selector for view workflows.
- `agentos chatlas stats` is index-only and should not become a derived-content stats surface.

Open design questions:

1. What is the first command surface for `agentos chatlas views`?
2. Should deterministic export views such as `zip-transcript` be addressable as dependencies without being cached themselves?
3. What is the exact manifest schema for committed dependencies, current fingerprints, artifact metadata, and producer policy versions?
4. What is the public freshness result shape, especially for recursive dependency diagnostics?
5. Does `agents-summary-zip-transcripts` select exactly one session through `index query`, or can a future view support multi-session inputs?
6. Should stale replacement use `views commit --replace`, archive old entries, or require explicit deletion?

## Session.Log

- 2026-05-13: Started artifact-backed design session in `agentos-py` for redesigning Chatlas view caching. Migrated fundamentals from `agentos-md` 520 and 521 into the current Chatlas index-first context.
