# Separate content claims and reading requirements

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

Knowledge.Surface: wiki. Phase: Execute (explicit user implementation request).

## Impl.Abstract

Replace the mixed block `reading` field with `contains`, `reading_deps`, and
`links`. Keep typed declarations and stable entity identities. Content claims
are not owned exclusively by reading analysis. Make positional reading-path
analysis available without requiring a retained loading registry. Preserve
existing optional explicit routes and rendering composition.

## Design narrative

The user chose `contains` for claims that output contains entities and
`reading_deps` for what a reader must know to understand a block. Reading
paths can be computed from position, rather than stored in a compulsory
registry. This is not a request to remove useful explicit cross-file routes.
Links remain separate reference claims, not implicit target loading.
<!-- tarav.breadcrumb 7e34d11a475a44549c38e6bb1f36f6b2838ac934d71f9d6ad0a708fda7103539 -->
<!-- tarav.breadcrumb 2f19bad06dff02ff9c49d030d6c6f79f35e555169134e41c30b9f2e1e2740961 -->

Keep typed declaration records to preserve delivery distinctions and current
composition fields. `links` is the implementation choice for existing links.
Move Contains's base relationship outside ReadingDeclaration while preserving
its TypeShip. Do not build a generalized ontology or infer claims from prose.

## Impl.Req.Wiki

Owner: tarav-md/notes/wiki; reader-context-path.md and daily/2026-09-30.md.
Evidence: current Codex session 01a0d86c-9538-7be1-af96-014cd4203d61,
User Turns 2f959d1ae2e730d2 and dbbff2867d8a6292; confirmation ca1a8951739a7814.

## Execution.Plan

- [ ] Checkpoint selected surfaces, preserving unrelated Lines/Models edits.
- [ ] Split block declarations and update consumers, without legacy fallback.
- [ ] Derive graph bindings from document positions when no loading file exists.
- [ ] Migrate maintained SKW records explicitly; preserve rendered content.
- [ ] Update tests and verify SKW, record contracts, and maintained skills.
- [ ] Capture evidence and close product/Wiki work.

## Impl.Log

Initial inspection: within-file predecessor computation already exists.
SkwSkill.loading() currently rejects packages without a loading field.
SkwBlock has one reading list; IncludesBlock is already a Contains subtype.
Existing l2/skw/skills.py changes disconnect Models and must be preserved.

Implemented split fields with typed declaration validation and explicit rejection
of the old reading field. Contains no longer subclasses ReadingDeclaration;
its TypeShip is preserved. No broad class/module renaming was introduced.
LoadingModel derives ephemeral UUID bindings and within-document predecessor
paths when the package omits loading. Existing optional loading files retain
their explicit routes; linked content is not automatically loaded.

Migrated 23 tarav-hugentics source records with the explicit migration script.
Compared all migrated IDs and output arrays against Git: unchanged. The
historical recipe fingerprint logic excludes the new annotation fields just
as it excluded reading; generation histories were not rewritten or accepted.
The maintained skill build refreshes compilation locks, not generation evidence.

Verification: 64 focused tests passed and Ruff passed. An additional legacy
field rejection test was added afterward for the final verification run.
One consumer-link test now expects an unannotated-output-link POI because
positional checks also run for packages without a loading registry.

The source records are JSON, which has no supported inline Breadcrumb
convention; source metadata is not polluted with invented comments. The
migration code and this request carry the conversational evidence. The
consumer-link test expectation is an implementation observation, not a
separate user design claim.

Final rerun: 65 focused tests passed, Ruff and whitespace checks passed.
All pending evidence submissions completed after continuation. Package build
completed with 14 stale-context and three unannotated-output-link POIs;
no context baselines were accepted automatically. Rendered Markdown remains
unchanged. Completion commit is pending: two touched Python files also retain
earlier uncommitted Models changes, which must not be silently absorbed.
