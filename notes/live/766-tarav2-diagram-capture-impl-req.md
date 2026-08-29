# Tarav2 Diagram Capture - impl-req

## Impl.Abstract

status: Complete

Implement the first narrow `Tarav.Diagram` vertical slice inside the isolated
`tarav.tarav2` namespace. The slice captures and reloads primary Line
Annotations and support-only Annotations whose `Support.Set` members are rooted
in one Chatlas User Turn and retain a selected neighboring set of User or Agent
turns.

Out of scope: Assertion scoring, Model HEAD computation, cross-model
composition, lineage forks, and storage optimization.

## Impl.Index

- [DC] Diagram capture stores one semantic Annotation mutation with explicit
  Model, Block, and Line ship placement; it does not create a general edge
  vocabulary.
- [DC] A `Support.Set` is a set of rooted members: the root is a Chatlas User
  Turn and the neighborhood contains selected companion Chatlas turns needed to
  interpret that touch.
- [DC] A later touch adds a support-only Annotation instead of rewriting the
  producing context or support of an older Annotation.
- [DC] Mechanical findings are reported as POIs and do not block applying a
  structurally representable capture.
- [DC] An Annotation Record loads as a generic `DiagramAnnotation`; explicit
  `specialize()` dispatches its retained `type` to a registered class or raises
  an ordinary error.
- [DC] Type-specific parsing and Assertions belong to specialized Annotation
  classes rather than the generic Record object.

## Execution.Plan

### Vertical.Slice::Capture

status: Complete

1. Add immutable Diagram value objects for Chatlas Turn references, rooted
   support members, locations, and the two initial Annotation types.
2. Add a Git-backed Diagram store and `Capture.Manifest` parser/check/apply
   path. Identity collisions may not rebind an existing Annotation.
3. Add `tarav tarav2 diagram` commands for manifest templates, checking,
   applying, and Annotation inspection with optional support rendering.
4. Add focused unit and CLI tests covering primary capture, later support,
   non-blocking findings, stable storage, and rendered neighborhoods.
5. Run focused tests, Ruff, architecture tests, and reinstall the editable CLI.

Acceptance: an Agent can author one JSON manifest, land a Line Annotation,
land later support on the same Line ship, reload both records, and render the
selected Chatlas neighborhoods in causal order.

### Vertical.Slice::Annotation.Type.Specialization

status: Complete

1. Keep `Diagram.annotation()` and collection reads generic.
2. Add strict `DiagramAnnotation.specialize()` dispatch from the retained
   Annotation type.
3. Add `LineAnnotation` and `LineSupportAnnotation` as the first typed behavior
   classes, with Line-specific Assertions owned by those classes.
4. Verify successful specialization, generic access to unknown types, strict
   unknown-type failure, and malformed typed-data failure.

Acceptance: a consumer may load every structurally valid Annotation as generic
data and explicitly request its registered typed behavior; specialization
either returns the correct class or raises an ordinary exception.

### Vertical.Slice::Namespace.Rooted.Diagram

status: Complete

1. Replace the single Diagram repository with independently created and
   Git-tracked `Diagram.Namespace` repositories.
2. Keep each Namespace physically flat: `namespace.json` plus the
   UUID-addressed `annotations/` tape. Models, Blocks, and Lines are
   projections, not storage directories.
3. Reduce the universal `Diagram.Annotation` contract to identity plus `type`;
   Namespace and specialized classes own support policy, Assertions, parsing,
   and other semantics.
4. Make a Model a root Annotation. A Capture.Manifest names one Model, and the
   Model resolves the only Namespace repository that capture may mutate.
5. Add a machine-local Namespace load path and default selection, plus
   Namespace create, mount, and list commands.
6. Bootstrap a project's main Model into `.tarav/project.json` when capture
   first targets that project.
7. Permit several Projects to point at the same existing Model; the Project
   marker is an association and does not imply ownership or copy Model data.

Acceptance: two Namespace repositories remain independent; a project capture
resolves its Model and writes only to that Model's Namespace; unsupported or
low-confidence semantic states remain writable and surface POIs.

### Vertical.Slice::Approval.Gated.Capture

status: Complete

1. Keep semantic proposal, revision, and approval in chat; create no Manifest
   before explicit `::land`.
2. Add read-only Model inspection and Capture.Context commands returning the
   shared target Model and manifest-ready Chatlas Turn references.
3. Restore support-neighborhood resolution and producer-context inclusion
   checks.
4. Surface missing Assertion scores and unavailable Chatlas-to-Archive
   grounding as non-blocking POIs.
5. Create and advertise the fresh `tarav-pkg --capture` operating module.

### Vertical.Slice::Verbatim.Gate.Review

status: Complete

1. Parse `Verbatim.Gate` instance data from both newly captured Line
   Annotations and gate-only Annotations targeting immutable existing Lines.
2. Resolve exact Agent proposal and User approval Chatlas Turn references and
   mechanically assess roles, shared opaque token, event order, and materially
   equivalent Line wording.
3. Derive Line-ship `Reviewed` standing only when at least one exact wording
   Annotation has a passing Gate; retain failures and unassessable evidence as
   POIs.
4. Keep review orchestration out of the CLI. An Agent compiles one ordinary
   `Capture.Manifest` containing an independently assessable typed Annotation
   per existing Line wording; the Annotation specialization owns Gate parsing,
   Assertions, and findings.
5. Project gate-only Annotations through Line, Block, Model, and named Renderer
   surfaces without modifying their targets.

Acceptance: an Agent can present an existing rendered Block with one opaque
token, resolve the later User approval from Chatlas, land a review Manifest,
and mechanically verify every Line ship as reviewed while the original Line
records remain unchanged.

## Impl.Log

- The mandatory execution-workflow Git checkpoint was not created because the
  project Git policy requires a separate explicit commit instruction. Existing
  uncommitted Chatlas changes are preserved and excluded from this slice.
- The existing IndexLab support model was inspected as historical evidence but
  is not imported; this slice uses the newly settled Turn-rooted model.
- The implemented capture path writes immutable UUID-addressed Annotation
  Records into the target Model's Namespace Git repository. Reapplying
  identical identity is a no-op; conflicting identity reuse is rejected because
  a stable reference may not rebind.
- Verification completed with the Tarav2 suite, architecture suite, focused
  Chatlas reference tests, Ruff, editable CLI reinstall, and installed CLI help
  smoke tests.
- Annotation type specialization remains an explicit library operation. The
  generic loader does not silently specialize or choose error recovery for its
  consumer.
- Gate review is a new Annotation layer rather than a mutation of previously
  captured wording. Gate standing is recomputed from retained Chatlas evidence;
  no authoritative passed flag is stored.
- `Capture.Manifest` has no Gate-specific behavior. It transports typed
  Annotation records, applies generic batch checks, and delegates type meaning
  and checks to Tarav's registered Annotation classes.
