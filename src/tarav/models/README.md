# Models

`ModelsWorkflow` owns `Model`, `ModelShipRecord`, and `ModelEditionRecord`.
Lines, Blocks, and Collections retain their own LinesWorkflow ownership.

```python
from tarav.models import Model, ModelsWorkflow

model = Model.from_project(path, diagram=diagram)
model = diagram.model(model_ship)  # No project required.
```

`from_project` discovers the nearest project from a root, file, or subdirectory.
It reads the existing `diagram.main_model` association and never creates one.
The resolver is explicit so Models does not depend on legacy storage adapters.
Several projects may point to the same Model. Models can exist without projects.

The existing Model handler remains a live namespace-bound handle, now a
TaravType with its class entity. Its retained Ship and edition Records are
TaravObjects. This move does not introduce another identity or change the
handler's existing projection and annotation APIs.

Python consumers now import `Model` from `tarav.models`, and Model Record types
from `tarav.models.records`. No old-path aliases are provided. Existing UUIDs,
record labels, and storage layouts remain unchanged. Retained class-entity
snapshots, if any, are historical metadata; this change does not rewrite them.
