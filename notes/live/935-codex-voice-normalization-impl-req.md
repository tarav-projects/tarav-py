# Codex native voice transcript normalization

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Normalize native Codex voice transcript segments into the existing Chatlas
Events, Messages, and Turns so retained speech is searchable and addressable.
The User selected Develop after investigation found raw voice text missing
from queries. Tests protect the corrected behavior; they do not preserve the
broken implementation or introduce legacy compatibility paths.
<!-- tarav.breadcrumb fe756abd2202 -->
<!-- tarav.breadcrumb f87ea3cc58bb -->

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: executing

Scope: the existing Codex normalizer, focused executable tests, and relevant
Wiki documentation. Rebuild this exact conversation's derived Normal Model
and Normal Models index, then retrieve the formerly missing passage through
ordinary Query. No raw transcript mutation, new public schemas, Notebook
changes, broad cache invalidation framework, or provider compatibility layer.

## Design

Measured failure: retained raw transcript line 1298 in this session's active
rollout contains a `realtime_item` whose payload is `transcript_segment`,
role `user`, with the complete support-set-root discussion. The existing
Codex normalizer recognizes the rollout format but emits an Unresolved.Event
with no text and no Message for that record. The inspected artifact contains
15 User and 17 Assistant voice segments. Ordinary delegated messages are a
different native path and already appear in queries.

Data shape first: keep existing Event, Chat.Message and Chat.Turn schemas.
Recognize a native voice segment by top-level `realtime_item`, payload type
`transcript_segment`, a string `text`, and role `user` or `assistant`. Map
the roles to existing User/Agent sides and preserve text verbatim, including
whitespace and repetitions. Keep current source observations and address/hash
construction. Unknown roles, missing/non-string text, and voice lifecycle
metadata remain unprojected; they are not fabricated chat messages.

Use one small native-segment classification helper for both Event origin and
Message side; extend text extraction at the same boundary. Existing Turn
assembly already groups consecutive User/Agent Events and excludes unresolved
ones. Do not infer Agent.Loaded.Context relations from speech merely being
recorded. Preserve the ordinary message paths because they remain current
formats used alongside voice; add no compatibility aliases or shims.

Current code: src/tarav/l1/chatlas/normal_model/codex.py, turns.py, pipeline.py;
Query consumes the resulting turns/messages in src/tarav/l1/chatlas/query.py.
Cache freshness depends only on raw input, as ARCHITECTURE.md documents, so
force the rebuild through ChatlasStages policy `all`; do not change that
independent contract. Rebuilding can change hashes for Turns whose actual
membership gains voice Events. Existing references may then correctly report
amendment; do not silently retarget evidence.

## Impl.Req.Wiki

Product: tarav-py. Documentation owner: tarav-md, notes/wiki/.
Relevant topic: ../tarav-md/notes/wiki/chatlas-normal-model.md.
Completion capture appends the voice normalization behavior, source retention
finding, and implementation evidence to that topic and the daily Note.
Reuse exact session 01a15483-94e8-7fe0-86ad-ddd83e2bae52, neutral identity
0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a.
One capture refresh has completed; reuse it across this pass. Support:
63ea3ae7c81d5e35 (Develop), 33b33ff97d269e26 (test/legacy distinction),
a41073fff0d2a51c (investigation), 1b7b646343645954 (recover the missing turn).

## Execution.Plan

1. **Complete — Bug fix — native voice normalization through Query.** Write
   focused tests using a small current-format Codex rollout. Confirm the
   absent voice Message fails first. Map valid User and Assistant segments,
   prove their literal text, raw source links and Query results, typed/voice
   coexistence, same-speaker Turn grouping, malformed/lifecycle exclusion,
   and stable addresses with amended content detected. Include the new test
   file in the explicit pytest testpaths. Run focused and existing Chatlas
   suites, syntax/lint checks, capture supported product Breadcrumbs, and
   commit the verified slice.
2. **Pending — Recovery and closure.** Refresh the installed editable tool,
   rebuild this exact retained session's cache and search index with policy
   `all`, retrieve the raw voice passage by Query, and compare its text with
   the retained segment. Run Project checks including tests. Complete scoped
   topical/daily Wiki capture, Breadcrumb audits and evidence commits.

Boundary discipline: native JSON recognition stays in the provider normalizer.
Subtract before adding: no dead compatibility path exists to remove. Keep the
small common helper local. Deviation triggers: unexpected duplicate/revised
native segment behavior, unrelated hash drift, or invalid current schemas
require investigation and alignment before expanding scope.

## Impl.Log

- Read project instructions, active Wiki context, normalizer/Turn/Query code,
  cache and stage APIs. Direct normalization reproduced the missing segment
  without relying on a stale cache or search index.
- Start checkpoint (Python): 5705e23d66814308cd46f631d2d2f4386110dfd0.
  Both product and documentation repositories were clean before checkpoints.
- Start checkpoint (Markdown): cb6abce5f6da380b0109d223aa890e7f4e9cd92a.
- Cold-reloaded the complete request after registering its two design
  Breadcrumbs. No material ambiguity or API gap found. Execute keeps the
  existing Event/Message/Turn contracts and extends native voice recognition.
- Design Breadcrumb audit: no POIs. Ready for the failing-before check.
- Failing-before: uv run pytest -q tests/chatlas_normal_model/test_codex_voice.py
  produced 2 failures / 7 passes. Both positive cases failed because voice
  Messages were absent; malformed/lifecycle exclusion already passed.
- Fixture clarification: the mixed typed/voice fixture legitimately includes
  one existing typed Agent.Loaded.Context link. Assert that exact link is
  retained and no voice consumption is inferred, rather than expecting none.
- Slice 1 verification: all 38 focused/current Chatlas tests passed; all 9
  new voice cases passed again after Breadcrumb submission. Ruff and diff
  whitespace checks passed. Tests exercise the actual normalization/cache,
  Query and SQLite index, mixed typed/voice records, seven excluded native
  forms, provenance, and amendment hashes.
- Product capture: code a80c6afe4a0f; tests 891ba9df18b1. The request's two
  Breadcrumbs and both product labels audited without POIs. pyproject.toml
  has no registered native embedding convention; no annotation syntax was
  invented. Its one routing entry makes the voice tests part of normal checks.
