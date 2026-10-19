# Stable Skillware POI identity — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: complete, 2026-10-19.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Stop putting `surface_state` (the content hashes of every file of a skill
package) into the situation of Skillware POIs. The situation names the problem
only, and `surface_state` is dropped from Skillware POIs altogether. A
blessing accepts a situation: when a fact relevant to the check changes, the
check raises a different POI, which the blessing does not cover. Details carry
no meaning. Audit the other POI Types for the same principle and fix what
breaks it; delete the action records whose identities no check can raise.
<!-- tarav.breadcrumb e1db2d92f63d -->
<!-- tarav.breadcrumb 9e16fa1b0142 -->

## Design

### Why

A POI's identity is its Type plus its situation. Skillware POIs carried
`surface_state` in the situation: 39 content hashes for `tarav-hugentics`,
keyed by absolute paths. Any edit to any file of a package gave every open
Skillware problem a new identity: the next check run closed the old action as
gone and opened a new one for the same problem. Measured 2026-10-19 over the
action store: 116 actions with `surface_state` for 43 distinct problems (Type
plus subject), 110 closed as gone, 6 open; several problems hold 8 actions.
Absolute paths also make identity machine-specific.
<!-- tarav.breadcrumb 8408e1d9322a -->

The state was put there deliberately, as a code comment in
`l2/skw/pois.py:surface_state` says: "so an acceptance cannot float across
later source edits". The goal stays; identity was the wrong place for it.

### Decisions (User)

- The situation of action `0338c321` (an `OutputChanged` for block `boundary`
  in `src/SKILL.skw.json`) is off: it carries `surface_state`.
  <!-- tarav.breadcrumb ba932b0a3092 -->
- Develop the proposed fix.
  <!-- tarav.breadcrumb 8950aa5ca626 -->
- Correction: a blessing relates to the situation; the situation describes
  what is relevant about the check; details are only what Agents may like to
  have, possibly nothing. No pinning, no `surface_state` in details.
  <!-- tarav.breadcrumb ec7edde0f2e1 -->
- Check around for violations of that principle.
  <!-- tarav.breadcrumb a0d923eccd1a -->
- Delete the churned action records; fix all the violations found.
  <!-- tarav.breadcrumb 8094892ec8ed -->

### Agent decisions

- Situation of Skillware analysis and reading-path POIs: `{"subject": ...}`
  only; no package state anywhere. These Types are not blessable, so the old
  "acceptance cannot float" reason never applied to them.
- Superseded (slice 1, reverted): `CheckPOI.pinned_details` and a
  `Blessing.reopens` that compared details.
- System Project: `ActiveProjectDoesNotLoad` names the Project by UUID; an
  `ActiveProjectMissing` has no Project, so its situation is `{"path": ...}`.
- Delete the action records whose identities no current check can raise:
  situations carrying `surface_state`, and situations naming Projects by
  absolute path (before Project UUIDs). The partition is a Git repository, so
  the deletion is recoverable.

## Current implementation observations

Inspected 2026-10-19:

- `src/tarav/l2/skw/pois.py`: `surface_state(package)` (absolute paths),
  `_analysis_pois` passes it as `state`.
- `src/tarav/l1/skw/pois.py:72` `from_finding(...)`: `held = {"surface_state":
  state}` merged into the situation.
- `src/tarav/l2/skw/reading_checks.py:50-55`: situation `{"subject": ...,
  "surface_state": state}`.
- `src/tarav/l1/poi/primitives.py:SituationPOI`: identity =
  `fingerprint([class_id, situation])`; `CheckPOI` adds `details`, outside
  identity.
- `src/tarav/l1/actions/blessing.py:Blessing.reopens` returns False; the
  record keeps `poi` as it stood. `src/tarav/l1/actions/pois.py` asks the
  closing whether a raised POI reopens a closed action.
- Tests: `tests/test_actions_workflow.py`
  (`test_a_blessed_action_stays_closed_while_its_poi_is_still_raised`),
  `tests/test_skw_poi.py:317` asserts `surface_state` is not in details.

## Impl.Req.Wiki

- Product project: `tarav-py`. Wiki: `tarav-py/notes/wiki/`.
- Capture status: see Impl.Log.

## Execution.Plan

1. Feature — blessings pin details. `CheckPOI.pinned_details`,
   `Blessing.reopens` compares them. Check: new test in
   `tests/test_actions_workflow.py` (a pinned detail that changes reopens a
   blessed action; one that stays does not; unpinned Types unchanged).
   Status: done (d93d624).
2. Bug fix — Skillware POI identity. Situation without `surface_state`;
   relative paths in details; `SkwPOI` pins it. Check: a test that the same
   finding keeps its identity after an unrelated package edit; the existing
   `test_skw_poi.py` expectation updated; real `tarav status --project
   tarav-md` before and after, counting open Skillware actions. Status:
   done (bec7bc8).
3. Docs — ARCHITECTURE if it states the Skillware situation; Wiki daily.
   Status: done, then corrected in slice 4.
4. Correction — revert pinning, drop `surface_state`, System Project by
   UUID, delete dead action records. Status: done.

## Impl.Log

- 2026-10-19: request written in the session above.
- Execute (same session). Start checkpoint 3daed55.
- Slice 1: `CheckPOI.pinned_details`; `Blessing.reopens` compares the pinned
  details of the raised POI with the blessed POI's. New test failed first
  (`(0, 0) == (0, 1)`: the blessing held although the pinned bulb changed),
  then passed; 40 Actions and POI tests pass. Commit d93d624.
- Slice 2: reproduction `test_a_problem_keeps_its_identity_when_another_
  package_file_changes`: editing an unrelated package file gave the same
  `SourceUncompiled` a new identity. `ProductDrift` was never affected (it
  names its own state); `OutputChanged` needs a recorded generation, so the
  test uses `SourceUncompiled`, which shares the general path. Fix:
  `surface_state` in details, relative to the package's Project; `SkwPOI`
  pins it. The existing assertion that details hold no `surface_state` never
  reached the general path (only `ProductDrift` was raised there); it now
  asserts that the situation holds none. Real surface, `tarav status
  --project tarav-md` twice: run 1 "6 opened, 6 closed as gone" (the
  one-time re-identification); run 2 "nothing". The re-identified action
  402ede9b keeps only `{subject}` as its situation and 39 Project-relative
  paths in its details. Suite 393 passed. Commit bec7bc8.
- Slice 3: ARCHITECTURE's Blessings row states pinned details; Wiki daily.
- Slice 4 (User correction): slices 1 and 2's pinning reverted:
  `pinned_details` and the detail-comparing `Blessing.reopens` removed, with
  their test; `surface_state` removed from Skillware POIs (and its helper).
  The identity test now asserts the situation is `{subject}` and the details
  hold no package state. Audit for the principle: code lookups are by
  identity; `StaleContext` churn is by design (`current_context` is relevant);
  `ActiveProjectCheck` named Projects by absolute path, now by UUID (missing:
  by active path). Action partition: deleted 1018 of 1190 records (116 with
  `surface_state` in the situation, 902 naming Projects by absolute path),
  partition commit 33b0348. `tarav status --project tarav-md` twice: 68 open,
  "nothing" both runs. Suite 392 passed.
