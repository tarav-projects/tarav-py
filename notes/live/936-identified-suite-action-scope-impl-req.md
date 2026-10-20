# 936 — Identified suite scope for POI Actions

## Impl.Abstract

Knowledge.Surface: wiki  
Alignment.Mode: Interactive  
Status: executing; user clarified scope.

An Action's `gone` closing path may use the disappearance of its POI only when
the suite that owns the signal ran conclusively. An identified suite for
document A cannot conclude anything about document B. Preserve the existing
behavior where a conclusive parent suite can conclude that a child suite it
previously yielded has disappeared.

## Design narrative

The md-library paragraph alignment workflow produces POIs for missing graph
registration, missing paragraph × reading links, overlap, and low scores. Its
ordinary check loop needs to open Actions and close repaired signals. Two
documents share one depot Project. `ProjectActions.update()` with a standalone
suite for A currently refreshes B's Action and treats A's conclusive suite as
evidence that B's signal is gone. `register()` avoids that false closure but
leaves repaired A Actions open.

The user clarified: a suite for A only knows A; B's Checks have not run. A
`gone` exit is one configurable Action closing path, not a blanket requirement
for every Action. The POI-resolution Action family offers this path. Match the
run's identified suite to the Action's recorded suite chain before deciding
absence. A plain Project suite remains authoritative over its children, and
an identified parent remains authoritative over a child it previously yielded.
No compatibility reader or new persisted Action state is required.

Companion md-library request:
`/Users/pereiro/projects/md-library-project/md-library-py/notes/live/630-paragraph-alignment-checks-actions-impl-req.md`.

## Impl.Req.Wiki

The md-library Project.Wiki owns the user-facing paragraph-alignment design.
This note records the Tarav mechanics dependency and the user's scope
clarification. Exact Chatlas evidence and Wiki completion capture remain in
the companion request.

## Execution.Plan

1. Add a regression with two sibling identified suites. After both Actions
   open, running only A without its POI closes A but leaves B open and marks
   B as `not run`. Verify a parent suite can still conclude a removed child.
2. Amend `POIResolutionAction.on_checks` to use the run root as fallback only
   when it is unidentifed or is in the Action's recorded suite chain. Keep
   present-POI refresh and existing closing policies intact.
3. Run focused Tarav Actions tests and md-library's two-document lifecycle
   test; update architecture guidance for suite-scope semantics.

## Impl.Log

- Design-reality mismatch found in md-library execution: standalone A update
  prematurely closed B. The user clarified that only suites actually run can
  establish disappearance; execution resumes on that basis.
