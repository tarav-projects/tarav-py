# 882 — Global Project index — Impl.Req

<!-- tarav.sessions
1ecb7d18 = codex:01a11db9-9ffe-7390-a38b-7b12d4b07714 @1ecb7d185a8f713f39ddd88e8dd5b622aff55d59ec635ba0824227061124aac5
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Status: implemented; product commit pending shared-file scope. Phase: Develop.

Keep a machine-local enumeration of Projects observed through Tarav commands, keyed by the existing portable `project_id`. Add `tarav project list --global` to show remembered Projects, their observed locations, and whether each location still resolves to the same marker. Retain missing paths after a move; a later observation at a new path joins the same identity. An optional explicit root scan populates the index without requiring every Project to be run.

Non-goals: changing Project markers, automatic whole-machine scans, moving directories, resolving duplicate live copies of one ID, and making this logistical index an authority over the marker.

## Design narrative

The User wants a holistic view of Projects, including Projects whose folders moved. They suggested Project commands and `tarav run --project` notify Tarav in the background, with identity by ID and a global list.
<!-- tarav.breadcrumb 2ab0f539fc4e -->

The existing `tarav project list` requires `--root` and scans that directory. Project markers already carry a UUID `project_id`. Project initialization and explicit run/check/harness commands can observe a validated marker without changing the command outcome if the index write fails. An ID alone cannot discover a new path after a move; a subsequent observation or explicit root scan is needed. A global index must expose that uncertainty rather than claim a stale path is current.

The User selected Wiki-backed Develop with autonomous alignment.
<!-- tarav.breadcrumb 39a11fb469f2 -->

### Agent choices

- Store one global JSON index under `~/.tarav/`, respecting `TARAV_HOME`, keyed by Project UUID. Each ID retains observed absolute paths and last-seen times plus a last-observed name. This is a logistical projection; the marker is authoritative.
- On global listing, validate each remembered path against the current marker ID. Report `present`, `missing`, or `different-id`; two present paths for one ID are visibly ambiguous. Do not erase historical paths.
- Successful explicit Project CLI use performs best-effort observation. Avoid hidden filesystem scans or mutation during general library discovery. Existing `--root` listing continues to work and also observes its discoveries. A `--root` value with `--global` may serve as explicit reconciliation scan.
- Use bounded atomic writes with a lock for concurrent commands. A malformed index is an explicit listing error; failed best-effort observation is logged without changing the foreground command result.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant Notes: `projects.md`, `daily/2026-10-08.md`. Supporting session: `codex:01a11db9-9ffe-7390-a38b-7b12d4b07714`. Capture status: committed as `756c65b`.

## Execution.Plan

1. Add the Project index mechanics and tests for observation, moves, duplicate live locations, and unreadable historical paths.
2. Wire global listing and best-effort observation into explicit Project CLI operations, `run`, and `check`; retain existing root listing behavior.
3. Update architecture guidance and CLI help, verify focused tests and CLI behavior, then capture Product.Surface and Wiki evidence and close the scoped work.

## Impl.Log

- Design inspection: `tarav project list --help`, `l1/project/commands.py`, `l0/project` marker discovery, `l3/run.py`, Project Wiki, and Tarav Constitution. Existing worktree contains unrelated edits; preserve them.
- Added a machine-local index under the Tarav home, keyed by marker UUID and recording observed absolute paths and times. Listing revalidates paths, retains missing ones, and exposes duplicate live locations as ambiguous. Atomic writes use a lock. Observation errors are logged without failing a foreground command.
- Added `tarav project list --global`, optional explicit `--root` scan, and observation in Project, run, check, and harness commands. Added move, duplicate/replaced-marker, and CLI scan tests; updated the architecture guide.
- Verification: 31 focused tests passed; full `uv run pytest -q` passed 222 tests; `uv run ruff check src tests` and `git diff --check` passed. An isolated `TARAV_HOME` CLI run of `tarav run --project` then `tarav project list --global --json` reported the root marker ID with a present location. Reinstalled the editable CLI.
- Product.Surface Breadcrumbs submitted on all seven changed product files. Audits resolved with no POIs on the code and test surfaces. `ARCHITECTURE.md` submission succeeded, but its full audit was stopped after a long run among many pre-existing labels; that audit remains open.
- Wiki capture added to `tarav-md/notes/wiki/projects.md` and `daily/2026-10-08.md`; both Breadcrumb audits returned no POIs. Scoped Wiki start `bf94953`, completion `756c65b`.
- The product start checkpoint is `2bc39a8`. Product completion commit remains pending because `src/tarav/l1/project/commands.py` and `ARCHITECTURE.md` have unrelated concurrent edits in the same files. The scoped commit workflow stages whole files, so including them would absorb another request's work. The implementation and tests remain in the worktree for a clean follow-up commit when that overlap has landed.
