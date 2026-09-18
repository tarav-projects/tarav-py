# Skillware document source

## Impl.Abstract

Status: complete with capture POIs below. Autonomous Develop, impact input from the current chat.
Replace the preliminary invocation store with document-scoped source Records.
Keep generated block outputs in source; mechanically compile the whole product.
Typed arguments, file/block dependencies, locks, generation annotations, and
read-only linting belong to Skillware. No Index/contextualization integration.
Supporting discussion: ../..//../tarav-md/notes/wiki/skillware.md.

## Impl.Req.Diagram

Namespace: 1c99092c-ba46-4006-adc3-9ada50c00abd.
Model: b7b78eab-e5c2-4610-9bf5-1b704a106f34.
Draft: 3f49d0d5-2c2d-4e4a-896f-d7247a62dd91.
Collection: cf0f3676-5d60-4130-ba72-924cd8d3021b (Closed).
Draft applied; receipt commit a64ca1c8f38bb3a57cda6cb78976cd6cd238aba8.
Authorization Gate: a5289967-cd4a-4597-99f9-3ee48dd3938f.
Capture POIs: unasserted semantic records, archive grounding unassessable,
and collection-hosted editions outside primary Model context. Product-context
annotations remain uncaptured; product paths and verification are retained here.

## Execution.Plan

- Implement typed document/generation/lock Records and deterministic compile.
- Implement prompt preparation, explicit generation recording, dependency
  fingerprints, and source/product linting without silent baseline updates.
- Expose library operations through `tarav skw document`; register Record types.
- Test stale source, changed input/output, block dependencies, persistence,
  path boundaries, and CLI. Update documentation and installed tool.

MVP choices: text documents; arrays of lines joined with newline, final newline
for nonempty documents; relative project paths; local block dependencies;
no agent launch or semantic scoring. Existing Markdown compiler remains a
distinct maintained consumer, not an adapter for the new schema.

## Impl.Log

- Project capture context resolved. Git checkpoint c4b070a.
- Implementation refinement: retain the independent typed template helper and
  compose it in `skillware/document.py`, rather than duplicate its validation.
  The new document API owns source/output/lock semantics; no compatibility adapter.
- Implemented runtime Record registration, `tarav skw document` commands,
  documentation, and tests. Full suite initially passed 1381 tests; subsequent
  CLI smoke exposed the handler dispatch key and prompted a regression test.
- Final focused suite: 6 document tests passed, including CLI dispatch.
  Ruff and diff checks passed. Reinstalled editable tool and verified installed
  CLI prepare/edit/record/compile/lint in a disposable project.
