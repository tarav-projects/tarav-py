# 803 — Chatlas TaravObject migration — implementation request

<!-- tarav.sessions
3dbc7074 = codex:01a0baed-f147-77e2-b298-ed15249a9410 @3dbc7074117a70b90f57c98b25690d3ea15a519f0da6e05043e59b8add00d3c4
-->

## Impl.Abstract

- **Status:** Complete.
- **Alignment.Mode:** Interactive.
- **Objective:** migrate independently meaningful Chatlas Normal Model records to registered `TaravObject` classes and remove pseudo-type `class` labels from ordinary Chatlas commands, queries, results, caches, indexes, manifests, and resolution projections.
- **Starting state:** Chatlas produces and consumes Normal Model Events, Messages, Turns, and loaded-context records as raw dictionaries selected by string `class` values. Only `ChatlasTurnReference` currently participates in the runtime Type registry.
- **Boundary:** semantic records use registered Types and `type`; operational and logistical projections remain ordinary Python values. Format-bearing persisted projections may use `schema` and `schema_version`, which do not participate in Tarav Type resolution.
- **Migration:** replace maintained schemas directly. Rebuild disposable indexes and caches rather than adding compatibility readers. Preserve existing Chatlas event, message, and turn addresses and hashes where their semantic inputs have not changed.
- **Out of scope:** Diagram's own legacy `class` envelopes, provider-native raw payload fields, and the separate Breadcrumb POI representation.

The invocation authorizes this bounded design and implementation.
<!-- tarav.breadcrumb eac1ad9551a7 -->

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Project Model:** `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Grounded View:** focused `Tarav.Record` View `7674a926-b123-4dc1-8f55-4be1d6c8624b`; refresh completed without mutations but its retained Namespace source remains stale
- **Semantic Block:** existing `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
- **Impl.Req.Collection:** `803.Impl.Req` — `bbe0e7ac-483d-4400-8ef4-61fa5d17e94f` (`Closed`)
- **Diagram.Draft:** `06498b76-2ac3-4f5f-a618-0b57ff97155b` (`Applied`)
- **Capture.Authorization.Gate:** `c9fccee6-4f7f-44af-b05b-d3134ffa6afd`

## Execution.Plan

### Slice 1 — Semantic Normal Model record classes

- Add registered `TaravObject` classes and strict nested interfaces for Normal Model Events, Messages, Turns, and loaded contexts.
- Make provider normalization and Normal Model finalization pass each complete semantic record through its class before serialization.
- Register the semantic classes in the composed runtime and expose them from Chatlas's maintained library surface.
- Preserve current address and content-hash identity for equivalent source data.
- **Observable:** Normal Model collection rows carry `type`, validate through their registered classes, and retain existing identities.
- **Check:** focused Normal Model record, provider normalization, reference-resolution, and runtime-registry tests.
- **Status:** Complete.

### Slice 2 — Typed semantic consumption

- Route persisted Query input and Chatlas reference resolution through the semantic record classes instead of independently interpreting unvalidated dictionaries.
- Keep structural members such as references, observations, sources, and session metadata as embedded `TaravObject.RecordInterface` models where useful; do not create artificial top-level Types for them.
- **Observable:** invalid semantic rows fail at the class boundary while valid queries and exact Turn references keep their behavior.
- **Check:** Query, rendering, and Chatlas reference tests, including strict invalid-record cases.
- **Status:** Complete.

### Slice 3 — Ordinary projection schemas

- Remove pseudo-type `class` labels from `current-session`, Query/Result/Finding, reference-resolution, and other transient Chatlas projections.
- Replace format discriminators on the Normal Model container, cache metadata, session-index rows, scan caches, derivation caches, and raw partition manifests with explicit `schema` values and advance affected schema versions.
- Rebuild disposable local indexes and caches after installation. Apply a bounded explicit migration to retained raw partition manifests; runtime readers must not repair them implicitly.
- **Observable:** maintained Chatlas output contains `type` only for semantic Tarav records and no Chatlas-owned pseudo-type `class` fields.
- **Check:** CLI, cache, index, raw-manifest, and repository-wide Chatlas schema tests plus a source scan for remaining owned `class` emitters.
- **Status:** Complete.

### Slice 4 — Documentation and closure

- Update architecture guidance to state the Chatlas semantic-record and ordinary-projection boundary.
- Run focused tests, Ruff, architecture checks, the complete suite, reinstall the editable CLI, rebuild local derived Chatlas state, and smoke the public commands.
- Annotate materially contextualized Product.Surface positions through Breadcrumbs.
- Close `803.Impl.Req`, check the Draft overlay, apply it once, and retain the Capture.Receipt.
- **Observable:** installed Chatlas commands expose the new schemas and exact current-session/Turn workflows remain usable.
- **Check:** full project validation and live CLI smoke tests.
- **Status:** Complete.

## Risks and deviation triggers

- If changing a serialized type key changes existing event, message, or turn hashes, preserve the established hash preimage unless the User explicitly authorizes identity migration.
- If a candidate record is merely a runtime instruction, repository service, or derived projection, keep it ordinary rather than assigning a Type Ship for symmetry.
- If a retained projection cannot be migrated or rebuilt without losing non-derived evidence, stop that storage slice and record the boundary rather than adding a silent compatibility reader.
- Existing Diagram assertion, Archive-grounding, Model-staleness, line-type, and View-staleness POIs do not block product mutation.

## Acceptance signals

- Every independently meaningful Chatlas Normal Model collection row is a registered `TaravObject` with a durable Type Ship and exact RecordInterface validation.
- Semantic consumers enter through those classes instead of assigning meaning directly to raw keys.
- Ordinary Chatlas projections do not claim Tarav Type identity and no longer emit pseudo-type `class` labels.
- Persisted nonsemantic formats use explicit schema markers and old disposable state is rebuilt without runtime repair.
- Existing exact Chatlas references continue to resolve after the migration.
- Focused checks, Ruff, architecture validation, and the complete suite pass.

## Impl.Log

- The existing `Tarav.Record` Block is the honest semantic attachment for this request; no new conceptual Block is needed.
- The focused View sync reported no content changes, while its check retained a stale Namespace-source POI. Direct Block rendering supplied current grounded context.
- Initial Draft check succeeded structurally and retained expected semantic-record, Archive-grounding, Model-staleness, and legacy line-type POIs.
- Added six registered semantic Record Types: `User.Event`, `Agent.Event`, `Unresolved.Event`, `Chat.Message`, `Chat.Turn`, and `Agent.Loaded.Context`. Provider normalization and cache/reference reads now validate complete retained rows through those classes.
- Preserved the legacy Event hash preimage while moving the retained discriminator from `class` to `type`; focused identity-continuity coverage confirms the hash remains stable.
- Query remains structurally independent of the Normal Model package. Its persisted reader validates semantic rows at the stream boundary, while exact reference resolution validates again at its semantic boundary.
- Replaced Chatlas-owned pseudo-type labels with ordinary projections or versioned `schema` markers. Explicitly migrated seven retained raw partition manifests and rebuilt 10,098 session-index rows from raw artifacts.
- Validation completed with Ruff, architecture checks, and the full suite (`1174 passed`). The editable CLI was reinstalled and the current session produced Normal Model schema 2 with registered Event, Message, and Turn records.
- Closed `803.Impl.Req` with a 30-day reopen window. Draft `06498b76-2ac3-4f5f-a618-0b57ff97155b` was checked once as the final overlay and applied once; receipt commit `30fa08ef2c947f174ee5ed19d3fc5cfe15cb0010` retains 405 pre-existing/expected Diagram POIs, including legacy line/block typing, Archive grounding, Model staleness, semantic assertion, and closed-collection write findings for the same landing manifest.
