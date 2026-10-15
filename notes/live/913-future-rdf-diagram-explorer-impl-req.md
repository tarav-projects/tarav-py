# Experimental RDF Diagram explorer

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Status: ready for execution; dependency verification pending. Alignment.Mode:
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
- [ ] Slice 4 — documentation and integration: runnable tutorial, architecture
  isolation checks, focused regressions and project verification; capture and
  commit the outcome.

Sequence: reusable Types before RDF engine, then demo integration and UI.
Use no alternative SPARQL interpreter or invented query language. A dependency
or environment failure is reported as unverified, never replaced by mocks
that claim query correctness. Each completed slice requires a green relevant
check; independent code may proceed while environment checks remain pending.

## Impl.Log

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
- Todo: execute the remaining slices and replace this status with measured results.
