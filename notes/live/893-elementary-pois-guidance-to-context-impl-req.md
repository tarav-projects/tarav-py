# 893 — Elementary POIs: guidance leaves the POI for its context — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented. Replaces request 890.

Remove the `read_first` and `may_do` fields from POI Types. A POI keeps what
an error keeps: its Type and an elementary message, with its situation and
evidence. What a Type's producer wants a reader to know becomes descriptive
notes in the POI's context.

Non-goals: a typed Message; moving notes into action skills (no real POI has
an action yet); changing which POIs are raised.

## Design narrative

The User asked for the consequences of the day's design to be turned into
as many requests as needed and executed.
<!-- tarav.breadcrumb 252ca0fbabee -->
<!-- tarav.breadcrumb 3f98a25e7836 -->

A POI is like an error: an object that states an event, with types so it is
expressed clearly; what is done with it is an explicit act by the code, using
primitives such as `throw()`.
<!-- tarav.breadcrumb 3405cc4fd8b1 -->

A POI is the general way to declare that an event happened. The message may
go to another method, to the standard output, may trigger an action, or go
nowhere.
<!-- tarav.breadcrumb df20d3811044 -->

The guidance fields go. More generally their content goes to the POI's
context, where the POI can describe what it was intended to be followed by;
it can also go to an action when the POI is followed by one. The POI itself
keeps something very elementary, such as a message.
<!-- tarav.breadcrumb 8c39631d7006 -->

Earlier the same day: POI wording is descriptive, not imperative, because the
producer cannot know the reader's goal.
<!-- tarav.breadcrumb d71ded179c5b -->

### Current behavior (observed 2026-10-09)

- POI Types may set class attributes `read_first` and `may_do`.
  `guidance_of()` (`src/tarav/l1/poi/reporting.py`) reads them;
  `reported_record()` stores them as `guidance`; `ReportedPOIContext` shows
  entries `read-first` and `may-do`, with imperative default texts.
- About forty Types set them: `l1/project/agents.py`, `l1/project/skills.py`,
  `l1/checks/poi_contract.py`, `l1/poi_tracking/__init__.py`,
  `l2/unsorted/pois.py`. Many `may_do` entries are orders ("Raise it first.").
- `POIGuidanceCheck` raises `POIGuidanceMissingPOI` for each local POI Type
  that sets neither; that accounts for most tracked POIs in the root Project.
- `tests/cli/test_context_command.py` and `tests/diagram/test_diagram_pois.py`
  mention the fields.

### Agent choices (proposals, not User decisions)

- One class attribute on `POI`, `context_notes`: descriptive sentences the
  Type contributes to its POIs' context. It is not part of the POI's record
  (`as_dict`). `reported_record()` keeps them as `notes`, and
  `ReportedPOIContext` shows one entry, `notes`, with a neutral default.
- Every existing text is rewritten as a statement: what the POI means, where
  its producer's documentation is, and what is known to make it stop being
  raised. Orders addressed to the reader ("Raise it first.") are dropped.
- `POIGuidanceCheck` and its POI are removed: a POI without notes is ordinary.
- Stored reports written before this change simply show no notes.

### Open questions

- None blocking.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md`, `operator-context.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: design
discussion captured; implementation capture pending.

## Execution.Plan

1. Start checkpoint. `context_notes` on `POI`; reporting and the reported
   view; remove `guidance_of`, the guidance check and its POI.
2. Rewrite the Types' texts, one workflow at a time; adjust tests.
3. Full suite, Ruff, `tarav check --project` on this workspace and a
   `tarav context` on one reported POI; Breadcrumbs; POI README and any skill
   text naming the fields; Wiki; completion commit.

## Impl.Log

- Designed 2026-10-09.
- Start checkpoint: commit `1258100` (request 892); every file this request
  changes was clean at HEAD except `ARCHITECTURE.md`.
- `POI.context_notes` (class attribute, empty by default, not in `as_dict`).
  `reported_record()` keeps them as `notes`; `ReportedPOIContext` shows one
  entry `notes` in place of `read-first` and `may-do`; `guidance_of()` is
  removed.
- `POIGuidanceCheck` and `POIGuidanceMissingPOI` are removed, and their use in
  `tarav.l2.project.dev`.
- Texts rewritten as statements in `l1/project/agents.py` (15 Types),
  `l1/project/skills.py` (6), `l1/checks/poi_contract.py`,
  `l1/poi_tracking/__init__.py`, `l2/unsorted/pois.py`. "Raise it first." became
  "Its producer intends it to be raised to the User before anything is
  changed."; each resolution became "It is no longer raised once ...".
- Tests adjusted in `tests/cli/test_context_command.py` and
  `tests/diagram/test_diagram_pois.py`; one new test that notes are not part
  of the POI's record. Full suite 266 passed in the shared worktree; Ruff
  clean.
- Real run, `tarav check --project . --tracking skip` on the root: 364 checks
  completed, 54 POIs (about 190 before: the guidance reminders are gone).
  `tarav context --id <id> --view reported-poi --path notes` shows the three
  notes of an agents-file POI.
- `ARCHITECTURE.md` and `src/tarav/l1/poi/README.md` updated. No skill or
  guidance file named the fields.
