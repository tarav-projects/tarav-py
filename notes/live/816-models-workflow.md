# Models workflow organization

Scope: move the existing Model handler and Model Ship/edition Record types to
tarav.models, owned by ModelsWorkflow. Preserve identities and project links.
Project entity integration is a separate task.

- [x] Extract Model types and update Python consumers without aliases.
- [x] Register ModelsWorkflow; keep Lines ownership for Lines/Blocks/Collections.
- [x] Add read-only Model.from_project(path, diagram=resolver).
- [x] Run regression checks: 1,329 tests passed; Ruff and diff whitespace checks
  passed. Editable CLI refreshed and Diagram help verified.

The handler remains a live namespace-bound TaravType, not a second retained
Model entity. Existing Model Records carry the persisted representation.

Implementation capture remains unreconciled; this coordination note is not
a supported Diagram capture. No retained user data was migrated or rewritten.
