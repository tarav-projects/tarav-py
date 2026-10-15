# 911 — Callable Context namespace and partial Type models

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Status: implemented and verified; durable Breadcrumb registration pending.
Replace the ordinary object
`context()` method with a bound namespace available on both Types and objects.
Preserve `obj.context(type=ObjectGroup)` as shorthand for
`obj.context.explore(type=ObjectGroup)`, and expose `SomeType.context.model`.
<!-- tarav.context 473c89a0:8cf85c979321cdcf -->

Include initial Type-model primitives, class declarations, external providers,
and a default retained location using existing Context storage. This does not
implement instance models, an external-annotation workflow, or automatic code
path checking.

## Knowledge.Surface

Backend: Project Wiki in `../tarav-md/notes/wiki/`. Read the existing Context and
namespace narratives before implementation; update the relevant topical note
and today's daily note after verification.

## Design

Context follows the existing namespace design: a stateless bound NamespaceBase,
an explicitly selected capitalized namespace class, ordinary Python inheritance
and `super()`, and rejection of dropped independent namespace contributions.
Callable namespaces are allowed here but are not imposed on NamespaceBase.
`__call__` delegates dynamically to `explore`, the single exploration override.
<!-- tarav.context 473c89a0:52d399e8d65f61fc -->

Every Type already has its Type Ship, the root of a potentially empty partial
Diagram model. Additional model nodes are identified objects. A node's Ship is
its identity; its current Type-relative path is a lookup label. Paths do not
become the nodes. Nodes have their own existing Context, allowing documentation,
annotations and supporting conversations to accumulate independently of code.
<!-- tarav.context 473c89a0:7ef12f9536d4a790 -->

Both the class and outside workflows can contribute nodes without requiring a
complete model of every Python member. Scope is Types, not instance fields.
Declared code correspondences may be checked later; absence of a model node is
valid and reading a model must not mint identities or create storage.
<!-- tarav.context 473c89a0:3fea6e90a968360c -->
<!-- tarav.context 473c89a0:0dfbeaeb402e0305 -->

The model belongs inside the Context namespace and workflow. Its nodes expose
their own Context using existing identified-subject storage.
<!-- tarav.context 473c89a0:568b173e6f7d5c24 -->

Implementation choices (agent decisions): place the namespace on TaravType so
class-only capabilities can use it too; object `.context.model` views its Type's
model. Introduce a typed `TypePath` entity and a read-only `TypeModel` folder.
Namespace `model_nodes()` supplies class contributions; runtime-specific Context
services supply external contributions and retain nodes in a subject's `model`
folder keyed by Ship. Multiple Ships may use the same path; unique path lookup
reports ambiguity. The node itself need not repeat its owning Type: membership
is provided by the model, allowing explicit reuse across Type models.

## Impl.Req.Wiki

Capture the callable-namespace contract, Type-only model, Ship identity versus
path label, partial-model validity, and external contribution/storage APIs.
Distinguish these implementation choices from user decisions above.

## Execution.Plan

1. Namespace slice (feature/refactor): bind Context on Type/object, preserve callable views,
   dynamic exploration overrides and explicit composition. Check existing
   Context tests plus new inheritance/composition tests. Status: verified.
2. Model slice (feature): typed path nodes, root-only model, lazy providers and
   explicit retained writes; expose model through Context exploration. Check
   Record round trips, no-write reads, external/class/storage composition,
   renamed labels retaining node Context and runtime isolation. Status: verified.
3. Integration slice (documentation): architecture, full tests and Project
   validation, product capture and Wiki capture. Status: verified product and
   captured Wiki text; Breadcrumb submission/audit pending as logged below.

## Impl.Log

- Baseline: 20 tests passed across object namespaces, Kernel Context and Context
  CLI tests. Worktree clean before editing. Start checkpoint: `3e6c570`.
- Evidence limitation: main Chatlas capture and commit evidence registration
  cannot write to `~/Documents/tarav/` under this sandbox. Exact current session
  was captured to `/tmp/tarav-context-chatlas` for faithful User-Turn resolution.
  Provisional markers and this session declaration preserve the read-only trace;
  durable registration remains pending. Following the skill's recovery rule,
  commits use plain Git when evidence registration fails.
- Namespace slice: 23 focused tests pass. The first selected-view test used an
  object unsupported by ObjectGroup; corrected the fixture to a supported POI.
  Product capture ran for Kernel Records and the namespace tests; both remain
  pending because the main data depot is read-only. Model host hook is declared
  here and will be wired in the next slice.
- Namespace slice commit: `bda47c4`; plain Git recovery, evidence registration
  pending. Namespace composition validation now lives on TaravType, covering
  class-only Types as well as Objects.
- Model slice: 75 focused/integration tests pass; configured suite: 312 pass.
  Ruff over all `src` and `tests` passes. The first storage test assumed Archive
  could overwrite a placement; inspection confirmed its existing create-only
  policy. Kept that policy, tested duplicate writes explicitly, and verified
  path renaming through a provider while retaining the node's Context by Ship.
- Data shape first: TypePath is the identified member, TypeModel the computed
  view. Subtract before adding: deleted the ordinary object context method;
  shorthand now delegates to the namespace operation. Boundary discipline:
  Kernel has host hooks only; Context mechanics stay in l1, retention in l2 and
  host selection in l3. No new mutable global model-provider registry.
- Product capture attempted separately on models, storage, runtime, model
  tests, architecture tests and architecture documentation. All submissions
  remain pending due the protected Breadcrumb store. Batch audit reports the
  pending markers and existing attachment/position concerns; it is not clean.
  TOML has no supported embedding convention, so pyproject test registration
  carries no invented marker. Exact session is declared above for recovery.
- Broader discovery (`pytest -q tests`): 461 pass, one unrelated failure in
  `test_scoped_lines::test_models_fail_before_side_effects`. It expects the old
  ToImplementError from ProjectModels(None), whose current constructor raises
  TypeError. Reproduced exactly against pre-change commit `4f4bf3d` in a
  temporary source extraction. No unrelated repair was made.
- `tarav status --project --all` completed 312 checks and reported 15 open
  actions across the root and child Projects. It warned that global Project
  index and usage retention could not write under this sandbox; those warnings
  did not stop the checks. An earlier commentary incorrectly called the run
  blocked after reading its warnings; corrected after inspecting the full
  result. The read-only `tarav check --project --json` also completed, reporting
  POIs rather than a clean Project. Existing POIs were not repaired.
  Editable reinstall was attempted as directed;
  uv itself panicked in macOS system-configuration before installing anything.
  The existing installed tool is editable and loads these source changes.
- Model/integration slice commit: `20a981b`.
- Wiki start checkpoint: `53434bd`; capture commit: `821fe48`. Daily destination:
  `../tarav-md/notes/wiki/daily/2026-10-15.md`; topical destination:
  `../tarav-md/notes/wiki/context-graph.md`. Both parse through WikiNote.parse.
  Separate Breadcrumb submission was attempted on each and failed with the
  protected store's PermissionError. Audit is not clean: the new markers are
  unsubmitted; older sessions' attachment/position concerns remain unresolved
  when auditing through the temporary single-session Chatlas depot.
- All commits used the skill's plain-Git recovery path after evidence
  registration failed. No fabricated Breadcrumb IDs or evidence envelopes were
  committed. Provisional surface markers and exact session declarations remain
  intact. A later session with data-depot access can refresh this exact Chatlas
  session, submit each supported surface, and rerun the batch Breadcrumb audit.
  Product behavior is complete; registration is the outstanding capture task.
