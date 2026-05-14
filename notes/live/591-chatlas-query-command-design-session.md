# Chatlas Query Command - design-session

## Session.Abstract

- intent: converge the design for `agentos chatlas query` as the full query caller surface for Chatlas sessions
- active focus: layered filtering semantics across index rows, raw artifacts, and standard session model data
- references: `agentos-md/notes/index/121-Design.Session.md`; `agentos-md/skills/hugentics-designer/references/`; current `agentos chatlas` CLI help
- state: active
- next: decide candidate bound naming and behavior

## Design.Index

### Chatlas.Query.Command

- `agentos chatlas query` is the main Chatlas session query caller.
- It should cover both interactive discovery and scriptable selection needs.
- `agentos chatlas index query` remains the low-level metadata-only selector, not the full query surface.
- The command should make common session discovery possible without shelling together index queries, raw artifact paths, and external grep.
- The command should not accept a positional query argument; all query intent should be expressed through explicit filter flags.

#### appendix

The motivating issue is that recent sessions working on Chatlas can currently be found only through a workaround:

```sh
agentos chatlas index query ... \
  | jq -r '.rows[].primary_backing_artifact.path' \
  | xargs rg -il "chatlas"
```

That workaround proves the data is available, but it also exposes that the query caller is missing a first-class layered selection surface.

#### meta

- status: accepted
- source: 2026-05-14 chat discussion

### Chatlas.Query.LayeredPipeline

- `agentos chatlas query` should resolve sessions through sequential filtering layers:

```text
session index rows -> raw artifact filters -> standard model filters -> result projection
```

- Each later layer should run only against candidates that survived earlier layers.
- Cheap and indexed filters should run before expensive content or model-derived filters.
- The pipeline should be explicit enough that users can reason about both cost and match semantics.

#### appendix

The layered model lets the command support broad searches without making every query pay the cost of standard-model extraction. It also keeps rough raw text checks available for discovery while reserving semantic interpretation for the standard-model layer.

#### meta

- status: accepted as starting model

### Index.Filter.Layer

- The first query layer should include the existing `agentos chatlas index query` selector fields.
- Initial fields:
  - `--uri`
  - `--identity-hash`
  - `--provider`
  - `--instance`
  - `--provider-instance-fingerprint`
  - `--session-id`
  - `--display-name`
  - `--extractable`
  - `--updated-after`
  - `--sort`
- `agentos chatlas index query` should remain available for direct metadata-only inspection.

#### meta

- status: likely accepted, pending exact CLI option review during implementation design

### Raw.Native.Filter.Layer

- The raw layer should support coarse artifact text presence checks against backing artifacts for a candidate session.
- This layer is intentionally dump-grep semantics.
- Raw filtering should answer whether a string or pattern is present in the raw artifacts for a session.
- Raw filtering should not introduce provider-aware semantic parsing.

#### appendix

Candidate flags:

```text
--raw-contains <text>
--raw-regex <pattern>
--raw-case-sensitive
```

Raw filtering is useful when the caller knows a literal project name, file path, command, or concept string may appear somewhere in provider-native artifacts.

#### meta

- status: accepted as first raw-layer model

### Standard.Model.Filter.Layer

- The standard-model layer should run after index and raw filtering.
- It should export or derive the standard session model only for remaining candidates.
- This layer owns higher-level semantic filters over normalized Chatlas session data.

#### appendix

Candidate filters:

```text
--user-contains <text>
--assistant-contains <text>
--message-contains <text>
--role <role>
--tool-name <name>
--path-contains <path-fragment>
--cwd <path>
```

This is where questions like "sessions where the user asked about Chatlas" should be modeled, rather than relying on raw artifact grep.

#### meta

- status: initial concept accepted, exact field set open

### Limit.Semantics

- `--limit` should apply to final returned matches by default.
- A separate candidate bound should control how many index rows may enter expensive later layers.
- Candidate bound and final result limit should not be conflated.

#### appendix

Candidate controls:

```text
--scan-limit <n>
--limit <n>
```

`--scan-limit` bounds how many index rows may enter raw and standard-model filtering. `--limit` bounds returned query results after all requested filters are applied.

Without this split, a query such as `--limit 20 --raw-contains chatlas` could miss relevant sessions merely because the newest 20 index rows did not match.

#### meta

- status: accepted as design pressure, naming still open

### Match.Provenance

- First-cut query results should stay low-resolution.
- The query result should return normalized session rows only.
- Raw, index, or standard-model hits decide whether a session matches, but do not need detailed match provenance in the first implementation.
- `--include-match` can be deferred until there is a concrete need for diagnostic match details.

#### appendix

The first query system should prioritize stable row typing over explanatory diagnostics:

```text
filter hit -> session matches -> normalized session row returned
```

Raw artifacts, index fields, and standard-model events are filter substrates, not primary query result types.

#### meta

- status: accepted low-resolution first cut

### Simple.Query.Composition

- The first `agentos chatlas query` system should use simple AND composition across all supplied filter flags.
- A session must satisfy every provided filter to be returned.
- This applies across layers: index filters, raw artifact filters, and standard-model filters all compose conjunctively.
- OR groups, nested expressions, ranking, and query DSL behavior are out of scope for the first query system.

#### appendix

Example:

```sh
agentos chatlas query \
  --provider codex \
  --updated-after 2026-05-01T00:00:00Z \
  --raw-contains chatlas \
  --user-contains "query command"
```

The example means:

```text
provider == codex
AND updated_at >= 2026-05-01T00:00:00Z
AND raw artifacts contain "chatlas"
AND user-visible standard model text contains "query command"
```

#### meta

- status: accepted for first implementation

### Query.Result.Projection

- The default query result should be minimal JSON rows, not full index rows.
- Minimal rows should include the canonical session URI plus enough identity metadata to scan and pipe results.
- `session_id` alone is not a sufficient default handle because the canonical session handle is the `uri`.
- Minimal rows should include practical session context when known, including provider home and project path.
- If `home` or `project_path` is unknown, return `null`.
- Additional data should be added through opt-in expansion flags rather than separate overlapping output modes.

#### appendix

Default row shape:

```json
{
  "uri": "agentos://chat-session/...",
  "provider": "codex",
  "session_id": "...",
  "updated_at": "...",
  "home": "/Users/pereiro/.codex",
  "project_path": "/Users/pereiro/projects/agentos-project"
}
```

Candidate expansion flags:

```text
--expand-index
--include-artifacts
--include-match
--include-provider-stats
```

`--expand-index` includes the full session index row for each returned session. `--include-artifacts` attaches backing artifact rows. `--include-match` attaches match provenance and match details. `--include-provider-stats` preserves the current provider-stat expansion model where useful.

#### meta

- status: accepted as first projection model

## Session.Notes

### Open Questions

- Cost controls: should candidate bounds be named `--scan-limit`, `--candidate-limit`, or something else?

### References

- `agentos-md/notes/index/121-Design.Session.md` - canonical design-session backend and section model.
- `agentos-md/skills/hugentics-designer/references/design-index.md` - `Design.Index` block shape and style.
- `agentos-py/notes/live/580-chatlas-index-query-command-impl-req.md` - current low-level index query command implementation request.
- `agentos-py/notes/live/581-chatlas-export-index-selection-impl-req.md` - current export selection behavior context.
- `agentos-py/notes/live/587-chatlas-views-cache-redesign-design-session.md` - related current Chatlas view/export architecture context.

### Scope Boundaries

- `agentos chatlas query` is independent from `agentos chatlas export` and `agentos chatlas raw` command behavior.
- This design does not change whether export or raw commands accept one session or many sessions.

## Session.Log

- 2026-05-14: Created session artifact for `agentos chatlas query` layered command design.
- 2026-05-14: Settled that `agentos chatlas query` should not accept positional query arguments.
- 2026-05-14: Settled simple AND composition across all supplied query filter flags for the first query system.
- 2026-05-14: Settled minimal JSON rows as the default query projection, with opt-in expansion flags for full index rows, artifacts, matches, and provider stats.
- 2026-05-14: Refined minimal query rows to include `uri`, `provider`, `session_id`, `updated_at`, `home`, and `project_path` when known.
- 2026-05-14: Settled a low-resolution first cut where filters return session rows without detailed match provenance.
- 2026-05-14: Settled that missing `home` and `project_path` values should be returned as `null`.
- 2026-05-14: Settled that `agentos chatlas query` design is independent from export/raw command behavior.
