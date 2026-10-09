# 893 — Elementary POIs: guidance leaves the POI for its context — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: ready. Replaces request 890.

Remove the `read_first` and `may_do` fields from POI Types. A POI keeps what
an error keeps: its Type and an elementary message, with its situation and
evidence. What a Type's producer wants a reader to know becomes descriptive
notes in the POI's context.

Non-goals: a typed Message; moving notes into action skills (no real POI has
an action yet); changing which POIs are raised.

## Design narrative

The User asked for the consequences of the day's design to be turned into
as many requests as needed and executed.
<!-- tarav.breadcrumb 252ca0fbabeeb3ca4fc75ed754f98ecae7335c3aaa27abdc064dfe2079577c8d -->
<!-- tarav.breadcrumb 3f98a25e78369558fa05df319e19cdeab5026cd3e19c6547677dc70bd0dfd91e -->

A POI is like an error: an object that states an event, with types so it is
expressed clearly; what is done with it is an explicit act by the code, using
primitives such as `throw()`.
<!-- tarav.breadcrumb 3405cc4fd8b11a14deadefec9165458d35d03beb8ecf33d47cfbdb29efb9d28c -->

A POI is the general way to declare that an event happened. The message may
go to another method, to the standard output, may trigger an action, or go
nowhere.
<!-- tarav.breadcrumb df20d3811044639c5177e01d239bf18cd298985eb5b8486278efd116fe040b04 -->

The guidance fields go. More generally their content goes to the POI's
context, where the POI can describe what it was intended to be followed by;
it can also go to an action when the POI is followed by one. The POI itself
keeps something very elementary, such as a message.
<!-- tarav.breadcrumb 8c39631d7006c62dcbf9adcf255cbcde142b7fbd0be03060172d67fc38439870 -->

Earlier the same day: POI wording is descriptive, not imperative, because the
producer cannot know the reader's goal.
<!-- tarav.breadcrumb d71ded179c5bd723abcfefce76a122a457d08a139c6e9d7d3de9806d6f99467c -->

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
