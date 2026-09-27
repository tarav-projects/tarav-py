# Models

`ModelsWorkflow` owns `Model`, `ModelShipRecord`, and `ModelEditionRecord`.
Lines, Blocks, and Collections retain their own LinesWorkflow ownership.

```python
from tarav.project import Project

model = Project.from_path(path).models().main()
model = diagram.model(model_ship)  # No project required.
```

Project discovery and the `diagram.main_model` association belong to
`tarav.project.models.ProjectModels`, not Model. The integration loads the
existing configured storage lazily and never creates an association.
Several projects may point to the same Model. Models can exist without projects.

Named associations live in the project's `diagram.models` mapping:

```json
{"diagram": {"models": {"research": "<model-ship-id>"}}}
```

`project.models().ls()` lists names in sorted order without loading storage.
`project.models().get("research")` resolves the selected Model; absent names
raise KeyError. The existing `diagram.main_model` remains independent, so
`main()` does not require a named alias. Reads never modify the marker.

The existing Model handler remains a live namespace-bound handle, now a
TaravType with its class entity. Its retained Ship and edition Records are
TaravObjects. This move does not introduce another identity or change the
handler's existing projection and annotation APIs.

Python consumers now import `Model` from `tarav.models`, and Model Record types
from `tarav.models.records`. No old-path aliases are provided. Existing UUIDs,
record labels, and storage layouts remain unchanged. Retained class-entity
snapshots, if any, are historical metadata; this change does not rewrite them.
