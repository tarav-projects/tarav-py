# 827 — Git commit evidence — implementation request

<!-- tarav.sessions
c6489f81 = claude-code:7f975c3c-3c91-4175-9071-0d132b06c356 @c6489f818b92448026b517c5019e576ec5d78b1470a8a3edc5fc4b06b4a469a8
-->

## Impl.Abstract

- **Status:** Implemented.
- **Knowledge.Surface:** wiki.
- **Alignment.Mode:** Interactive.
- **Requested result:** a best-effort workflow in which the agent that did the
  work attaches Chatlas User-Turn evidence to its Git commit messages, grouped
  by change, through Breadcrumbs whose surface is the commit message itself.
- **Scope:** a commit-message Breadcrumb locator and its observations in
  `tarav.l1.breadcrumbs`; preparation, registration, resolution and audit for
  that surface; manifest-driven Git staging and committing; a shared skill
  module for composing evidence commits; bracketing
  commits in modifying Hugentics workflows.
- **Non-goals:** requiring complete evidence coverage; proving that a change is
  faithful to its turns; guaranteeing that only the agent's work lies between
  bracketing commits; per-hunk evidence; a git hook; message-content hashing.

The user asked for this implementation-request design in `tarav-py`.
<!-- tarav.breadcrumb 74645a096cba -->

## Design narrative

### Why

Tarav aims to make agent work auditable and accountable. Transcripts exist,
but auditing them without mechanics is too expensive, and using agents to
check agents is recursive: the checker shares the error rate of the checked.
The user's direction is to prefer procedural, code-based checks and to keep
agents from long reasoning chains that drift from user intent by making them
attach evidence to what they do. Commit evidence runs in parallel with the
existing Wiki and Product.Surface Breadcrumbs; none of these layers needs to
be complete on its own.
<!-- tarav.breadcrumb 3bf2bce1b1b7 -->
<!-- tarav.breadcrumb 85a3223b17e0 -->

Proposal (agent): the author only points; it does not prove. An audit then
reduces to a narrow question — "does this turn support this change group?" —
which is cheaper and less error-prone than an open review.

### Behavior (user decisions)

- Best effort. Missing evidence coverage does not demand extensive work. The
  committer records what it knows. If the committing session did not do some
  of the work, it says so with a standardized marker. Large changes may be
  split into commits by evidence group.
<!-- tarav.breadcrumb 0193c9268232 -->
- The message format resembles the draft shown in chat and is compatible with
  Breadcrumbs. The original discussion proposed a temporary message file;
  the follow-up below refines this into a temporary JSON manifest, with Tarav
  preparing and checking the message before committing.
<!-- tarav.breadcrumb 2107b5f6d0ad -->
- The commit message is its own surface, distinct from files inside the
  commit, and needs an explicit Breadcrumb workflow because Breadcrumbs are
  registered records, not only inline labels. Instead of a file position, the
  locator stores commit-relative data such as the parent and the last few
  (three to five) commit hashes, so agents can later research the repository.
  The goal is to leave as much evidence as practical of which discussion
  triggered or justified each modification.
<!-- tarav.breadcrumb 12d4d5ecb166 -->
- The message is full of Breadcrumb IDs and therefore easy to find; hashing
  its content is optional. The critical concern is cost-benefit: the agent
  that did the work should commit it. Skills that modify things — capture and
  implementation skills — commit at their start and at their end. The start
  commit is a checkpoint. The original proposal swept up earlier uncommitted
  work; the follow-up replaces that with agent-declared scope. An empty start
  is fine; broader direct commits remain a separate action.
<!-- tarav.breadcrumb 0eaaeb77ed0b -->

### Message shape

```text
<subject>

<!-- tarav.sessions
c6489f81 = claude-code:<native-id> @<identity-hash>
-->

- notes/wiki/inbox.md, AGENTS.md: journal inbox rule
<!-- tarav.breadcrumb <id> -->
- src/tarav/l1/breadcrumbs/model.py: commit locator
<!-- tarav.breadcrumb <id> -->
- tests/…: formatting only
<!-- tarav.evidence agent-initiated -->
- src/…: pre-existing edits
<!-- tarav.evidence unknown-session -->
```

The example illustrates the human-readable groups. The final message must
also retain the mapping from each Breadcrumb ID to its typed evidence
references, so registration can be recovered from the commit alone. Session
declarations and bare Breadcrumb IDs are insufficient for that mapping.
Preparation may consume provisional `tarav.context` markers, but must retain
their evidence in the final message rather than replace and discard it.
Choose a minimal machine-readable encoding during implementation and test its
round trip. Preserve message content explicitly through Git message cleanup.

Proposal (agent): the two non-Breadcrumb markers stay distinct because they
mean different things — `agent-initiated` names who decided;
`unknown-session` is an honest gap.

### Current behavior (inspected)

- `LocatorObservation.locator` is strictly
  `FilePositionReference.RecordInterface`
  (`src/tarav/l1/breadcrumbs/model.py`).
- `BreadcrumbStore.observe_position` and `resolve` assume file positions
  (`src/tarav/l1/breadcrumbs/store.py`); resolution requires an exact label at
  a recorded file line and never falls back to hints.
- `submit_annotations` writes a file-position observation for the submitted
  surface (`src/tarav/l1/breadcrumbs/surfaces.py`). Submitting a temp file
  today therefore leaves every Breadcrumb pointing at a file that disappears
  after the commit.
- Annotation workflows own attachments; `chatlas-context` is the only one
  (`src/tarav/l2/breadcrumb_workflows/chatlas_context/`). Surface language is
  inferred from the file suffix (`.md`, `.py`).
- `src/tarav/l1/references/git.py` already offers read-only Git helpers and
  `GitFileReference`.
- `tarav-hugentics` Execute policy (`references/impl/execute.md`) creates one
  checkpoint before product edits and explicitly **no** automatic commit at
  completion, leaving changes for User review. The bracketing decision
  replaces that policy. The default Wiki implementation module
  (`references/impl/wiki.md`) also needs the corresponding update.

### Design

Proposal (agent): the commit message is a new **surface/locator kind**, not a
new attachment workflow. Attachments remain `chatlas-context`, so the same
typed Chatlas Turn records, submission, and audit apply; only where the label
lives changes.

- **Manifest (follow-up user decision).** The agent supplies a JSON file
  declaring the repository, files to add, commit message and Breadcrumb
  evidence. The manifest may be temporary. The agent owns file selection and
  the semantic justification; Tarav does not infer authorship, compare edits
  with the discussion, or require hunk selection or path-coverage checks.
- **Register Breadcrumbs before committing.** Tarav validates the manifest and
  evidence references, creates or reuses each Breadcrumb, and attaches its
  typed evidence before Git mutation. It then renders those stable IDs and the
  recoverable evidence mapping into the message. Incomplete coverage is
  allowed through the explicit non-Breadcrumb markers. Breadcrumb identity is
  independent of any one surface location, so it may exist before the commit.
- **Commit and observe.** Once preparation succeeds, Tarav stages the declared
  files, commits the prepared message, then appends an observation with the
  actual commit hash and message line to each Breadcrumb. Preserve unrelated
  staged changes outside that selection. No nullable commit locator is needed.
- **`GitCommitMessagePositionReference`** — locator: `repository`, exact
  `commit` hash and `line`; hints may include parents and recent first-parent
  ancestors. Resolve the recorded commit message and verify the label at the
  recorded line. Hints never silently substitute another commit.
- **Independent registration.** Registration also accepts an existing commit
  and reads all required IDs and evidence from its message. It creates missing
  Breadcrumbs or reuses matching ones, then completes missing attachments and
  observations without duplicates. Conflicting records are reported, not
  overwritten.
- **Failure recovery.** If Git fails, the registered Breadcrumbs remain valid
  without a commit-message observation and may receive another location later.
  If the commit succeeds but observation fails, report its exact hash and
  findings. Retry registration on that commit, without creating another commit
  and without needing the temporary manifest. Partial registration is resumable.
- **Historical locations.** Amending or rebasing does not itself invalidate an
  observation: the original commit remains resolvable while Git retains it.
  Registering a replacement commit can append another location. An inaccessible
  recorded commit is an unavailable location, not a pending pre-commit record.
- **Generalized observation.** `LocatorObservation.locator` accepts either
  reference type; `resolve` dispatches on the locator type.

### CLI (proposal)

```text
tarav git commit --manifest <manifest.json>
tarav breadcrumbs register-commit --repo <repo> --commit <hash>
tarav breadcrumbs audit chatlas-context --commit <rev> --repo <repo> --json
```

Tarav owns the Git operations for the manifest command. Both commands share
the same registration mechanics. Resolve revisions to exact hashes before
recording observations. This CLI shape is the proposed adapter; expose the
mechanics through Python as well, respecting dependency layers.

### Package organization and Python interface

The follow-up discussion selects a Git Workflow for repository operations,
with Breadcrumb integration one dependency layer above it:

```python
# General Git mechanics.
from tarav.l1.git import GitWorkflow, GitRepository

# References to immutable Git surfaces.
from tarav.l1.references.git import GitCommitMessagePositionReference

# Git commits carrying Breadcrumb evidence.
from tarav.l2.git.breadcrumbs import (
    CommitManifest,
    prepare_message,
    commit_from_manifest,
    register_commit,
)

# CLI composition.
from tarav.l3.git.commands import register_commands
```

These are target imports for this implementation, not claims about existing
APIs. `l1.git` owns repository operations and remains independent of Breadcrumb
and Chatlas attachment policy. `l1.references.git` retains the existing
read-only Git reference helpers and owns the commit-message reference.
`l1.breadcrumbs` owns generic observation and resolution support.

`l2.git.breadcrumbs` combines Git, Breadcrumbs and attachment workflows. It
owns manifest validation, message preparation, the commit-and-register flow,
and registration from an existing commit. Both CLI entry points use these
same Python mechanics. `prepare_message` validates the manifest, creates or
reuses Breadcrumbs, attaches their evidence, and renders the recoverable
message; `commit_from_manifest` performs the complete flow; `register_commit`
supports independent recovery and post-commit observation.

`l3.git.commands` exposes the Git command adapter; the Breadcrumb CLI exposes
its registration/audit entry points through the same integration. Installed
runtime composition registers the Workflow and concrete Types explicitly.
Keep imports directional and update `ARCHITECTURE.md` and architecture tests
with these boundaries. Implement only the Git mechanics needed by this slice.

### Skill integration

- A shared `tarav-hugentics` module, `references/commit-evidence.md`,
  describes manifests, markers, validate → stage → commit → register, splitting by
  evidence group, and the two `tarav.evidence` markers.
- Modifying workflows reference it for their bracketing commits: Wiki capture
  and Design Dialogue (the existing Git closure becomes the end commit),
  Model capture, and implementation Execute/Develop/Harvest. Read-only routes
  (audit, ground, review) never commit. Multi-repository work brackets each
  repository separately. Automatic commits use the files the agent declares
  for its work; they do not sweep unrelated repository edits. Broader direct
  commits remain available when separately requested. Start checkpoints obey
  the same scope; an empty checkpoint must not expand the selection.
- Skill sources live in `tarav-md/skills/tarav-hugentics/` and are rebuilt
  through SKW.

### Implementation choices

- The bracketing decision replaces the old no-end-commit policy. Update both
  Wiki-backed and Model-backed implementation instructions; no renewed
  alignment is needed for this already chosen behavior.
- Wiki capture uses the shared manifest commit flow with its declared files.
  Preserve existing `Wiki.commit` callers as appropriate; a message-file API
  extension is not required just to pass multiline text.
- Audit validates the Breadcrumbs present and their attachments. It does not
  assess path coverage, authorship or semantic support of changes.

## Impl.Req.Wiki

- **Product project:** `~/projects/taravangian-project/tarav-py`.
- **Wiki root:** `tarav-py/notes/wiki/`; related:
  `best-effort-mechanics.md`.
- **Skill sources:** `tarav-md/skills/tarav-hugentics/`.
- **Supporting discussion:** journal dialog
  `~/Documents/tarav/journal/notes/wiki/dialogs/commit-evidence-breadcrumbs.md`
  (commit `e2d393d`), session `c6489f81`.
- **Capture status:** original journal capture retained. Implementation closure
  updated `best-effort-mechanics.md` and the 2026-09-29 daily Note from session
  `1f561f5d`; all newly submitted Breadcrumbs resolve and audit cleanly.

## Execution.Plan

### Slice 1 — Commit-message locator

- Add `GitCommitMessagePositionReference` beside `GitFileReference`, with
  exact resolution against `git log -1 --format=%B`.
- Widen `LocatorObservation.locator` to the file/commit union; add
  `observe_commit_position`; dispatch `resolve` by locator type. Commit
  locators always carry the actual hash.
- **Check:** record round trips; resolution in a temporary Git repository,
  including amended-commit and missing-commit POIs.

### Slice 2 — Message preparation and existing-commit registration

- Validate evidence, create or reuse Breadcrumbs, attach their typed evidence,
  and retain a self-contained mapping in the prepared message.
- Add `register-commit` to recover missing Breadcrumbs or attachments and add
  exact message locations from an existing commit alone.
- **Check:** prepared IDs match retained Breadcrumbs; registration survives
  deletion of the manifest; repeat and partial registration resume without
  duplicate attachments or observations.

### Slice 3 — Manifest-driven Git commit

- Add `GitWorkflow` and `GitRepository` under `tarav.l1.git`; place the
  evidence integration in `tarav.l2.git.breadcrumbs` and its Git CLI adapter
  in `tarav.l3.git.commands`, following the target imports above.
- Implement the manifest contract and Python/CLI flow: validate the message
  and references, register Breadcrumb identity and evidence, stage declared
  files, commit, then observe the commit-message locations.
- **Check:** selected files only, unrelated staged changes preserved, malformed
  message rejected before Git mutation, Git failure leaves valid unobserved
  Breadcrumbs, and observation failure reports the created hash and can be
  retried separately.

### Slice 4 — Commit audit

- Let `audit chatlas-context` take `--commit/--repo`, reading labels from the
  commit message and reusing existing attachment checks.
- Recognize `tarav.evidence agent-initiated|unknown-session` as valid
  non-Breadcrumb markers.
- **Check:** audit tests covering resolved, unavailable, unregistered and
  marker-only groups. Do not introduce a pre-commit pending locator.

### Slice 5 — Skill module and workflow integration

- Write `references/commit-evidence.md`; reference it from Wiki capture,
  Design Dialogue, Model capture, and both Wiki and Model implementation routes;
  rebuild through SKW.
- **Check:** skill lint/build; one real evidence commit on a scratch repo.

### Validation

Focused tests per slice, Ruff, `tests/test_architecture.py`, full suite,
`uv tool install --reinstall --editable .`, CLI smoke.

## Impl.Log

- 2026-09-29 — Implemented the Git Workflow, immutable commit-message
  reference, generalized Breadcrumb observations, manifest preparation,
  scoped commit operation, recovery registration, and commit audit. The Git
  operation uses an isolated temporary index so unrelated staging survives.
  Breadcrumbs and typed Chatlas attachments are retained before Git mutation;
  the exact commit observation is appended afterward.

- 2026-09-29 — Added the public CLI routes from this request and covered their
  combined commit → recover → audit path. Added runtime registration and
  architecture boundaries. Focused Git evidence, Breadcrumb, reference,
  architecture, Record-contract, and Ruff checks pass; the complete test
  result is recorded after final validation below.

- 2026-09-29 — Final validation: Ruff passed, 1,396 tests passed, the editable
  tool installation succeeded, and installed CLI help exposed manifest commit,
  existing-commit registration, and commit audit. The focused CLI test also
  executes the complete marker-only commit → recover → audit path.

- 2026-09-29 — Added the shared Hugentics commit-evidence module and linked it
  from modifying Capture, Wiki capture, Design Dialogue, and implementation
  routes. Rebuilt the generated skill products through SKW. The package check
  now reports 15 existing unrelated POIs and no unreachable or stale output
  introduced by this slice; those findings were left unblessed.

- 2026-09-29 — User clarified that Breadcrumb identity and evidence may be
  registered before the Git commit. The commit hash is a later locator
  observation. Replaced the unregistered-ID preparation design with
  register → commit → observe; a failed Git operation may leave a valid
  Breadcrumb without that commit location.

- 2026-09-29 — User accepted the package organization: general Git operations
  in `l1.git`, Git surface references in `l1.references.git`, commit evidence
  integration in `l2.git.breadcrumbs`, and CLI composition in `l3.git.commands`.
  Added target imports and responsibilities to the implementation contract.

- 2026-09-29 — Follow-up discussion in the current Codex session introduced a
  temporary manifest and Tarav-managed Git operations. The user assigns file
  selection and message authorship to the agent. A separate existing-commit
  command supports recovery. Automatic commits are scoped to agent-declared
  work; broader commits are separate. The nullable locator and pending-
  observation designs were rejected. Product implementation has not started.

- 2026-09-29 — Design drafted from session `c6489f81`. Inspected
  breadcrumbs l1 model/store/surfaces/workflows, chatlas-context workflow,
  `references/git.py`, and Hugentics Execute checkpoint policy. The initial
  alignment questions were resolved by the later decisions above.
