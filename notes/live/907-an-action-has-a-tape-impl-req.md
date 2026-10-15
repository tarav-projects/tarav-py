# 907 — An action has a tape — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

An action that reopens forgets how it closed: reopening clears its closing
record, which then survives only in the Git history of the registry. This
request gives every action a **tape**: one append-only list of typed
entries, one per important event, from which its state is read.

1. Entry Types: `Tarav.Actions.Tape.Opened`, `Closed` (its exit and closing
   record), `Reopened`, `Clean` (one repository seen clean) and
   `ClosingAttempt` (an operator's or the loop's attempt at an exit, with its
   tests). Status entries carry the repository states when suites declare
   them.
2. `state`, `exit`, `started_at`, `opened_at`, `closed_at` and `closing()`
   are read from the tape. The stored fields `state`, `exit`, `started_at`,
   `opened_at`, `closed_at`, `closing`, `closings` and `git` go.
3. Every record of the registry is migrated.
4. The context entry `tape` replaces `closing`, `closings` and `git`.
5. The extension's action page shows the tape.

Non-goals: `sessions`, `intakes` and `operations` (StepAction lists) stay as
they are; the situation axis stays a field; Git remains the full history of
every other change.

## Design narrative

### User decisions

A reopened action had a closing record; the User asked where it is now and
how all this should be interfaced.
<!-- tarav.breadcrumb 4aec507c47fac2e090bafc3a8a72c0f667e5f98679728c52d4f57a28e7b8c6bb -->

Git is how history is kept, and infrastructure must not be duplicated; some
knowledge about the history of closing records would be nice, perhaps an
append-only list beside the current record.
<!-- tarav.breadcrumb 15af8bda1f3c3949ee292254efa59122adb34426ce2f98c1bf33aa14365cbdc9 -->

The User preferred the agent's option of one status log in the action, with
the closings included: a single log, with different entry Types for
different events.
<!-- tarav.breadcrumb ab3aad1c2203150d38e2f9a0bc0360e59114ef16a4b9345e6bc7e9507e0acfb0 -->

Fold the operator's attempts into it, and read the state from it. Name it
`tape`: actions have a tape on which important events are recorded.
<!-- tarav.breadcrumb 39e24f9471b889fa005344fc645734691b67626ac54d7d8de14e34c8361bd7c2 -->

Build it.
<!-- tarav.breadcrumb e439ba3be0888c7dc29fddbb3895b12a5b72fbd819d44cfb17e7316bdb049d9e -->

### Current behavior (inspected)

- `ActionRun` (`l1/actions/__init__.py`) stores `state`, `exit`,
  `started_at`, `opened_at`, `closed_at`, the current `closing` record,
  `closings` (operator and loop attempts with their tests) and, since 905,
  `git` (`{repositories, log}`). `close_run()` writes the closing; the POI
  action's `on_checks()` (`l1/actions/pois.py`) clears `closing`, `exit`,
  `closed_at` and `output` when it reopens. `StepRunner` writes attempts,
  error closings (failed opening, abort: exit `error`, no closing record).
- Readers: `ActionRunStore.list()` (state, exit, `started_at` order),
  `ProjectActions.update()` (`started_at` to know a new action),
  `l1/actions/commands.py` (rows, close output), `views.py`, `l3/status.py`,
  the extension's scripts (`_common.py`) and page (`pages.ts`).
- The registry holds 160 actions: 145 closed, 15 open, 36 with a `git`
  log, none with attempts, one reopened (`fe1e4dca`, whose earlier `gone`
  closing record is in the registry history, commit `93ee414`).

### Proposals of the agent

**Entries.** `tarav.l1.actions.tape` defines `TapeEntry` and the five Types,
written and read through the Record system. Fields: all have `at`; status
entries may have `repositories` (`{root: {commit, clean}}`); `Closed` has
`exit` and `closing` (the closing record, or none for an `error` exit);
`Clean` has `repositories` with one root; `ClosingAttempt` has `exit`, `by`,
`passed`, `results`.

**Reading.** `run.state` is closed when the last status entry is `Closed`;
`exit` and `closed_at` come from it; `opened_at` from the last `Opened` or
`Reopened`; `started_at` from the first entry. `run.closing()` builds the
closing object from the last `Closed` entry. A record must start with
`Opened`.

**Writing.** `tape.opened()`, `tape.closed()`, `tape.reopened()`,
`tape.attempt()` and `tape.clean()` append entries; the 905 rules for
repository states and first clean state per phase move here, and
`tarav.l1.actions.git` goes.

**Context.** `standing` keeps the axes and times, read from the tape; the
entry `tape` lists the entries with the advice of 905.

**Migration.** A one-off script rebuilds each record's tape from its
fields and its `git` log; for `fe1e4dca` the earlier closing comes from the
registry history.

**Extension.** The script gives the page the derived times and closing (the
page does not re-derive them); the page gets a Tape section, one row per
entry, a closing record expandable, repository states as tags.

## Impl.Req.Wiki

Product project: `tarav-py`; also `vscode-tarav-center`. Wiki owner:
`tarav-md`, root `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-14.md`. Supporting chat: session `abd0372d`. Capture status:
done (`poi-system.md`, section "An action has a tape"; daily 2026-10-15).

## Execution.Plan

Core data shape: `ActionRun.tape: list[entry record]`; entry Types in
`tarav.l1.actions.tape`; derived properties on `ActionRun`.

1. Feature — the tape (tarav-py). Entry Types, `ActionRun` fields and
   properties, every writer and reader, context entries; the action tests
   rewritten to read the tape. Check: the whole `tests/`.
2. Migration — the registry. Check: every record loads; `tarav status`
   gives the same open actions; `fe1e4dca` has Opened, Clean, Closed (gone,
   with its record), Reopened.
3. Feature — the extension. Script and Tape section. Check: compile,
   script tests, the record script on a real action, package and install.
4. Docs: `ARCHITECTURE.md`, `tarav-pkg` step-actions.
5. Breadcrumbs, Wiki capture, commits per slice.

Risk: other callers of the removed fields outside the actions workflow;
deviation trigger: a reader that cannot be served by the properties.

## Impl.Log

- Design written from the discussion of 2026-10-14.
- Start checkpoint: tarav-md `7a7dfe9` (the commit rule of the skill); tarav-py
  was clean.
- Slice 1 (`6a19f68`): `tarav.l1.actions.tape` with `TapeEntry`,
  `StatusChange` and the five entry Types, each holding its state as
  attributes (the Record contract test requires it). `ActionRun` stores
  `tape`; `state`, `exit`, `started_at`, `opened_at`, `closed_at`,
  `closing_record()` and `closing()` read it; a record must start with
  `Opened`. `tarav.l1.actions.git` is deleted; its rules live in
  `tape.closed()` and `tape.clean()`. The context entry `tape` (entries and
  advice) replaces `closing`, `closings` and `git`. Tests read the tape.
- Slice 2 (registry `65327fa`): a one-off script rebuilt 160 records; the
  opening always comes from `started_at` (`02063ac8`'s Git log did not start
  at its opening), Git entries added on top. `fe1e4dca`: Opened, Clean,
  Closed (gone, its record recovered from registry commit `93ee414`),
  Reopened. `tarav status` still gives the same 15 open actions.
- Slice 3 (extension `cab36ac`, 0.0.18 installed): script shape 8 gives the
  page `standing` (first opened, opened, closed, closing); the action page
  has a Tape section (one row per entry, the closing record expandable,
  repository states as tags). The old closings table is gone.
- Slice 4: `ARCHITECTURE.md` (the tape, closing records on `Closed`
  entries) and `tarav-pkg/references/step-actions.md` (tape paragraph,
  scenarios Git and Reopen; source block compiled).
- Checks: Ruff clean; the whole `tests/` 442 passed, 1 failed
  (`test_scoped_lines`, another agent's area); doc and architecture tests
  after slice 4: 54 passed.
- Breadcrumbs: audited ok on `tape.py`, `ARCHITECTURE.md`, this note and the
  Wiki.
