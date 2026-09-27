# Project capability tiers

## Impl.Abstract

Develop the captured core/integration split and explicit Project subtyping.
Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: ready.
Minimal TaravProject handles marker identity/discovery; Project adds lazy
models() and wiki() access. ProjectModels and ProjectWiki live below project,
not in generic Models/Wiki. No automatic execution of project-local code,
marker migration, new attachment schema, or storage rewrite.

## Impl.Req.Wiki

Product: tarav-py. Wiki: tarav-md/notes/wiki/projects.md and
daily/2026-09-27.md. Captured design commit: 7c6489b.
Evidence session: 01a0d86c-9538-7be1-af96-014cd4203d61; user turns
1a2de679427a8005, 0b69fb552001128d, 2f3603d91f37b3d6, 03bc252ce562e0f8.
Completion capture pending.

## Execution.Plan

1. Checkpoint current product; extract TaravProject, retain Project identity.
2. Isolate ProjectModels and ProjectWiki, with lazy convenience accessors.
   ProjectModels.main() uses existing configured storage by default; optional
   resolver injection supports isolated tests. No implicit creation.
3. Verify caller-selected subclasses, unchanged marker identity, import
   boundaries, missing attachments, and normal Context/record behavior.
4. Update docs, run focused/full tests, capture results.

## Impl.Log

The API shape is an implementation choice: project.models() returns the
ProjectModels handler; project.wiki() returns a Wiki via ProjectWiki.open().
Existing marker type tags must not select Python code. from_path selects cls;
generic from_record/load_object retains exact Type dispatch.
