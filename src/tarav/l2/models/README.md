# Models

The Models backend is currently disconnected. `project.models.ls()` reads the
Project marker, while `get()` and `main()` retain their intended paths and
raise until Model resolution is restored.
<!-- tarav.breadcrumb ba10a290f359 -->

`ModelsWorkflow` owns `Model`, `ModelShipRecord`, and `ModelEditionRecord`.
Lines, Blocks, and Collections retain their own LinesWorkflow ownership.

Intended resolution calls once the backend reconnects:

```python
from tarav.l2.project import Project

model = Project.from_path(path).models.main()
model = diagram.model(model_ship)  # No project required.
```

Project discovery and the `diagram.main_model` association belong to
`tarav.l2.project.models.ProjectModels`, not Model. When connected, the
integration will load configured storage lazily without creating an association.
Several projects may point to the same Model. Models can exist without projects.

Named associations live in the `diagram` section of the project's
`.tarav/config.json`, as its `models` mapping:

```json
{"diagram": {"models": {"research": "<model-ship-id>"}}}
```

`project.models.ls()` lists names in sorted order without loading storage.
`project.models.get("research")` will resolve the selected Model; absent names
raise KeyError. The existing `diagram.main_model` remains independent, so
`main()` does not require a named alias. Reads never modify the config.

The existing Model handler remains a live namespace-bound handle, now a
TaravType with its class entity. Its retained Ship and edition Records are
TaravObjects. This move does not introduce another identity or change the
handler's existing projection and annotation APIs.

Python consumers now import `Model` from `tarav.models`, and Model Record types
from `tarav.models.records`. No old-path aliases are provided. Existing UUIDs,
record labels, and storage layouts remain unchanged. Retained class-entity
snapshots, if any, are historical metadata; this change does not rewrite them.
