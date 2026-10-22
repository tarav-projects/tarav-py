# Path Notebook

PathNotebook is a typed child inside an existing Project Notebook. Its notes
describe registered schemas and paths of that Project's Types. Registry data
continues identifying those schemas/positions; Notebook owns the note links and
Lines. There is no independent database.
<!-- tarav.breadcrumb b8e8e33fcb68 -->
<!-- tarav.breadcrumb eae82dc9bf55 -->

```python
from uuid import uuid4
from tarav.l0.kernel import Ship, entity
from tarav.l1.lines import Line
from tarav.l2.project import Project

project = Project.load_project(path="/path/to/tarav-py")
book = project.paths.notebook()  # Same as project.notebook().paths; no writes.
book = book.create()            # Explicitly adds it inside the existing notebook.
# If needed, enroll the Type's View through project.paths.enroll(Line, "record").
registry = project.paths.open()
view, = [v for v in registry.views if v.typed.owner == entity(Line).id and v.typed.name == "record"]
schema = book.add_schema(registry, view.id)
target, = registry.at(view.id, "/properties/text")
leaf = book.add_path(registry, target.id)
schema.append(Line(id=Ship(uuid4()), text="These notes concern the Line record.", scope=schema))
leaf.append(Line(id=Ship(uuid4()), text="This field carries the statement's wording.", scope=leaf))
book.save()
```

Add operations change the loaded Notebook in memory; save persists it. Normal
Notebook capture/support/review operations can target these Blocks and retain
their existing policies. Plain Lines above impose no additional support policy.
An empty notebook child does not enroll Types or generate documentation.

`add_path` adds only the registered ancestors needed for that path: schema Block,
empty root-path Block, then each exact JSON Pointer prefix. For `/a~1b/~0/0`,
the chain is `""`, `/a~1b`, `/a~1b/~0`, `/a~1b/~0/0`. Escaped slash characters
do not create extra ancestors. Every parent position must have one active
registered Path Ship. Missing or ambiguous ancestry requires registry maintenance.

Each Line is interpreted with its own Block and all parent Blocks, including
the schema and Project context. Child Blocks do not supply context to parent
Lines. SchemaBlocks contain Lines/PathBlocks; PathBlocks contain Lines/PathBlocks;
the PathNotebook contains Lines/SchemaBlocks.

Read existing notes with `book.schema(registry, schema_ship)` or
`book.path(registry, path_ship)`. `book.label(registry, path_ship)` returns the
current pointer as a Label without writing a duplicate title Line. Ordinary
storage load remains available for historical inspection.

A same-parent rename retains the note's Ship and text. A move to another parent
causes current-path access to report an ancestry mismatch. Readers never silently
change authoring context; a maintainer explicitly edits that Notebook structure,
preserving Block Ships and resolving Line scopes, then saves. Retired or removed
paths never delete notes automatically. There is no automatic reconciliation
service or new lineage model here.
