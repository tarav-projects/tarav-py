# 889 — A general `throw()` on POIs — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design.
Status: ready.

Every POI can be raised as an exception by whoever wants that: `poi.throw()`
raises an exception that carries the whole POI.

Non-goals: making any existing POI interrupt by default; a hierarchy of
exception classes per POI Type; changing what a POI carries (request 890).

## Design narrative

The User planned to give POIs a `.throw()` method that raises the POI as an
exception, in case somebody wants to use it.
<!-- tarav.breadcrumb a232779b7953c0d4e9d5f3ab89661ca9be49a396373c7306f00cdd13584079de -->

It should be general to POI. The exception carries the whole POI, so a caller
that decides to stop still hands the next reader the situation, the code
location and the context.
<!-- tarav.breadcrumb 4607be0967fb8d330ee9c24ce591351aaeba55324ba9d1e79cf43780ea7ee194 -->

### Current behavior (observed 2026-10-09)

- `POIError(poi)` exists in `src/tarav/l1/poi/primitives.py`; it keeps the
  POI as `.poi` and builds its message from the POI's Type, or its check's
  Type, and the identity.
- Only `CheckPOI` can raise it, through `error()`
  (`src/tarav/l1/checks/__init__.py`). The one caller is
  `tests/test_checks_workflow.py`.
- POIs do not interrupt otherwise; `NotificationPOI` emits a warning.

### Agent choices (proposals, not User decisions)

- `POI.throw()` on the base class raises `POIError(self)`.
- `CheckPOI.error()` is removed and its test uses `throw()`: one name, and
  `AGENTS.md` rules out compatibility aliases.
- `POIError` is unchanged.

### Open questions

- None.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md` (section of 2026-10-09), `operator-context.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done (Wiki notes written 2026-10-09).

## Execution.Plan

1. Start checkpoint. Add `POI.throw()`, remove `CheckPOI.error()`, update
   the test and add one for a plain `IdentifiedPOI` and a `NotificationPOI`.
2. Update `src/tarav/l1/poi/README.md`.
3. Focused tests, full suite, Ruff; Breadcrumbs, Wiki, completion commit.

## Impl.Log

- Designed 2026-10-09. Not executed.
