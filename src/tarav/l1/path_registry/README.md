# PathRegistry

A Project's maintained map from JSON positions to Ships. Computed structure and
maintained semantic identity are separate. Checks report drift; only explicit
maintenance assigns, moves or retires identities.
<!-- tarav.breadcrumb 03c002051ef7 -->

## Computed Views

Every TaravObject class provides `view_schemas()`:

```python
from tarav.l1.lines import Line

schemas = Line.view_schemas()
schemas["record"]     # JSON Schema exported from RecordInterface
schemas["instance"]   # partial declaration-only Python introspection
```

Instance defaults inspect constructor parameters, annotations and properties.
They never construct an object, invoke property getters or evaluate annotation
strings. They cannot discover every runtime attribute or infer exact instance
semantics. A Type can override `view_schemas()` and return named JSON values.

The Record projection includes a `type` position because Type dispatch is a
separate boundary from the payload's RecordInterface. JSON Schema references
remain references: paths index the actual finite JSON schema, not an infinitely
expanded recursive object graph.

## Project integration

`project.types.all()` selects registered TaravObject classes defined in source
files under the Project root. It does not import or scan source files. Override
`Project.Types.all()` or `.owns(cls)` for other membership rules. The dispatch
registry stays available as `project.records.types`; selection changes neither
registration nor what dependencies can load.

`project.paths.views()` computes the selected Types' Views. `project.paths.open()`
reads `.tarav/paths.json` or returns an empty in-memory registry. Neither read
creates storage. Enrollment is explicit and selects which Views to maintain:

```python
from tarav.l2.project import Project
from tarav.l1.lines import Line

project = Project.load_project(path="/path/to/tarav-py")
project.paths.enroll(Line, "record")  # once; fresh Ships for every JSON position
registry = project.paths.open()
view = next(v for v in registry.views if v.typed.owner == Line.class_entity().id)
entry, = registry.at(view.id, "/properties/text")
```

Paths are RFC 6901 JSON Pointers into the View's JSON value. The root is `""`;
literal `/` and `~` in keys become `~1` and `~0`. Array positions are literal
indices. A schema field is `/properties/text`; this is distinct from the
instance's `/text`. Moving array items changes the schema and requires maintainer
judgment too. No automatic field-rename or semantic continuity heuristic runs.

## Consumers and identity maintenance

The registry provides identified schemas and positions. Consumers own their
documentation, evidence and other associations to those Ships. The registry
stores no attachments and has no dependency on Lines. For example, a documentation
consumer can hold its own mapping keyed by a Path Ship:
<!-- tarav.breadcrumb 8dcb7ba7b400 -->

```python
from uuid import uuid4
from tarav.l0.kernel import Ship
from tarav.l1.lines import Block, Line

block = Block(id=Ship(uuid4()))
line = Line(id=Ship(uuid4()), text="The statement's wording.", scope=block)
block.append(line)
documentation = {entry.id: line}  # Illustrative consumer-owned data, not a registry API.
# The consumer chooses its own persistence and how to present this association.

# After a deliberate rename, keep the same Ship:
registry.declare(entry.id, "/properties/wording")
assert documentation[entry.id] is line  # The external association still names it.
# Add fresh positions explicitly, or retire an identity:
registry.add(entry.typed.view, "/properties/other")
registry.retire(entry.id)
```

`registry.accept(computed_view)` records the reviewed schema value without
changing any entries. Save explicitly. Commit `.tarav/paths.json` through the
Project's ordinary Git workflow to retain history. There is no parallel history
database and no automatic commit on a read or check.

Once enrolled, Project status composes an identified PathRegistry suite. Missing
paths, new unmapped paths, duplicate declarations, active entries lacking a path,
identity conflicts, missing Views and schema changes yield typed findings and
normal Project Actions. An unavailable scan is incomplete; it does not close old
actions. Removing a registry does not certify that its old findings disappeared.
Schema drift can exist while capture and other work continue.

`registry.retire_view(view.id)` ends maintenance of a removed Type/View, keeping
its Path Ships as retired entries. Consumers decide what retirement means for
their own associations. `registry.at(view.id, path)`
returns all active matches; duplicates are visible rather than resolved arbitrarily.
