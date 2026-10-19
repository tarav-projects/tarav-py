# Stable Skillware POI identity; blessings pin what they accepted — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: complete, 2026-10-19.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Stop putting `surface_state` (the content hashes of every file of a skill
package) into the situation of Skillware POIs. The situation names the problem
only; `surface_state` becomes a detail, with paths relative to the Project. A
POI Type can name the details a blessing pins, and a blessed action reopens
when a pinned detail differs from what was blessed. Skillware POIs pin
`surface_state`, so an acceptance still cannot float across later edits.

Non-goals: changing other POI Types' identities or blessings; migrating or
deleting existing actions (their store is append-only history).
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

### Agent decisions

- Situation of Skillware analysis and reading-path POIs: `{"subject": ...}`
  only. `surface_state` goes into `details`, keyed by paths relative to the
  package's Project.
- `CheckPOI.pinned_details: ClassVar[tuple[str, ...]] = ()` names the details
  a blessing pins; `SkwPOI` pins `("surface_state",)`.
- `Blessing.reopens(record, poi)` returns true when any of the raised POI's
  pinned details differs from the same detail in the blessed POI the record
  keeps. Types without pinned details keep today's behaviour: a blessing
  holds while the situation exists.
- Existing actions are left as they are. On the first check run after the
  change, the open Skillware actions close as gone and reopen under stable
  identities, once.

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
   Status: done.

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
