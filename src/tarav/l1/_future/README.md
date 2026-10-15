# Experimental RDF Diagram

This is an opt-in `_FutureWorkflow` experiment. It reuses Tarav's existing
objects, Ships, class projections, JSON Records, Pydantic interfaces and Record
Registry. Importing the normal runtime does not import this engine or register
its Types. Importing the `_future` package alone does not import RDFLib.
<!-- tarav.context 473c89a0:b4ad4b3730008174 -->

## Run the visual explorer

From `tarav-py`:

```bash
uv run --extra future tarav run -- -m tarav.l3._future --seed-demo
```

Open `http://127.0.0.1:8737`. The synthetic conversation's root ID is:

```text
776cd033-b741-4bc2-8207-193ca827d9f2
```

`--seed-demo` creates only missing synthetic Records through the normal Record
Registry in `_FutureWorkflow`'s partition. It never rewrites an existing Record.
Use `--records-root /tmp/tarav-future-demo` for a disposable Registry root.
Use `--root ID` to select another retained object in that partition, or paste
an ID in the UI. The live session also resolves loaded class, member, predicate,
relationship and runtime object identifiers. This is one local explorer session.
<!-- tarav.context 473c89a0:8944495a171e5499 -->

If dependencies are already installed and a package-manager refresh is
undesirable, use `uv run --no-sync tarav run -- ...` instead.

Choose `messages`, then `by-alice`. Initially there is one result. Load the
runtime-only turn: the same selection now has two. Load the external annotation,
follow its target message and choose `in` to discover the annotation link.
Click nodes to inspect their Records and code grounding. Relationship labels
open their predicate objects; arrows open particular relationship objects.
The SPARQL editor runs read queries over the same accumulated graph.
It displays the current query bindings as well as the query text.

## Python uses the same engine

```python
from pathlib import Path
from tarav.l2._future.demo import Demo

demo = Demo(Path('/tmp/tarav-future-demo')).seed()
explorer = demo.open().select('messages').select('by-alice')
view = explorer.view
view.ls()
explorer.expand('runtime-turn')
view.ls()  # Re-evaluates the same query against the larger graph.
print(view.sparql)
```

`examples/future_diagram.py` is a runnable, disposable version:

```bash
uv run --extra future tarav run -- examples/future_diagram.py
```

For existing objects, `future(obj).context(diagram=diagram)` explicitly adapts
them. Experimental Types also expose `obj._future.context(diagram=diagram)`.
The namespace follows NamespaceBase's stateless binding and explicit
multiple-inheritance composition. The returned explorer owns navigation state.

## Contributions and views

Providers register per Diagram with `register(Type, provider)`. A provider
receives `(obj, diagram)` and contributes finite relationships with
`diagram.relate(subject, predicate, target)`. Predicates are represented objects.
`diagram.offer(subject, key, label, load)` advertises a loading operation;
listing never invokes that loader. Literal targets have RDFValue representations.

The default graph describes object Types through their existing TaravClass
identities. Expanding a class adds its Python base relationships and declared
partial model nodes. `register_model(Type, nodes)` supplies external members.
Model Ships are identities; code paths are labels. No path is evaluated.

Built-in views are `out`, `in`, `type`, and `model`. `Along(predicate)` selects
targets through one relationship; `Where(predicate, value)` adds a condition on
those targets. Registered named requests appear when compatible. Requests
compose SPARQL patterns and preserve prior bindings and qualifications.
Opening a view and passing the equivalent typed request use the same refinement.
`ContextViewEntry` distinguishes available view steps from result entries.

Views share a Diagram. Following changes focus; back/forward change history;
loaded triples remain. `Diagram.merge(other)` imports another exploration's
loaded graph and object representations, preserving Ships and reconciling
runtime nodes by Python object identity. Local provider and view registrations
remain host policy. Queries never implicitly load more data. Their coverage is
the current graph. RDFLib evaluates SPARQL; this package defines no alternative
query language or inference engine. Dataset-loading clauses and remote SERVICE
queries are rejected because exploration is confined to the loaded graph.
<!-- tarav.context 473c89a0:2231281cb94571ae -->
<!-- tarav.context 473c89a0:2a9c92e92b99b1e7 -->

The synthetic Annotation Type is test data, not the production external
annotation or documentation workflow. Relation occurrences are graph-local
computed objects. Ordinary RDF reification makes them inspectable without
requiring RDF-star support. This prototype is additive: source mutations and
Record reloads that disagree on the same identity report conflicts; it does not
implement a general refresh/deletion or edition reconciliation policy.

`view.sparql` and `view.bindings` together describe the selection. Pass both to
`diagram.query(view.sparql, bindings=view.bindings)` when evaluating it directly.

## Verification

```bash
uv run --extra future pytest -q tests/future
```

The suite tests normal JSON retention and reload, actual SPARQL execution,
composed views, graph growth and merging, relationship inspection, history,
import isolation, and real HTTP parsing/serialization against the shared backend.
The HTML's JavaScript is syntax checked when Node is installed. Browser rendering
and actual local-server launch are separate checks; the implementation session's
sandbox prohibited TCP binding and exposed no browser automation tool.
