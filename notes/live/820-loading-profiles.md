# Loading profiles

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Design. Alignment.Mode: Interactive.
Status: ready for review; no product implementation authorized by this phase.

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

TaravProject opts in with (.tarav/project.json, project.json). These describe
project-root and metadata-folder loading. The existing from_path upward search
remains separate and unchanged in this slice; dynamic load preserves the
Record-declared class instead of selecting cls.

## Execution.Plan

1. Add tarav.loading with LoadingWorkflow, LoadingProfile, bounded entry
   selection, and one engine accepting an explicit trusted registry internally.
   Public load uses the current runtime. Keep kernel imports acyclic: isolate
   profile/selection foundations from runtime convenience composition, and
   update architecture tests at module granularity if necessary.
2. Move loader orchestration out of Kernel into the loading foundation and
   route TypeRegistry.load, runtime.load_object, and public load_object through
   it. Preserve existing callers and default behavior; inspect entry_file and
   private loader consumers before relocating helpers. Kernel must not import
   runtime or project domains.
3. Register LoadingWorkflow; declare ontology identity for any new TaravTypes.
   Mix the opt-in profile into TaravProject without adding it to TaravObject.
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
- Project root, .tarav folder, and explicit project.json resolve the same typed
  Project; a missing marker never selects the parent project.
- Custom Project Type is instantiated through its registered Record identity.
- Default directory loading retains its existing DirectoryRecord checks.
- Different candidates obey explicit precedence; selected bad data fails.
- Discovery/read operations never create, migrate, or repair files.

## Impl.Log

Design only. Profile argument does not claim family filtering. Proposed
profile-directory semantics resolve a real incompatibility with today's
DirectoryRecord guard without reclassifying all Project objects as directories.
No product edits, product checkpoint, or retained-data migration performed.
Wiki capture completed in loading.md and daily/2026-09-27.md. Both
Breadcrumb audits passed; shifted older daily-note positions were explicitly
observed without changing their attachments. Wiki-only closure completed.
