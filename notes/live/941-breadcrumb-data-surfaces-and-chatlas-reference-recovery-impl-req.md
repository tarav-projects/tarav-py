# Breadcrumb data surfaces and exact Chatlas reference recovery

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: developing.
The User requested fixes for the investigated provenance gaps, explicitly
including native JSON and TOML Breadcrumb support. Preserve unrelated Notebook
work and existing evidence targets. No heuristic retargeting of old references.
<!-- tarav.breadcrumb 8f3ccc85c105 -->
<!-- tarav.breadcrumb 0e492270e444 -->

## Design and measured evidence

The investigation found twelve broken Breadcrumbs naming nine User Turns in
session 01a15483-94e8-7fe0-86ad-ddd83e2bae52 (identity 0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a).
Seven Turns (eight labels) resolve exactly from the original rollout alone;
later rollout files reuse native session and record indexes and replace those
events in the aggregate. Two Turns (four labels) resolve exactly with the
pre-voice normalizer on the retained later rollout; their messages still exist,
but newly recognized voice events change their Turn boundaries. See request
935 for the earlier measured collision and raw-retention context. Raw evidence
for all nine targets is retained. Temporary reproduction and reconstruction:
/tmp/investigate-project-manager-references.py and
/tmp/breadcrumb-investigation-reconstruction.json.

JSON uses an explicit `tarav.breadcrumbs` array of strings at a schema-permitted
object position. Marker strings become Breadcrumb label strings without
changing application fields. Ordinary JSON strings remain inactive. TOML uses
native # comments; all basic/literal and multiline strings are skipped. Both
use normal submit/resolve/audit, validate native syntax, and preserve formatting.

Fix cross-rollout collisions in the aggregate by retaining distinct event
variants and remapping their dependent Messages and Context memberships, while
identical observations still merge. Preserve all retained signal rather than
letting record position silently select another event. Keep current aggregate
schema and source navigation. Make collision selection deterministic.

For exact references, retain the addressed Turn, Messages and supporting Events
as a validated immutable snapshot in the Chatlas Record Registry partition.
The existing three-coordinate locator still pins the same exact Turn; resolution
can explicitly report its retained representation. Capture snapshots before
creating new Breadcrumb attachments. Restore the nine historical snapshots
once from exact reproductions; do not ship an old normalizer or guess a new
target. Current Turn lookup and snapshots stay distinct and inspectable.

## Impl.Req.Wiki

Product: tarav-py. Documentation owner: tarav-md/notes/wiki.
Relevant notes: chatlas-normal-model.md, breadcrumbs.md (if present), and
daily/2026-10-22.md. The User's direct fix request and explicit JSON/TOML
instruction supply scope. Implementation observations are not User decisions.
Exact current-session evidence will be attached during closure.

## Execution.Plan

1. Feature: JSON/TOML marker spans, rendering, submit/resolve/audit and native
   validation. Existing unsupported-language failure was measured in request
   940. Verify real CLI round trips, malformed markers, ordinary strings,
   nested JSON metadata and all TOML string forms. Prototype: 29 focused tests
   pass. Add both formats to the public capture guidance and use them on the
   formerly unsupported manager sources.
2. Bug fix: write a failing two-rollout collision regression first, retaining
   both user messages and exact source observations. Remap events and dependent
   messages/contexts with stable conflict identities; shared prefixes dedupe.
   Rerun Normal Model, Query, raw-version, cache and architecture tests.
3. Feature/recovery: validate and retain exact Turn snapshots, resolve references
   and audit them through that path, capture future attachments before loss,
   and restore nine exact historical targets from retained raw. Verify tamper
   detection, immutable writes, current-model loss and all twelve real labels.
   Refresh the affected derived session, run focused and full Project checks,
   inline/Wiki capture, evidence audits, and completion closure.

## Impl.Log

- Start checkpoint e34051b9149285206c667a0682c6ccf809b3ab45 retains existing
  independent Notebook work as found; no changes were discarded.
- JSON/TOML native support and tests are complete. Existing Markdown,
  Python and TypeScript contracts remain supported. No fake JSON comments.
- Cold read confirmed a bounded data-surface change plus independent exact
  reference recovery. No workflow primitive or Project manager redesign needed.
- Concurrent Archive DOI work checkpointed the initial implementation in
  be281910; its later 6058ca35 commit retained the shared architecture test.
  External Archive changes were preserved. The tarav-md start checkpoint is
  0bb5ce5d33fedc21d6b1456b53e02a41c462ee49 (existing Archive documentation).
- Focused verification: 87 tests pass across Breadcrumbs, Chatlas, Normal
  Model collisions, snapshots, Query, cache, index and raw-version behavior.
  Snapshots validate Event, Message and Turn hashes, exact membership, text,
  source observations and pinned coordinates; reads never create storage.
- Recovered all nine historical Turns backing twelve reported labels by
  exact reconstruction from retained raw. Seven used the current normalizer
  on individual tapes, two the historical pre-voice normalizer from Git.
  No historical normalizer is shipped. Snapshots retain the producer commit.
- Rebuilding the session exposed four more previously cited Turn boundaries
  changed by the merge fix. Retained their exact prior hash-checked projection
  and protected all 140 matching existing attachments from that session before
  discarding the diagnostic projection. All three original affected surfaces
  now audit clean: zero POIs, zero errors. Labels and attachments are unchanged.
- The production session cache now holds 10,031 Events, 779 Messages and
  1,554 Turns. Current projection and retained cited representations remain
  explicitly distinct. Raw artifacts were not rewritten by recovery.
- Reindexed exactly the affected session with ChatlasStages.update_index
  policy `all`: one indexed, zero failed. Other sessions were not rebuilt.
- All three slices are verified. The collision regression lost the first
  request before the fix and now retains both with correct raw observations;
  reversed source enumeration gives the same semantic addresses.
- Complete Python verification: `uv run pytest -q` passed 558 tests;
  `uv run ruff check src tests tooling` passed. After the final compact-array
  ordering improvement, all twelve data-surface tests passed again.
- Product capture created 27 Breadcrumbs across 21 code, test, configuration,
  request, skill-source and Wiki surfaces. Final batch audit: 21 OK, zero POIs,
  zero errors. Both the real AGENTS JSON source and pyproject TOML use their
  new native conventions. JSON metadata at the AGENTS source was merged with
  the concurrently captured existing array rather than replacing it.
- Authoritative SKW source was edited and compiled. Four changed generated
  guidance blocks were prepared and recorded explicitly. The two unchanged
  blocks were reviewed against their changed constitutional context and
  explicitly observed; final document lint has no findings. The Project
  prompt is a manual block without a code producer; its compile has no findings.
- The installed editable CLI was reinstalled and exposes both new formats.
  Wiki capture destinations are breadcrumbs.md, chatlas-normal-model.md and
  daily/2026-10-22.md. There are no pending capture gaps on this implementation.
