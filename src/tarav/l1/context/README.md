# Object contexts

Construction has one public entry point:

```python
cxt = document.context.build(options={"include_title": True})
triplets = cxt.triplets
```

The result is an `ObjectContext`, a TaravObject holding the subject, mutable
triplets, options, opaque contributor `hints`, execution `runs`, and status.
Hooks receive that same object, in this order:

1. `subject.context._class_context_hook(cxt)` — the class contribution.
2. `subject.context._obj_context_hook(cxt)` — the instance contribution.
3. External hooks registered on the runtime, in insertion order.

The inherited class hook adds the subject's type triple. The inherited
instance hook is empty. Override hooks in the Type's nested `Context`, call
`super()` to compose them, then mutate the context. A hook may remove or
replace earlier triplets, modify options for later stages, and add other
data under hints. Build options are copied at the outer mapping; hooks
share the resulting options, including any nested values.

For multiple inheritance, explicitly compose the namespace classes as usual:
`class Context(Left.Context, Right.Context)`. The builder calls each stage
entry point once; Python's cooperative MRO runs the super chain.

## Classes use their representing object

`Document.context.build()` and `entity(Document).context.build()` both
build the class identity. With an ordinary TaravClass identity, that means
TaravClass's class hook, the identity object's instance hook, then external
hooks. Document's hooks describe Document instances and do not run here.
There is no separate `.context.triplets()` method.

## External contributors

```python
from tarav.l3.runtime import get_runtime

runtime = get_runtime()
runtime.contexts.register("my-workflow", contribute_context)
# contribute_context(cxt) inspects the subject and mutates this build's result.
runtime.contexts.unregister("my-workflow")
```

The registry belongs to this runtime, not the singleton ContextWorkflow.
Names must be unique. The builder snapshots registrations before any hook
runs; registering or removing a hook affects subsequent builds. A workflow
decides which subjects its hook handles and which data it loads.

Hook failures raise `ContextBuildError`; `error.context` retains the failed
result, including the run's error and preceding changes. The original
exception is available as `error.cause` and the chained cause. Stage runs
include elapsed seconds and triple counts before/after, not a detailed
diff or a trace of every superclass implementation.

## Explore a built context

```python
from tarav.l1.context import ContextExplorer

explorer = ContextExplorer(cxt)
assert explorer.contexts[explorer.node(cxt.subject)] is cxt
```

`document.context()` remains the existing Explorer entry point; the runtime
builds its initial context. Opening or following another object builds it
once and retains its result. For a standalone custom builder, pass
`build=builder.build` to the Explorer so later opens use that same builder.

The RDF graph is a snapshot of contributions collected so far. Removing
triplets before collection changes that contribution; changing a result
after collection does not retract facts. A failed hook or invalid triple
does not partially publish an object's contribution or mark it opened.

An ObjectContext is itself contextualizable: `cxt.context()` describes
that result object. To explore the subject represented by an already-built
result, pass it to `ContextExplorer(cxt)` instead.

The [complete example](../../../../examples/object_context.py) exercises the
real public entry points, external registration, retained results and SPARQL:

```sh
tarav run -- examples/object_context.py
```
