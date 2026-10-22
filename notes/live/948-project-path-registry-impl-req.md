# Project Types, computed Views and maintained path identities

## Impl.Abstract

Status: complete. Knowledge.Surface: wiki. Alignment.Mode: Interactive.

Implement a Python-first PathRegistry for TaravObject Record and instance schema
Views. Projects enumerate their registered Types and own registry maintenance
through normal checks and Actions. Documentation and other identified objects
attach to path Ships. Git tracks registry history. No extension changes, filesystem
scanner, general lineage, automatic semantic rename detection or doc generation.

## Design

The User chose computed structure with a maintained path-to-Ship map. Attachments
target Ships, active entries declare paths, and changes are repaired by agents or
users, with normal Project Actions. Project Type enumeration is a separate
capability; reuse the existing dispatch registry rather than register classes twice.
<!-- tarav.breadcrumb 4a6bd4fe6818 -->

Data shape first:

- `TaravObject.view_schemas()` produces named JSON values by default: Record
  JSON Schema from RecordInterface, and a partial instance schema from constructor
  parameters, public class annotations and public properties. Inspect declarations
  without invoking descriptors, constructors or evaluating annotation strings.
  Types can override this method to provide exact/custom schemas.
- `Project.Types` / `project.types` is an overridable manager over
  `project.records.types.types()`. Default selection uses the defining class's
  source file under the Project root; it neither scans nor imports new modules.
  Classes with unavailable source are excluded; overrides can include them.
- `JSONView`: identified by owning Type Ship and view name, with computed JSON
  value. Paths are RFC 6901 pointers into that JSON value, including the root.
  For schema Views this means `/properties/id`, not the instance's `/id`.
- `PathEntry`: Ship, View Ship, active/retired state, declared path, attachment
  Ships. Identified objects remain owned by their own workflows; documentation
  may use `PathDocumentation`, a Line subtype in its ordinary authoring Block.
- `PathRegistry`: identified Project-owned object retaining accepted JSONViews
  and PathEntries in one normal typed JSON file at `.tarav/paths.json`. Reads of
  an absent registry return empty in-memory state without provisioning. Explicit
  enrollment creates entries/Ships for all paths; later computed changes never
  rewrite the map. Explicit reassignment preserves Ship and attachments, retirement
  keeps historical identity, and accepting a schema records the maintenance choice.
- `Project.Paths` / `project.paths` composes the workflow, storage and checks.
  No duplicate Type dispatch system or custom history service. A schema's changed
  value, missing/new paths, duplicate active assignments, undeclared active paths
  and missing View membership produce atomic typed findings. Unavailable View
  computation is incomplete, never evidence that old actions disappeared.

First enrollment is explicit and opt-in. Project checks do not create a registry
or require every runtime dependency to be documented. Once enrolled, registered
Views continue being checked. Declaration-only introspection cannot guarantee a
complete instance model; its output says partial and Type overrides refine it.
Subtract before adding: reuse managers, current Record dispatch, Lines and Action
lifecycles. No old API or data migration is needed for this new capability.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Read projects.md and
record-framework.md; capture the registry design in path-registry.md and link
the daily Note. Source and request Breadcrumbs use the exact current Chatlas
session, refreshed once for this pass. Preserve older evidence gaps separately.

## Execution.Plan

- [x] Feature: computed default Views and Project Type enumeration. Verify real
  Line/Block schemas, safe introspection, source ownership, manager overrides.
- [x] Feature: typed Views/entries/registry, explicit maintenance and Project
  checks/actions. Verify save/load, stable Ships and attachments through a rename,
  new/retired/duplicate paths, schema drift and action closure; checks are read-only.
- [x] Capture/verification: register public Types, update architecture/guidance,
  add source evidence, run focused and full Project checks, Wiki capture and
  evidence commits. Demonstrate on real Block/Line schema values in isolated data.

## Impl.Log

- Inspected TypeRegistry, Project Records/Checks/Actions managers, runtime
  registration, existing schema interfaces and Wiki. `project.records.types` is
  runtime-wide dispatch; no owned-Type enumeration exists. Live Record schema
  export works; Line class annotations are empty, while constructor/properties
  expose useful instance structure, hence explicitly partial defaults.
- The plan above is the task todo list; cold reload precedes execution.
- Cold reload completed. Start checkpoints: Python
  `1e5d1e3db6c99025444cd1455e61600cb8901c12`, Markdown
  `2bfa0656d99786751816238485d85d64fc6644da`.
- Implemented declaration-only schema production, source-based Project Type
  selection, explicit path maintenance and typed read-only checks. Registry
  enrollment remains opt-in. Path lookup exposes duplicate matches; View
  retirement retains retired identities and attachments.
- Focused code/architecture/Project/Record-contract run passed 79 tests. The
  first run exposed builders that needed explicit TypedState loading and a
  missing identity in the PathEntry record example; fixed both using existing
  Record patterns. Instance introspection correctly includes public scope_ship
  properties as well as scope; adjusted the test's incorrect exclusion.
- Live read-only probe computed default Views for all 389 currently selected
  TaravObject Types in tarav-py, with no errors. No live registry was enrolled.
  New kernel architecture test and final path lookup/retirement tests are
  included in final verification. Full Project status is running.
- Full Project run: 86 checks completed, none incomplete; all 66 pytest
  suites passed. POI render coverage flagged seven new Types without summary
  docstrings. Added their semantic summaries; follow-up status closed all seven
  Actions, leaving the existing Gitleaks finding and two synthetic test markers.
- Final behavior-only run passed 13 tests. Ruff passed. Source Breadcrumb audit
  resolved all 14 surfaces with no errors; its 77 informational POIs record
  updated source positions. Guidance source annotation was registered separately.
- Wiki capture added path-registry.md and linked projects.md and the daily Note
  for 2026-10-22. Markdown status completed 1,215 checks, with existing harness,
  Git, SKW and provisional-marker findings; capture submission ran afterward.
- Final focused run passed 76 tests across path behavior, architecture and kernel
  Record contracts. Final non-test Python status completed 20 checks and retained
  only the three existing findings. The prior all-suites run covered all 66 pytest
  suites; the final focused run also covers the additional retirement and
  architecture assertions introduced during that run.
- Product slice: `f2d8e87d3511b32cdb49898be9d61d2118594c3f`. Commit Breadcrumb
  audit passed. Wiki capture: `004c4c27eba4061c7a825821350b6b2eb6596ca1`.
  All three Wiki surfaces audited with zero POIs/errors. Final Markdown status
  completed 1,215 checks; remaining provisional markers are on other Wiki
  surfaces (including context-graph.md), not this capture. Existing harness/Git
  and SKW findings remain outside this request. No mixed external edits entered
  the product slice; start checkpoints retained the pre-existing work.
- Schema/identity demonstration uses real Line and Block computed Views in the
  tests, and the rename/save/load test uses isolated Project data with a real
  PathDocumentation Line. No live registry enrollment or extension change.
