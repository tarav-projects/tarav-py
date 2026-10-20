# Notebook capture: support and review evidence

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Phase: Execute
Status: executing
Product: tarav-py. Documentation owner: tarav-md.

Implement the evidence-producing part of Notebook capture: small reusable
support and review primitives, explicit retained links to evidence, Notebook
specializations, and automatic mechanical checks. Use the Project Model as
the concrete example. Stop before semantic Assertion evaluation and scoring
integration; the User explicitly deferred those mechanisms.
<!-- tarav.breadcrumb 8cec09071401 -->

All newly captured Notebook Lines must carry support from User-touched data,
normally specific Chatlas User turns. A reviewed part additionally requires
explicit User approval of the presented wording or change. Agent-maintained
parts can evolve without verbatim review but retain the support requirement.
These are independent axes, not successive confidence levels.
<!-- tarav.breadcrumb 0e44852a55fd -->

This request supplies Python-first capture and inspection operations. A new
skill route, extension UI, general Notebook editor, product/code alignment
engine, semantic claim propagation, and LineTrace implementation are outside
this bounded pass. Existing read-only Notebook grounding remains operational.

## Accepted design and rationale

### Minimal primitives, composed capabilities

Lines and recursive Blocks remain the general expression primitives. Support,
review and edition-handling behavior are capabilities supplied by particular
Types and their workflows. Establish small identified workflow roots and base
Types, then implement only the Notebook example deeply enough to capture,
reload, inspect and check its evidence. Do not create a broad framework of
empty methods or attach mandatory chat fields to the base Line.
<!-- tarav.breadcrumb 25e5c25934c0 -->
<!-- tarav.breadcrumb 7c312f45fb8c -->

Support means the captured content summarizes material already established
in the selected discussion. It is an explicit attributed claim, not proof
that a referenced turn justifies the wording. A reference to a rejected
alternative cannot mechanically establish acceptance of that alternative.
Keep authoring context separate from support: a Line's own Block and ancestors
still determine its intended reading.
<!-- tarav.breadcrumb a203f7a301b5 -->
<!-- tarav.breadcrumb acdadf330fd1 -->

### Two independent evidence paths

1. User support: a nonempty SupportSet whose members identify substantive
   User-touched evidence. The initial concrete member uses an exact Chatlas
   User turn and may carry explicitly selected contextual neighbor references.
   Neighboring Agent text provides context; it is not silently promoted into
   substantive User support. Retain the producing Agent turn separately when
   recording a conversational capture.
2. Verbatim review: a review record identifies the reviewed Line state or
   bounded Block change, the Agent proposal turn, the later User approval
   turn, and a shared opaque token. The proposal states the destination and
   operation and presents the exact wording. The User explicitly approves
   the token. The review can be added later without rewriting support.

An approval turn is not automatically substantive support. One turn may fill
both roles only through distinct explicit claims justified by its content.
Support, producer, review and operation authorization retain distinct roles.
This pass implements support and verbatim review; no generic authorization
framework is required.
<!-- tarav.breadcrumb 12eba065ac8b -->
<!-- tarav.breadcrumb 038079aa83b7 -->

### Evolution without a mandatory LineTrace

A simple Line keeps its Ship while its text changes; Git preserves older
records. Evidence must name the particular state it concerns. A change does
not rewrite old support or approval into evidence for the new state. The
simple path reports a stale or missing current-state relationship and allows
fresh evidence to be attached. It does not infer semantic continuity.
<!-- tarav.breadcrumb 57af430c3665 -->

Implement the minimum state coordinate needed for this behavior: subject
Ship, concrete Type and a deterministic fingerprint of captured wording and
its declared interpretive context. Preserve the corresponding bounded
snapshot in the evidence record so it is inspectable before any Git commit.
For a Block/change review, retain an explicit ordered target set and operation;
approval never implicitly covers every future descendant. Relevant ancestor
context changes must be detectable, as well as Line text changes. Exclude
support/review attachments from that fingerprint to avoid recursive invalidation.
This state-coordinate design is an implementation proposal, not a new general
history API. Keep the representation reusable and small; no history crawler,
edition collection, automatic claim carry or commit prerequisite.

### Notebook requirements

Provide a supported Notebook Line specialization and an explicitly reviewed
specialization or composed capability. Block Types declare the requirements
for their subtree; reviewed children retain the support obligation. Explicit
review is opt-in for a selected part, not a requirement imposed on the whole
Model. Descendant configuration must not silently weaken an inherited
requirement. Do not materialize a mandatory reviewed/unreviewed folder layout.

Existing imported Archive records and seed context Lines must be preserved.
Do not manufacture support, interpret an import as review, or silently rebind
an existing Ship to a new Type. New capture uses the evidence-bearing Types;
an explicit policy check can report missing evidence on older content without
rewriting it. No bulk archive migration is included.
<!-- tarav.breadcrumb 2f89b44b15f0 -->

### Mechanical checks and future assessment

Implement a small set of atomic Situation Chains using the maintained Checks,
POI, Action and Project machinery. Mechanical cases include:

- required support absent or an empty support set;
- unresolved or drifted evidence references, distinguished from wrong roles;
- support/review targets disagreeing with the current Line/context state;
- required review absent;
- an invalid review protocol: wrong proposal/approval roles, missing explicit
  token approval, wrong ordering/session, or mismatched presented wording.

For this first verbatim path, allow only declared presentation whitespace
normalization when locating wording within the proposal. Do not equate
paraphrases, case changes or punctuation changes with a semantic review.
Present removals and before/after changes explicitly in the bounded review
payload. Token agreement alone cannot establish which content was reviewed.

Unavailable evidence yields a visible unresolved check result, never a pass
or a claim that the content is false. Store structurally valid incomplete
capture and report POIs afterward: validation does not block recording.
Malformed record shapes still fail at the schema boundary. Rechecking does
not mutate or bless evidence. A review-completion operation must not report
success when its protocol fails. Ordinary action closure never fabricates a
User approval; any blessing follows the declared Action Type's existing rules.

No Assertable implementation, semantic entailment evaluator, scoring provider,
AssessmentCase producer, score persistence, threshold policy, automatic
support carry, or semantic blessing mechanism is part of this request.
Mechanical checks cannot certify that the support justifies the Line. Records
must expose sufficient subject/evidence identity for that later work without
introducing a parallel scoring system now.
<!-- tarav.breadcrumb 3a3c0387df7a -->

## Inspected current implementation

- `src/tarav/l1/lines/__init__.py`: Line retains id, text and scope_ship.
  `block.py`: one ordered Line/Block contents collection and bounded ancestry.
- `src/tarav/l1/notebook/__init__.py`: standard Record Registry persistence,
  save/load by Ship, connected-context binding, explicit Git commit. Saving
  rejects Type rebinding of a stored Ship.
- `src/tarav/l1/notebook/blocks.py` and `l2/project/notebook.py`: shallow
  Project/Discussion/Model/Archive Types; initial explanatory Lines currently
  have no support fields. Opening a notebook never provisions or regenerates it.
- `src/tarav/l1/chatlas/references.py`: existing ChatlasTurnReference and
  ChatlasTurnLocator address an exact turn by session identity/address/hash;
  use these and the maintained Normal Model rather than new chat lookup code.
- `src/tarav/l1/references`: typed resolution, including mismatch and unavailable
  paths. Non-chat support must use an explicitly authorized typed source;
  supply the base extension point now and implement Chatlas first.
- `src/tarav/l1/checks/chains.py`, `l2/project/dev.py`: atomic chain naming and
  Project suite composition. `l1/assertions` and `l2/scoring/assertions.py`
  exist but Notebook support/review assessment integration is deferred.
- `src/tarav/l2/notebook.py`, `l3/notebook/commands.py`, `l3/runtime.py`:
  Context-based read/query and trusted Type composition must keep working.
  Register persistent new Types explicitly in the existing runtime registry.

Historical implementation was inspected, not executed: Git `4b95d7b^`
contains `src/tarav/index/gates.py` and `capture_manifest.py`; `0369b73^`
contains the later `src/tarav/diagram/__init__.py` and Diagram tests.
They implement distinct support, producer and review relationships, later
edition-targeted LineGateAnnotation records, and recomputed protocol checks.
The old ship-level any-historical-review aggregate must not be restored.
Attic deposit 16a34bf9-6f2e-4ef2-9536-56955c35b0e7 retains a real gate record
at annotations/9e7aeb90-610e-4c66-a268-fb4dc10f18b1.json. This is candidate
evidence; none of the old Model, Anchory or Chat.Index pipeline becomes active.

## Impl.Req.Wiki

Selected Wiki: `../tarav-md/notes/wiki/`.
Relevant Notes: `line-notebook.md`, `lines-workflow.md`, `lineage.md`.
Capture this accepted support/review split in the Notebook topic and the
2026-10-20 daily Note, with exact User-Turn Breadcrumbs. Keep implementation
proposals distinguished from accepted requirements. Design capture does not
create supported Notebook Lines or count as implementation of this request.

## Execution.Plan

Data shape first: small workflow roots; typed subject-state reference;
SupportSet/member; review evidence with token/proposal/approval/target;
Notebook capability composition; atomic check situations. Exact class/module
names are executor choices within these boundaries. Prefer general support
and review records with l2 Notebook/Chatlas integration; keep l1 primitives
free of runtime and Project imports. Use the existing Record system and
workflow partitions, not an extra bespoke database.

1. Feature — Define and register reusable retained evidence Types and Notebook
   specializations. Verify literal Record round trips in a fresh runtime,
   stable Ships, preserved mixed Block contents and existing Notebook reads.
2. Feature — Add Python capture/attachment and inspection operations for support.
   Capture from fixed User-turn fixtures, reload explicit references and the
   target state. Verify support absence/drift/wrong-role cases without making
   a semantic entailment claim. Old evidence survives a Line revision.
3. Feature — Add explicit verbatim review capture for one Line and a bounded
   Block/change set, including later review of existing content. Verify exact
   targets, token, roles, order, wording and independent support; verify edit
   and ancestor-context changes do not retain current-review standing.
4. Feature — Compose the small mechanical check suite into the Project notebook
   integration and normal action lifecycle. Verify supported/unreviewed and
   supported/review-required cases; missing evidence remains persistable;
   check→action→correct evidence→gone works; an unavailable source does not
   pass. Never reach a scoring provider. Confirm no existing capture/read
   operation implicitly provisions a Notebook or rewrites Archive records.
5. Verification/closure — Run focused Lines/Notebook/Chatlas-reference/checks
   tests, layer/import checks, then required Project checks. Capture touched
   product surfaces and update the Wiki through the invoked implementation
   workflow. No live Notebook migration or fabricated evidence for this chat.

Subtract before adding: reuse current references, Record storage, Context and
Situation Chains; do not revive retired Diagram Model/Gate infrastructure.
If an implementation requires LineTrace, general lineage reconstruction,
semantic scoring, or a new review policy decision, record the mismatch and
return for Interactive alignment rather than expanding this request.

## Impl.Log

- Design only. No product implementation, tests or Notebook data were changed.
- Current session resolved directly; exact session refreshed once for this
  capture pass. Supporting User Turns resolved through Chatlas Query/render.
- Worktree inspected clean in tarav-py and tarav-md before scoped checkpoints.
- Readiness review: current interfaces and owners inspected, data shapes and
  dependencies described, each slice has a public observable result and proof,
  semantic scoring/LineTrace boundaries explicit. Proposed state-coordinate
  details remain implementation choices within the accepted behavior.
- Request capture submitted 11 Breadcrumbs; complete request audit passed.
  Notebook Wiki topic gained five Breadcrumbs and daily/2026-10-20.md two;
  both complete Note audits passed. Scoped Wiki capture commit:
  ceab0bca33779c3100b99638b43743363048043e.
- Start checkpoints: Python d29b1681704828859247d5f277eee675490c68e4;
  Markdown bac44cdbd20eac0f8da5fe505269f19627529e45.
- Baseline umbrella status --all completed 1,212 checks, zero incomplete,
  68 existing POIs and zero newly opened actions. No existing findings were
  blessed or repaired by this design pass. Scoped diff whitespace checks pass.
- Ready for a later Execute invocation. Execution must cold-read this note
  and current guidance before product changes; this request does not execute
  its implementation plan.

### Execute pass

- Cold-read the complete request and inspected current interfaces. No material
  mismatch with the accepted design. Implementation uses independent Grounding
  and Review workflows, Notebook capability Types and exact retained state
  snapshots; no base Line or legacy Notebook data migration.
- Todo: retained Types; support capture; bounded review; mechanical chains and
  Project integration; full verification and Wiki closure. Work remains scoped
  to Python APIs, with semantic Assertions and scoring deferred.
- Slice 1: added registered SubjectState, SupportMember, SupportSet,
  VerbatimReview, NotebookLine/ReviewedLine and supported/reviewed Blocks.
  Two public round-trip/schema tests and focused Ruff passed. Notebook storage
  preserves identity and mixed membership with the specialized Line Types.
