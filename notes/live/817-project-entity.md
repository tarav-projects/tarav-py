# Project entity

## Impl.Abstract

Implement the approved Project entity over existing discovery and marker data.
Preserve project_id, marker contents, and independent Wiki/Models ownership.
Status: implemented and verified. No new attachment registry or storage migration.

Knowledge.Surface: wiki

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki.
Support: current conversation approving Project.from_path and existing identity.
Capture: daily-only capture in tarav-md/notes/wiki/daily/2026-09-27.md,
committed as a3ee048. No topical integration needed for this bounded slice.
Session: codex:01a0d86c-9538-7be1-af96-014cd4203d61,
identity 6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.
User Turns: 6344b0e4fa63ba14 (inspection), 22876c2907dc8db6 (implementation).
Breadcrumbs: 6d91a30390eb8d30bd96f340409ef7304ad78353f804a0e7fa5a0d053a7de15c,
158241df6d671944a4ee7174112b9e5699332c115b6e57f7f35936538389e5ae.
Submission and audit passed with no findings.

## Execution.Plan

1. Add ProjectWorkflow and Project with marker-backed identity.
2. Accept Project in Wiki and Models; register ownership in runtime.
3. Test discovery, unchanged records, detached records, and Context access.

## Impl.Log

- Checkpointed existing Models work before product edits.
- Existing markers lack a Kernel Type reference. Explicit Project.from_path
  interprets them without rewriting data or changing generic dispatch rules.
- Runtime location stays outside the portable marker; detached records cannot
  infer their root. Command adapters are imported explicitly by runtime.
- New constructed projections carry a Type reference; loaded legacy records
  remain unchanged. This satisfies registered example round-tripping without
  broadening Kernel dispatch or migrating retained data.
- Focused verification: 43 tests passed, then all five Project tests passed
  after adding generic typed-marker loading coverage. Ruff and diff checks pass.
- First full-suite run: 1333 passed, one example-dispatch failure; corrected
  by the Type reference on newly constructed projections, then rerun.
- Real project smoke: a source subdirectory resolves tarav-py's existing
  e308d11f-d709-4f23-b8c7-f214e28b3f11 identity and Wiki path, read-only.
- Final full suite: 1335 passed. Installed editable CLI refreshed; project
  command help smoke passed. Product edits remain uncommitted.
