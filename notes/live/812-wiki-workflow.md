# Wiki workflow implementation

## Scope

One WikiWorkflow owns folder-based Wiki and WikiNote mechanics and the existing
Hugentics Wiki capture instructions. Project integration supplies the default
root; a standalone Wiki does not require a Project. All Markdown parsing uses
tarav.surfaces.markdown.

## Execution

- [x] Add WikiWorkflow and register Wiki/WikiNote record types.
- [x] Implement lazy folder and project resolution, note listing, daily paths,
  reading, writing, and surface parsing.
- [x] Implement explicitly invoked Wiki-scoped Git commits.
- [x] Connect workflow help to the skill entrypoint and update its retained
  source and compiled capture instructions.
- [x] Verify containment, symlink escape rejection, native Markdown parsing,
  project lookup, record round-trips, runtime ownership, and scoped Git behavior.

34 focused tests passed; Ruff and diff whitespace checks passed. The skill
document compiled without findings. Existing unrelated working changes remain.

The current Project implementation is TaravProjectHandler. Wiki.from_project
accepts that handler or a path for existing upward project discovery. No new
Project ontology or Capture workflow was introduced.

## Capture status

The preceding Wiki capture preserves the User's organizational principle.
This implementation note is coordination; no implementation Collection or
Diagram Draft was created for this slice. Implementation capture remains
unreconciled and does not gate the requested product work.
