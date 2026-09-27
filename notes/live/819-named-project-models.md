# Named Project Models

## Impl.Abstract

Knowledge.Surface: wiki. Execute named Project Model selection approved in
the current conversation. Add ls()/get(name), preserving main() and existing
identities. No storage migration or Model creation.

## Impl.Req.Wiki

Product: tarav-py. Wiki: tarav-md/notes/wiki/projects.md and daily/2026-09-27.md.
Evidence: session 01a0d86c-9538-7be1-af96-014cd4203d61, user turns
509f9d6d1c032325 and 3888b312aa5a0a41. Daily and topical Wiki capture
submitted and audited with no findings; Wiki-only closure completed.

## Execution.Plan

1. Read diagram.models as a name-to-Ship mapping, independently of main_model.
2. List names without storage resolution; resolve selected references only.
3. Test empty/malformed mappings, missing names, live marker changes, and
   multiple/shared Model references. Update documentation and capture.

## Impl.Log

Existing product changes checkpointed before edits. Configuration remains
editable JSON; no additional mutation API is introduced in this slice.

Implemented and verified: 48 focused tests passed (Models, Project, and
architecture), Ruff and diff checks passed. Listing avoids storage resolution;
get resolves only after name selection. Existing main behavior is unchanged.
Product implementation remains uncommitted.
