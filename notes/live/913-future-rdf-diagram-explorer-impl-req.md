# Experimental RDF Diagram explorer

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Status: implementation verified; visual UI moved to Tarav Center (extension
request 012); VS Code visual review and durable capture pending. Alignment.Mode:
Autonomous. Knowledge.Surface: wiki.

Build an explicitly selected `_future` experiment: typed Python objects expose
an in-memory RDF graph, SPARQL selects Context views, and a local visual
explorer uses the same backend as Python callers. `_FutureWorkflow` owns the
experimental Types and their ordinary JSON Records. Keep existing Context,
runtime assembly, identities and storage consumers intact.
<!-- tarav.context 473c89a0:b4ad4b3730008174 -->
<!-- tarav.context 473c89a0:8944495a171e5499 -->

Scope includes identified model members, represented predicates and particular
relationships, a small synthetic Conversation/UserTurn/Annotation family,
normal Record Registry retention, progressive graph loading, typed view
selection, direct SPARQL and a browser UI accepting a root identifier.
The UI is a local experiment, not a new deployed Center application.
General ontology inference, production workflow migration, global completeness,
disk RDF indexing, and a general annotation/documentation schema are outside
this implementation. These boundaries are agent implementation choices.

## Design narrative

The user selected RDF as the shared graph representation and SPARQL as the
query language. Identifiable nodes, predicates and particular relationships
have TaravObject representations. Python classes participate through their
existing TaravClass entities; partial class models identify selected members.
Opaque Ships survive changes to current code paths when semantic continuity
is intended. The established pipeline is Record → Object → RDF, reusing the
same contribution path for loaded and runtime-only objects.
<!-- tarav.context 473c89a0:a25dc4a4402725c7 -->
<!-- tarav.context 473c89a0:26ed8f97ba0dba97 -->

The explorer owns one progressively growing graph. View refinement changes a
query; loading context adds triples. Following another object retains the
shared graph and history. Re-evaluating an unchanged query after expansion
may yield a different result. Providers explicitly expose finite contributions
and available loading steps; RDF does not discover Python objects itself.
<!-- tarav.context 473c89a0:2231281cb94571ae -->
<!-- tarav.context 473c89a0:2a9c92e92b99b1e7 -->

Agent choices: use an optional RDFLib dependency; plain Python providers;
explicit in-memory identity resolution; built-in out/in/type/model views;
parameterized predicate and literal filters composed as SPARQL patterns;
ordinary RDF reification for inspectable relationship occurrences; explicit
expansion entries; one local HTTP process with a self-contained SVG UI.
Experimental objects expose `._future.context()`, and a `future(obj)` wrapper
adapts existing objects without modifying Kernel.

Current mechanics inspected: `l0/kernel/records.py` provides class projections,
Records and bound Context namespaces; `l1/context/models.py` provides TypePath;
`l1/records/registry.py` provides Workflow-partitioned RecordMap storage.
`tests/test_architecture.py` enforces layer direction and import isolation.
No obsolete product path is removed: isolation is the requested migration
strategy, not an opportunity for a Context rewrite.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md, `notes/wiki/`.
Relevant context: `context-graph.md`, `record-framework.md`, and the scoped
`rdf-diagram-experiment.md` capture. Supporting current-session turns were
resolved through Chatlas Query; exact session retained above. Breadcrumb
registration is pending because the durable data directory is sandbox-protected.

## Execution.Plan

Data shape first: `_FutureWorkflow`; experimental Type/object namespace;
Member and vocabulary resources; Relation occurrences; Diagram object map and
RDF graph; typed query requests, entries and explorer history; synthetic
Conversation/UserTurn/Annotation Records; explicit demo host and UI adapter.

- [x] Slice 1 — feature: isolated Types and ordinary JSON retention. Prove
  class ownership, namespace binding, Pydantic validation and RecordMap reload.
- [x] Slice 2 — feature: RDF contributions, direct SPARQL, typed views and
  progressive loading. Prove live/stored parity, representation resolution,
  cumulative filtering, growth, incoming edges and history against RDFLib.
- [x] Slice 3 — feature: browser explorer over the same session. Prove root-ID
  opening, query/view dispatch, expansion, inspection and navigation through
  the HTTP adapter; inspect the rendered UI where browser tooling is available.
- [x] Slice 4 — documentation and integration: runnable tutorial, architecture
  isolation checks, focused regressions and project verification; capture and
  commit the outcome.

Sequence: reusable Types before RDF engine, then demo integration and UI.
Use no alternative SPARQL interpreter or invented query language. A dependency
or environment failure is reported as unverified, never replaced by mocks
that claim query correctness. Each completed slice requires a green relevant
check; independent code may proceed while environment checks remain pending.

## Impl.Log

- 2026-10-15 correction: the user requested the visual explorer inside the
  existing Tarav Center extension. The HTTP server was an unnecessary agent
  choice. Superseding the standalone browser slice: move its consumer adapter
  to `vscode-tarav-center/scripts`, keep Python state through stdin/stdout,
  and delete the l3 HTTP package and HTTP-specific tests. The extension's
  request 012 owns its workflow/UI; l1/l2 RDF mechanics stay reusable.
  <!-- tarav.context 473c89a0:944a943d7daaf1ba -->
- Correction checkpoints: `4f0fd8b` (tarav-py), `e899443` (tarav-md) and
  `5d2e25c` (extension), ordinary fallback after evidence-depot denial.
  Deleted l3 `_future` HTTP package and six HTTP tests; updated the README,
  architecture narrative and obsolete server-existence assertion. No graph,
  query, Record or runtime assembly code changed.
- Corrected verification: core maintained pytest 353 passed in 71.42 seconds;
  Ruff passed. `tarav status --project tarav-py --all --json` completed all 52
  checks, including 40 pytest suites, with no incomplete/not-run checks and
  zero test POIs. Exit 1 represents the same two existing MarkerPOI actions;
  no actions were opened, reopened, updated or closed. Existing protected
  usage/index writes emitted warnings. The extension's 12 tests include its
  actual persistent `tarav run` worker and rendering adapter; 0.1.3 packages.
- Per-surface correction capture attempted on the remaining changed core
  sources/docs. Durable registration is still denied; supported provisional
  markers and exact Chatlas session remain intact. Pending visual verification
  is now a VS Code window check; no listening server remains to verify.

- 2026-10-15: start checkpoints `65b60c6` (tarav-py) and `51bf436` (tarav-md).
  Evidence commit registration failed on the protected Breadcrumb store;
  ordinary empty Git checkpoints created under the skill's fallback rule.
- Exact native session resolved and refreshed once into
  `/tmp/tarav-future-chatlas`; neutral identity is declared above. Selected
  user turns resolved using Chatlas Query, including the current authorization.
- Environment: RDFLib absent; uv install panics in macOS system-configuration;
  direct PyPI download fails DNS in this sandbox. Asked asynchronously for
  dependency installation while proceeding with independent work.
- Slice 1 measured: `uv run --offline --no-sync pytest -q
  tests/future/test_records.py`: 4 passed. Ruff on the new modules/tests passed.
  Existing TypePath semantics are reused; the new Member adds an owning
  TypeShip. Constructors and JSON loading produce the same operational state.
- Slice 1 committed as `5142b07`; per-surface submission/audit ran. Files with
  justified markers retain them because durable registration is denied;
  package initializers and the initial test file had no justified marker.
- User installed RDFLib 7.6.0 into tarav-py's `.venv`; actual query verification
  is now available. No substitute query engine was implemented.
- Slice 2 measured: 15 experimental tests pass, including normal Record reload,
  direct SPARQL, cumulative filters, unchanged-view results after graph growth,
  incoming links, relationship and predicate resolution, and retained history.
  RDFLib's Literal inherits str; a failing query test exposed and fixed
  accidental conversion of RDF terms to resource IRIs at the resolver boundary.
- Local TCP bind is denied by this sandbox. HTTP verification will feed actual
  HTTP requests through the handler in-process; browser/server launch remains
  a separate host-environment check if this restriction persists.
- Slice 2 committed as `9d1124c`; supported code/test surfaces submitted and
  audited. Durable Breadcrumb registration remains denied; provisional markers
  retain the exact session and user turns. TOML has no capture convention.
- Slice 3 measured: 19 experimental tests pass. Actual HTTP request bytes go
  through BaseHTTPRequestHandler into the same Application/ContextExplorer;
  queries return 2 stored turns, then 3 after the runtime-only expansion.
  Tests cover predicate/occurrence inspection, history and invalid requests.
  The actual served HTML's JavaScript passes `node --check`. This does not
  claim a browser rendering review or a successful TCP server launch.
- Optional dependency lock entries were reconstructed from inspected PyPI
  release metadata (RDFLib 7.6.0 and pyparsing 3.3.3) after uv lock's native
  configuration panic. `uv export --frozen --extra future --no-dev` succeeds;
  the existing dependency versions are preserved.
- Slice 3 committed as `f7d64aa`; code/test capture submitted and audited.
  HTML/JavaScript has no supported inline capture convention in this skill;
  no native markers were invented in that surface.
- Slice 4 measured: 23 experimental tests pass. Graph merge preserves Ships,
  reconciles runtime resources by their actual objects, and is idempotent.
  The merge test exposed differing graph-local blank-node labels in occurrence
  Records; occurrence identity checks now compare endpoint identities in the
  receiving graph. Runtime provider/view registration stays local host policy.
- Full maintained `uv run --offline --no-sync pytest -q`: 359 passed in 74.28s.
  An earlier run had one new architecture assertion matching Python's
  `__future__` import; the check was corrected to match the actual experimental
  module namespace. The full rerun passed. `ruff check src tests
  examples/future_diagram.py` and `git diff --check` passed.
- `tarav check --project tarav-py --all --json`: 53 completed checks, no
  incomplete/not-run checks, 41 completed pytest suites without test POIs.
  Two existing `Tarav.Test.Actions.MarkerPOI` signals remain. Routine status
  completed with those same two open actions and no action changes; its slow
  tests were explicitly left out, covered by the separate all-check run.
  Machine-local Project-index and usage-log writes emitted permission warnings.
- The real `tarav run -- examples/future_diagram.py` surface succeeded: one
  stored Alice message became two after runtime expansion; the active SPARQL
  remained qualified. The module's real `--help` route also succeeded.
- Added a README with browser/Python commands and a runnable disposable example.
  The UI displays active query bindings and limits result rendering explicitly.
  Optional RDF tests are skipped clearly when the `future` extra is absent;
  namespace/JSON/import-isolation tests still run. The experiment imports no
  higher layer and normal runtime composition does not register its Types.
- Required editable-tool reinstall was attempted; uv hit the same native
  configuration panic. The already editable command successfully loaded and
  ran the new module/example, so source dispatch is verified.
- Remaining limits: TCP binding is denied in this sandbox and no browser tool
  is exposed, so visual rendering and an actual listening server are unverified.
  The complete HTTP wire-to-application path and JavaScript syntax are tested.
  Durable Breadcrumb registration remains pending in the protected data depot;
  provisional markers plus the exact Chatlas declaration retain recovery paths.
- This first experiment is additive and scoped. It does not implement global
  completeness, arbitrary query-composition inference, mutable-source refresh,
  RDF persistence, a production annotation schema or production workflow migration.
- Final review reproduced an uncaught FileNotFoundError for a valid but unknown
  pasted root ID through the actual HTTP handler. Added a 404 boundary response
  and a regression test proving the current focus is preserved. The focused
  experiment suite and the complete maintained suite then passed.
- Final per-surface capture covered supported code, tests, documentation and
  both Wiki destinations. The 14-file audit completed with 200 POIs: 45 pending
  markers, 82 labels without matching position observations, and 73 invalid
  attachment resolutions (the selected temporary Chatlas depot contains only
  this exact session). This is a scoped inventory including older material,
  not a claim that all findings were introduced here. ARCHITECTURE position
  refresh was attempted and denied by the protected Breadcrumb store. TOML,
  lock files and HTML have no supported native capture convention.
