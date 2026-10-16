# 914 — Graph Context model: `triplets()` and one growing Explorer

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: designed; ready for execution.

Migrate all of Tarav's Context to one model. Every object answers
`obj.context.triplets()` with the triples it contributes about itself; by
default one, `(obj, rdf:type, its class)`. `obj.context()` returns a
`ContextExplorer`, a TaravObject holding an RDF graph that only grows, the
set of opened objects, a focus and its history. It lists the edges at the
focus, opens objects (by object or identifier), follows edges (moving the
focus and opening the target), runs SPARQL over what is open, and goes back
and forward. The old Context system and every Type's Context contribution
are deleted, not ported: they stay in Git history and are reimplemented
later, one by one, as they are needed. Using a removed feature (a named
Context view such as `object-group`) is an explicit error.

Non-goals: reimplementing any Type's contribution beyond the default;
labels; named views; offers; merging explorations; a relationship object per
edge; a persistent graph; changes to the extension, the skills or other
repositories (they follow separately).
<!-- tarav.breadcrumb cc2b83a7f8e258417ad7faf4557e7846ad895cb5ddba8c49eef9dc4387ca13e0 -->
<!-- tarav.breadcrumb 5ba37585494ea9f25fd4d9029bb4ee9f4ba48dcd8cd7ce7ae44ed0d2cd640417 -->

## Design narrative

The User's first principles (Wiki, "First principles: code produces the
graph" and "The projection contract"): code is the center and produces the
RDF graph; graph technology extracts semantics; Tarav defines only how code
connects to the Diagram. All code for the code → graph step belongs to the
Context workflow; everything objects must implement goes in the `.context`
namespace. `triplets()` means "what I contribute about myself", nothing
more, and whatever an object returns is its contribution. Navigation,
search and opening by identifier are ordinary Tarav code.
<!-- tarav.breadcrumb 85f0723e9d4dcdaad322a254cea3003ab758acff242f451f54374982008c5eba -->
<!-- tarav.breadcrumb e68db1933d20c300d7aebc2e0c04834e258e3e9ba3f0a5ab68f25973405269e8 -->

User decisions for this usage case: an object's context returns a navigable
object that holds the opened graph, can be expanded and queried, and grows
by asking each visited object for its triplets. The default triplets are
VERY basic: one type triple. The Explorer is a TaravObject, which only
means it answers when asked for its context. History (back/forward) is in;
it moves the cursor, and the graph only grows. All of Tarav migrates: every
Type resets to the default and its context is rebuilt later as used.
ObjectGroup is just a query now; using it errors. `tarav context --id`
finds the object and returns `.context()`. Context code in Actions and
elsewhere is cut.
<!-- tarav.breadcrumb 17c3e24d99631f69830d8b68c9d240d2a201f023864eda192e4401c982e1246a -->
<!-- tarav.breadcrumb bc574679fb38bd6989008b113f3dbc13e83ae42310e702184519a0e8e91aff33 -->
<!-- tarav.breadcrumb ccbc58147add58df00114484dce4547fd12f3672fd9437bbc62d26ba52b3a039 -->

Current behavior (inspected 2026-10-16, baseline `uv run pytest` 353
passed): Kernel `TaravType.Context` (`l0/kernel/records.py`) exposes
`explore(views=)`, `model`, `model_nodes()`; `class_context(builder)` and
`obj_context(builder)` are population hooks overridden in Actions, POIs,
Checks, Lines, Archive, Settings, Breadcrumb audits, scoring and the test
fixtures. `tarav.l1.context` holds views, builder, entries, scopes, the
explorer, Type models (`models.py`) and ObjectGroup links (`groups.py`,
fed by `run_links`, `poi_links`, `poi_run_links`, `situation_links`,
`check_links`). `tarav.l2.context.storage.ContextService` retains Context
entries in an Archive partition and registers views; the runtime wires it
(`l3/runtime.py`). `tarav.l1.context.query` resolves identifiers through
search engines (`TypeResolver`, `ActionResolver`) and then opens views and
paths. `tarav.l1._future` (request 913) is the RDF experiment; the
extension's Diagram explorer imports it.

Agent implementation decisions:

- Triples are Python tuples `(subject, predicate, target)`: subject a
  TaravType instance or class, predicate an IRI string, target a TaravType
  instance or class, or a str/int/float/bool literal. Kernel exports
  `RDF_TYPE`. A class subject stands for its `entity(cls)`. This keeps RDFLib
  out of Kernel; the Explorer converts at its boundary and rejects anything
  else with a TypeError.
- Identity: a TaravEntity (TaravClass included) is `urn:uuid:<id>`; another
  object is a blank node kept for the Explorer's life. The Explorer keeps
  term → object for everything it has seen, so every node it lists resolves
  back to its object.
- Opening by identifier uses Tarav's existing resolver service
  (`ContextQueryService`, search engines), stripped of views and paths. The
  runtime composes it and configures Kernel's `.context()` opener.
- `ls()` returns `ContextEdge(direction, predicate, node)` for outgoing and
  incoming triples at the focus among those collected. `follow()` takes an
  edge or its index. `query()` supports SELECT (rows of objects or literal
  values) and ASK (bool), and never opens anything.
- `tarav context --id <id> [--json]` prints the focus and its edges;
  `--view` remains only to fail with an explicit not-reimplemented error;
  `--path` is removed.
- RDFLib becomes a core dependency; the `future` extra goes.
- The `_future` experiment is deleted: one Context model, one Explorer.
  The Records its demo seeded in the User's records root are left untouched
  and reported.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`.
Relevant notes: `rdf-diagram-experiment.md` (sections "First principles:
code produces the graph", "The projection contract"), `context-graph.md`.
Supporting session: abd0372d above. Capture status: pending until completion.

## Execution.Plan

Core data shape: `Triple = tuple[TaravType | type, str, TaravType | type |
str | int | float | bool]`; `ContextExplorer(TaravObject)` with `graph`
(rdflib Graph), `objects` (term → object), `opened` (terms), `history`
(focus terms) and `position`; `ContextEdge(direction, predicate, node)`.

1. Refactor (subtract): delete `tarav.l1._future`, `l2/_future`,
   `tests/future`, `examples/future_diagram.py`, the `future` extra and test
   path. Check: `uv run pytest` green (minus the removed tests).
2. Feature + subtract (replace, one coherent slice, since the old and new
   hooks cannot coexist without a shim): Kernel Context namespace becomes
   `triplets()` plus `__call__`; new `tarav.l1.context` engine; delete views,
   builder, entries, models, groups, storage, every `class_context` /
   `obj_context` override and link helper, runtime wiring; resolver service
   without views; `tarav context` on the new Explorer; RDFLib core
   dependency. Check: new tests through `obj.context()` and the CLI
   (default triple, follow to the class and its fixed point, open by
   identifier, query SELECT/ASK, back/forward, graph only grows, `--view`
   error); full suite green; `uv tool install --reinstall --editable .`;
   `tarav context --id Tarav.POI` and an action id print through the real CLI.
3. Documentation: AGENTS.md, ARCHITECTURE.md and the Context README match
   the new contract. Check: `rg` finds no reference to removed APIs in
   maintained docs; Ruff clean; `tarav status --project --all`.

Risks and deviation triggers: an unmaintained test or module outside the
curated test paths importing a deleted symbol (delete the deleted behavior's
tests, fix imports); a consumer needing a removed feature at import time
(make it fail explicitly where used, not at import).

## Impl.Log

Start checkpoint: `c607b84`. Baseline: `uv run pytest` 353 passed.

### Slice 1 — delete the `_future` experiment (refactor, done)

Deleted `src/tarav/l1/_future`, `src/tarav/l2/_future`, `tests/future`,
`examples/future_diagram.py`, the `future` extra and its test path, the
ARCHITECTURE "Opt-in RDF experiment" section, and the architecture test
guarding the experiment. `uv lock` dropped RDFLib (it returns as a core
dependency in slice 2). Check: `uv run pytest` 335 passed after removing
that guard test (the 18 experiment tests are gone); Ruff clean. Inlined
capture: deletions only, no remaining position to annotate.
