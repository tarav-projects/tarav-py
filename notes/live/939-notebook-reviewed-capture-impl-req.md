# Notebook reviewed capture staging

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Provide the bounded Python staging needed by the Notebook capture skill:
propose new Blocks/Lines or amend existing Lines without changing live Notebook
records, then land the exact approved change with support and review evidence.
The User requested design followed by execution. The skill owner is
[request 869](../../../tarav-md/notes/live/869-notebook-capture-skill-impl-req.md).
<!-- tarav.breadcrumb d571f6169837 -->

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: executing

## Design

The current Notebook integrates capture/support/review/checks, but capture
persists immediately and record_review expects existing current Lines. Retain
those APIs. Add an ephemeral NotebookDraft, reached through Notebook.draft(),
that stages one coherent cluster under an existing target Block. Its in-memory
candidate is built from fresh persisted records. It supports new recursive
Blocks, new Notebook Lines and amendments preserving Ships and concrete Types.
Plain archive Lines may be cited in new supported captures; this workflow does
not migrate their Types or invent evidence for them.

The draft records a small sequence of additions/amendments, affected original
Line states and the direct-Line context of affected Blocks and ancestors.
Proposal rendering presents destination, operation, new Block placements,
Types, before/after wording and state digests, followed by one opaque token.
An exportable temporary JSON plan lets a later tool invocation restore the same
proposal without inventing new identities or rebasing it silently. It is
workflow transport, not another Notebook database, Model or lineage system.

Discussion and review are separate from focus: an approved proposal can remain
pending while the conversation moves to another Block. Token approval does
not land data. The skill supplies a separate landing command. Landing checks
real proposal/approval evidence, the exact staged presentation, current source
states and context, and new-ID collisions before any writes. It replays only
the declared operations onto freshly loaded data. Unrelated child-Block
additions can coexist; changed semantic context requires a fresh proposal.
This is optimistic preflight, not a transactional/concurrent database promise.
<!-- tarav.breadcrumb dd9a362ae19a -->
<!-- tarav.breadcrumb a102c5fad955 -->

After landing, use existing SupportMember/SupportSet, VerbatimReview and
NotebookCapture mechanics. Each supplied root plus neighborhood produces an
independent support set; several can support the same Line. Missing or invalid
substantive support remains retainable and becomes a check finding. Review
validation governs this reviewed workflow; base capture stays nonblocking.
Preserve previous evidence links on amendments and let state checks mark old
claims stale. No automatic semantic assessment or scoring is added.

Scope: add/amend staging and exact reviewed landing; temporary-plan roundtrip;
Notebook integration; behavioral tests and architecture guidance. No removal
workflow, general drafts registry, lineage, UI writes, changes to Chatlas,
automatic live Model capture or unrelated suite-checkpoint changes.

## Impl.Req.Wiki

Product tarav-py; Wiki owner tarav-md, notes/wiki/line-notebook.md and mandatory
daily 2026-10-20.md. Relevant mechanics: l2/notebook.py,
l2/notebook_capture.py, l1/review, l1/grounding, l1/lines/block.py. Existing tests
test_notebook_evidence.py and test_notebook_integrator.py establish the APIs.
Current skill still points at retired Diagram capture commands; request 869
adds a separate --capture --notebook route without reviving that backend.

## Execution.Plan

1. **Verified — Feature.** Implement NotebookDraft and Notebook.draft(). Data
   shape: operation records, bounded baseline contexts/Line states and sealed
   presentation/token. Verify no writes during staging/proposal/export/restore,
   new recursive Blocks, amendments retaining Ships, exact token checks,
   support/review independence, stale edits/context rejection, preservation of
   unrelated additions, and restored-plan landing through the public API.
2. **Pending — Integration/closure.** Add the test file to Project testpaths,
   update architecture, run focused and full Project checks. Capture code
   Breadcrumbs and commit verified work; finish the dependent skill request,
   topical/daily Wiki capture and completion evidence.

Subtract before adding: reuse the current review renderer, evidence partitions
and checks; introduce no new retained lineage or approval schema. Separate
mechanical replay from agent interpretation. Keep the code below CLI/runtime
composition and avoid imports from the skill or CLI.

## Impl.Log

- Read Notebook, Line/Block, review and support APIs and current capture skill.
  Inspected the Attic manifest and relevant legacy capture/writing documents;
  no historical command was executed. The new user turns are retained through
  this pass's single Chatlas refresh.
- Concurrent suite-checkpoint work is present in both repositories. The start
  checkpoints preserve it as found under the shared commit policy; later
  feature commits stay scoped to this task.
- Cold-read both requests before product edits. Checkpoints: Python
  ca3cb1a8fd9698623443dec7e80a7fc184986c4d and Markdown
  c22cad08abdad997211890e1cc3705a9ae0fbb0e. External work is explicitly marked
  unknown-session; it remains ordinary editable work for its owning task.
- The initial agent design included optional Type promotion. A boundary test
  showed Notebook storage deliberately forbids rebinding a Ship to another
  concrete Type. Removed that unrequested extension: amendments retain Type;
  plain historical Lines need separate new supported captures. The test now
  verifies the actual invariant and no writes, rather than changing storage.
- The first focused run passes 79 tests across draft, integration, evidence and
  architecture. New tests exercise actual public draft/restore/land APIs with
  Normal Model reference fixtures and isolated storage, including byte hashes
  before rejected landings. The initial Type-wording failure was a test fixture
  using the wrong retained Type name; corrected it to Tarav.Notebook.ReviewedLine.
