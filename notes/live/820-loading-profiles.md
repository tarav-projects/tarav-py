# Loading profiles

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Develop. Alignment.Mode: Interactive.
Status: first implementation verified; subsequent semantic clarification
captured below. Implementation alignment with that clarification remains pending.

Introduce LoadingWorkflow and an opt-in LoadingProfile interface for caller-
selected Record discovery configuration. Types may implement it; ordinary
TaravObjects acquire no new obligation. Keep trusted Record Type dispatch and
exact expected_type checks independent from profile selection.

## Impl.Req.Wiki

Product: tarav-py. Documentation owner: tarav-md/notes/wiki.
Relevant context: projects.md and record-framework.md.
Evidence session: codex:01a0d86c-9538-7be1-af96-014cd4203d61,
identity 6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.
User Turns: 95f56e70ae55f654 (configurable discovery), 67a0d0ae4b9028a4
(general mechanics and named arguments), 7f09fe1c3ef4eb9f (opt-in interface).
Related decisions: 382f7e21e4fadbca (typed Project records, ambiguous labels).
Capture destinations: loading.md and daily/2026-09-27.md.

## Inspected implementation

- kernel/records.py: entry_file uses __tarav.json, main.json, type.json in
  order. _load_record selects, reads, resolves, exact-checks, constructs,
  and attaches source. Directory input additionally requires DirectoryRecord.
- kernel/types.py: TypeRegistry.load delegates to that loader. Registration
  currently rejects duplicate labels as well as duplicate Ships.
- runtime.py and tarav/__init__.py expose load_object with exact expected_type.
- project/base.py: from_path walks upward and explicitly constructs cls,
  reprojecting a retained Type tag. This is not dynamic Record dispatch.
- kernel/environment.py: trusted lazy external bindings are keyed by name;
  bind_type replaces a binding. Ship lookup does not discover arbitrary code.

## Proposed interface

    from tarav.loading import load
    load(path=path, profile=TaravProject)
    load(path=path, profile=TaravProject, expected_type=ConcreteProject)

One optional positional subject (path); all configuration keyword-only.
Existing load_object entrypoints remain maintained, delegate to the same
implementation, and accept profile. This is one engine, not parallel loaders.

LoadingProfile is a small abstract classmethod contract, proposed name
loading_paths(), returning an ordered tuple of relative entry paths. It is
owned by LoadingWorkflow and may be mixed into a TaravType or implemented by
a standalone configuration class. It need not itself inherit TaravObject.
The exact method name is an implementation proposal, not a user mandate.

The first profile controls only entry selection. It neither chooses the
concrete Type nor imposes an implicit family/subtype constraint. expected_type
continues to require exact identity of the resolved Python class.

## Selection semantics

### Clarification after implementation review

The user clarified that `load(path=path, profile=TaravProject)` is a general
Record-loading operation. `path` is the location of the Record being loaded,
not a project-root argument. LoadingProfile is an interface owned by
LoadingWorkflow; TaravProject hooks into it as a configuration provider.
The loading process applies that configuration using Record-loading semantics.
It has no knowledge of Projects, project roots, or the meaning of `.tarav`.

Project discovery and interpretation of a loaded Record's location belong to
Project code. The project root is the parent of its `.tarav` metadata folder;
its Record is `.tarav/project.json`. Neither convention becomes special logic
in the generic loader. `Project.from_path()` remains a distinct discovery API.

This supersedes the earlier explanation that the loader supports three
Project-specific entry modes (project root, metadata folder, and marker file),
and the inference that finding `project.json` establishes a new project layout.
A configuration may supply relative candidate paths, but those are interpreted
by the general loading contract, not as Project discovery modes. The exact
Project profile candidate list needs review against this distinction; this
clarification does not prescribe a replacement list or change product code.

The generic selection rules below remain independent of Project conventions.

- No profile: preserve existing default entry ordering and DirectoryRecord
  behavior exactly.
- Explicit file: read that file; do not search sibling candidates.
- Directory plus profile: use the profile's complete ordered candidate list,
  rather than merging defaults implicitly. A profile may explicitly include
  the default paths to extend them. First present entry wins.
- A selected malformed, unreadable, directory-valued, or dangling entry
  raises its error. Never skip it to try a lower-priority Record.
- Paths must be nonempty relative paths without parent traversal. Preserve
  existing symlink behavior; do not introduce a new filesystem sandbox here.
- No ancestor traversal or recursive discovery in this loader.
- Explicit profile selection treats the directory as a search location for
  a Record, not as an assertion that its Type is DirectoryRecord. Therefore
  the existing default DirectoryRecord guard applies only without a profile.
  This deliberate distinction needs documentation and regression tests.
- Dispatch reads the selected Record's Type through the trusted registry;
  profile selection never rewrites its Type or executes code from its folder.
- Attach the actual selected file as source after successful construction.

The first implementation configured TaravProject with
(.tarav/project.json, project.json) and broadened its root inference to two
layouts. Those implementation facts are not the clarified contract and need
alignment review. Dynamic loading still preserves the Record-declared class;
it does not select the profile provider as the concrete Type.

## Execution.Plan

1. Add tarav.loading with LoadingWorkflow, LoadingProfile, and the public load
   facade. Public load uses the current runtime. Profile selection yields an
   ordered path tuple at the runtime boundary; Kernel never imports the
   workflow or runtime.
2. Keep one generic loading engine in Kernel. Extend its entry selection with
   optional candidate paths, and route TypeRegistry.load, runtime.load_object,
   public load_object, and public load through it. Preserve existing entry_file
   consumers and default behavior. Kernel validates candidate path safety and
   selected-file behavior; it never imports project domains.
3. Register LoadingWorkflow; declare ontology identity for any new TaravTypes.
   Mix the opt-in profile into TaravProject without adding it to TaravObject.
   Keep Project location interpretation outside generic loading. Review the
   first implementation's two-layout root inference against the clarification.
4. Add tests using explicitly typed temporary Project markers. Verify profile
   independence, selection order, errors, no side effects, trusted dispatch,
   source attachment, and expected_type exactness. Run focused loader,
   environment, Project, Archive, Context, and architecture suites, then full
   tests and lint. Refresh installed CLI if public entrypoint behavior changes.
5. Update architectural/API documentation and selectively capture results.

## Follow-up slices, not silently bundled

- Type-label ambiguity: allow distinct registered classes to share labels,
  error on label-only resolution, resolve uniquely by Ship. Duplicate Ship
  identities remain errors. Must also design external environment bindings:
  name-keyed replacement cannot represent multiple lazy candidates. Do not
  solve only the in-memory registry and claim the whole system supports it.
- Project marker migration: explicit bounded inventory, dry-run report and
  backed-up writes for selected projects. Add the existing Project Type to
  untyped markers; preserve IDs and unrelated fields. Existing typed markers
  retain their Type. New initialization should emit that same declaration.
  This design does not authorize scanning/migrating every machine project.
- ProjectProjects integration: named relative references resolved dynamically
  through the Project profile, validating TaravProject membership explicitly
  in the integration. No upward fallback at a missing child. Keep containment
  separate from inheritance and workflow ownership; no recursive tree engine.

## Acceptance checks

- A non-Project test Type implements LoadingProfile successfully.
- An ordinary TaravObject requires no profile method.
- Profile methods cannot bypass registry trust or exact expected_type checks.
- Profile paths are interpreted by the same generic rules for Project and
  non-Project providers, with no special Project entry modes or ancestor search.
- Project discovery and root interpretation are tested separately from loading;
  loading a candidate does not itself establish another supported Project layout.
- Custom Project Type is instantiated through its registered Record identity.
- Default directory loading retains its existing DirectoryRecord checks.
- Different candidates obey explicit precedence; selected bad data fails.
- Discovery/read operations never create, migrate, or repair files.

## Impl.Log

The implementation results below describe the first implementation, before the
subsequent user clarification. Passing tests do not establish alignment with
the revised semantic boundary. This update changes the note only.

Profile selection remains independent of Type dispatch and expected_type.
The Kernel retains one loader engine; the Loading workflow supplies optional
entry paths through the runtime. Default loading retains its DirectoryRecord
guard. TaravProject supplies both marker paths and computes its root from
either layout. No retained-data migration was performed.

The pre-execution product checkpoint was cfaddda. The implementation added
LoadingWorkflow, LoadingProfile, tarav.loading.load, profile arguments on
load_object, and focused behavioral and architecture tests. A Context test
exposed an existing wrapper around TypeRegistry.load; unprofiled runtime calls
retain the old call shape. Full pytest: 1,358 passed. Ruff: clean. Existing
typed Project markers were tested with temporary files; untyped markers still
need the separate authorized migration slice.
Wiki capture updated loading.md and daily/2026-09-27.md with exact User-Turn
Breadcrumbs; both audits passed after shifted older positions were observed.
Wiki-only closure: b67dc3c.
