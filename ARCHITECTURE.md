# Tarav Python Architecture

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
64298cbc = claude-code:9da4cef5-68b7-4d17-8a06-1351ca51e82f @64298cbc8db2e7aa971e0828653c07bcb483cfed40931fdf87d5abe7ce1c60b3
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

`tarav-py` is Tarav's maintained Python distribution. It is one modular
monolith: the Python library is the primary interface, and the CLI and daemon
adapt that library for particular operating environments.

This document explains the system shape, semantic boundaries, and dependency
rules that code alone does not make obvious. Python classes and their
`RecordInterface`s define exact behavior and schemas; CLI help defines commands;
tests enforce the mechanical boundaries.

## System model

Tarav is an executable ontology. Its foundational unit is `TaravObject`: an
object whose Python class supplies executable meaning and whose Record supplies
a lightweight, inspectable representation. Persistence is optional, and a
Record does not need to contain every fact known by its class.

An object's own state is its source of truth, never its loaded Record. Every
construction path, whether a constructor, a factory, or `_from_record`, fills
that state; objects may be partial, because a Record need not hold every fact
(a location in particular), and a missing part fails where it is used.
`_record` keeps what was read and is not consulted as state; `to_record()`
projects state. The kernel's `_to_record()` fallback to `_record` remains only
for Types not yet migrated, which `tests/kernel/test_object_record_contract.py`
lists and lets only shrink.
<!-- tarav.breadcrumb 020e9873510e3a8944267702ca20fa60fa8410e5e51dfe4082c233e7e8d9e789 -->

The main concepts are:

- **Artifacts** are parts of the world Tarav may operate on: files, code,
  repositories, chats, external systems, and Tarav data itself.
- **References** address objects or Artifacts. Their locator determines how a
  target is found; References may also point within Tarav.
- **Records** are lightweight JSON representations understood by Tarav.
- **Types** are registered Python classes that assign executable meaning to
  Records and runtime objects.
- **Objects** couple a Type's behavior with a Record representation.
- **Entities** are Objects with a stable, non-rebindable Ship identity.
- **Workflows** are identified bundles of functionality, comparable to
  applications. They may overlap and may operate on both Records and native
  Artifacts.
- **The Diagram** is the graph that emerges from Objects, Types, Ships,
  References, and workflow-defined relationships. It is not limited to the
  `tarav.diagram` package or one physical store.
- **Context** is the graph of triples objects contribute about themselves,
  explored from a Type or Object.

A subject participates in the Diagram when Tarav can represent it as a
`TaravObject`. Python classes participate through `TaravClass`, Workflows are
singleton `TaravWorkflow` entities with independently represented implementation classes,
and the `TARAV` Entity represents the system itself.

## Bootstrap path

Tarav provides a small opinionated bootstrap so agents can discover the system
without first selecting another discovery workflow:

```text
TARAV
  └── Workflow entity          addressed by established WorkflowShip
        └── Type               identified by TypeShip
              └── Object      represented by a Record
                    └── Entity, when needed, identified by Ship
```

Every `TaravType` defines a class-local `class_entity()` hook that directly
constructs the `TaravClass` representing it. The public `entity(SomeType)`
operation validates that projection. Type identity, name, Python location, and
owning Workflow are data on that `TaravClass`, rather than parallel attributes
on the Python class. `TypeWorkflow` owns `TaravClass`, while its instances'
`workflow` fields continue to describe the represented classes' owners.
`TaravClass.bases()` derives direct Tarav base entities from Python declaration
order, omitting non-Tarav mixins. Detached class Records cannot infer live
bases or targets.
`KernelWorkflow` owns the remaining foundational Types; each concrete
Workflow entity retains its established WorkflowShip address. Each concrete
Workflow declares that fixed identity independently through `_workflow_id()`;
`WorkflowClass()` returns the same process-wide entity on repeated calls.
`entity(WorkflowClass)` represents only the implementation class, retaining its
separate TypeShip. Its `workflow` field declares ownership, not instance identity.
Classes and their objects therefore have separate identities. Both UUIDs
remain unchanged; existing Archive partitions do not move. Workflow Records
can be projected and explicitly loaded through their class, but Workflow Types
are not automatically registered for dynamic Record loading.

`TaravWorkflow()` is the umbrella workflow with its own fixed Ship and no parent
(`workflow is None`). Other workflows default to that root; Record Archive is
contained by Archive. Workflow nesting is explicit, not inferred from Python
inheritance. The workflow object's `workflow` returns its parent instance.
Class entities' `workflow` returns the containing workflow instance, while
`workflow_ship` exposes the stored address. Ordinary Objects inherit ownership
from their class; Archive partitions resolve their declared owning workflow.
Library composition supplies lazy resolution through the current runtime's
registry, so Kernel does not import runtime or domain packages. Unknown owners
raise on resolution; class Records can still be read and inspected by Ship.
Stored class and partition Records retain UUID strings without migration.

The registries keep mechanics separate from semantics:

- `TypeRegistry` maps retained Type references to trusted Python classes.
- The runtime's `TaravEnvironment` holds mutable external Type bindings: a
  Type name maps to a class object or an importable `package.module:Class`
  path in the running Python environment. The registry imports path-backed
  classes only when needed and verifies their declarations and Workflow owner.
  The sibling `tarav-extension-py` package exercises this boundary from its
  own installed environment.
- `WorkflowRegistry` maps Workflow name or established Ship to a Workflow class.
- The Type itself declares Type-to-Workflow ownership; the registries do not
  maintain a second reverse relationship.
- Each Workflow class declares its code-owned text constitution alongside its
  name; the constitution remains code-owned rather than a retained instance field.
- Runtime-local state lives in `ReferenceService`,
  `BreadcrumbService`, and `RecordsService`, not Workflow instances or mutable
  Workflow class attributes. Separate runtimes receive separate service objects.
- Runtime composition verifies that every registered Type's Workflow Ship
  resolves to a registered Workflow.

Every TaravType has the `.context` namespace. `subject.context.build()`
returns an `ObjectContext`; its `triplets` list holds triples `(subject,
predicate IRI, target)`, the target a Tarav object, class or str/int/float/bool
literal. Class access delegates to the representing object:
`SomeType.context.build()` builds `entity(SomeType)` through TaravClass's
namespace, not the hooks for SomeType instances.

One result passes through `_class_context_hook(cxt)`, then
`_obj_context_hook(cxt)`, then registered external hooks. Both namespace
hooks compose through ordinary `super()` and explicit NamespaceBase multiple
inheritance. The default class hook adds the type triple; the instance hook
is empty. `build()` owns orchestration; Types override contribution hooks.
There is no `.context.triplets()` shortcut. Kernel delegates construction
and `.context()` exploration through host callbacks, importing neither
Context nor RDFLib.

`tarav.l1.context.ContextBuilder` owns each runtime's ordered external
registry (`runtime.contexts.register(name, hook)` / `unregister(name)`). All
hooks share the mutable result, including its options and opaque hints.
Registrations are snapshotted before construction; changes take effect on
the next build. `ObjectContext.runs` records stage entry points, elapsed
time, triple counts and errors; it does not trace individual super calls.
`ContextBuildError` retains the failed partial context and cause. Results
are runtime data, with no persistence contract.
<!-- tarav.breadcrumb d2fc001a48cd5061c68999356e70273bc19428e950af073ad0a3b2052123c46f -->

`tarav.l1.context.ContextExplorer` is a TaravObject holding an RDFLib graph
collected from the objects it opened, the object behind every term, a focus
and its history. Its constructor takes a completed ObjectContext. `open()`
builds an object's context once and retains it in `contexts`, keyed by graph
node; an identifier
resolves through the runtime's resolvers (`TaravRuntime.context_queries()`).
`ls()` lists the edges at the focus among the triples collected, `follow()`
moves the focus along an edge and opens its target, `back()` and `forward()`
move the focus, and `query()` runs SELECT or ASK over what is open without
opening anything. The graph only grows. Entities, classes included, are
`urn:uuid:<Ship>`; other objects are blank nodes for the Explorer's life.
Navigation, search and resolution are ordinary Context workflow code; objects
only contribute. Invalid or failed contributions are not partially published;
an unsuccessful open may be retried. Later mutation of a retained result
does not retract collected facts. Contributions are added Type by Type as
they are needed. See `src/tarav/l1/context/README.md` and the runnable
`examples/object_context.py`.
<!-- tarav.breadcrumb f4ee4baa75c2ef6c6f63210c2e4267b40246449d077c7e81a03f38dc82a491e2 -->
<!-- tarav.breadcrumb 31740a0af8080b6fcd08005c5dddb9e71ac81187cb544723c254a6000b8f51e6 -->
<!-- tarav.breadcrumb 786354609782dd54b9d97050a7218a3b244f3ff621a473a69035a5838f1176f2 -->

`tarav.l3.loading.load(path, expected_type=...)` is the primary dynamic loading
interface. The composed runtime locates the Record, resolves its registered
Type, checks that any `expected_type` is the exact resolved class before
construction, and invokes that class's `from_record()` boundary. The expected
Type never selects a different implementation. Callers use Python inheritance
on the loaded object when they need parent behavior.

`tarav.l3.loading.load(path=..., profile=...)` is a caller-selected discovery
facade over that same loading engine. A `LoadingProfile` class supplies an
ordered set of relative entry paths for a directory; it does not select the
Record Type or constrain its family. Without a profile, the existing default
entries and `DirectoryRecord` guard apply. An explicit file bypasses entry
search. Selection remains in the Kernel engine; the Loading workflow and
runtime supply configuration without reversing Kernel dependencies.

The Python Workflow owns explicit process execution. `RunnerConfigurator` is
the abstract selection contract, `CurrentRunnerConfigurator` selects the
interpreter running Tarav, and `RunnerConfiguration` is the resolved value
consumed by the shared file/source runner. The Project Workflow specializes
that contract with `ProjectRunnerConfigurator`; its bootstrap input is a
`ProjectLaunchConfiguration` read from the `harness` of project.json without
concrete Project Type dispatch. Environment selection is explicit and never participates
in Record loading or automatic imports.

`tarav.l3.runtime.get_runtime()` returns the lazy process-wide current runtime;
`tarav.l3.runtime.set_runtime(runtime)` selects a separately composed runtime. Library
conveniences use it directly; Record Archive reaches its trusted Type registry
through Kernel's configured accessor. Callers do not pass that registry through
Archive APIs. Archive validates on write and dynamically loads on read.

Each typed Record Archive keeps its identity and constitution in `main.json`.
Its placement index lives separately in `entries.json`: names or Vector
positions point to retained ArchiveEntry Records under `records/`. Each Entry
Record points to a file or directory under `artifacts/`, which loads through
trusted Type dispatch. The index owns mutable names and positions; Entry
Records do not repeat them. Archive `ls()` exposes lightweight entries from the index, while selecting
one entry reads its Record and `open()` loads its artifact. An artifact can be
another typed Archive, recursively using the same layout.
Index reads use the current `entries.json`; mutations take one lock per Archive,
read that index again inside the lock, write the new artifact and Entry Record,
then atomically replace the index. Readers need no lock. An interrupted write
may leave unindexed files, which remain available for a later integrity audit.
The global `tarav.l1.archive.records.ARCHIVE` is a read-only `ArchiveRoot` folder at the Tarav
Archive data directory. `ArchiveExplorer` holds navigation state and history;
folders and lists hold no cursor. An `ArchiveEntry` opens a retained object or
another Archive folder, list, or path-only grouping. A Workflow Ship partition
opens as an `ArchivePartition`, which can separately resolve its owning Workflow.
Contained objects need no Archive interface, and intermediate groupings need
no retained Record.
`ARCHIVE.for_workflow(WorkflowType)` resolves the registered Workflow Ship and
returns a handler for `archive/<workflow-ship>/` without creating data. The
handler explicitly creates subdirectories and registered typed Archives,
including Dictionary and Vector structures. Human-readable workflow names
remain labels; renaming one does not change its storage path. Existing
name-based partitions require a one-time
migration, with no runtime fallback reader.

The Workflow Ship partition is never a Git repository. Archive directory
creation uses the nearest repository below that boundary, or creates one at
the new child when none exists. A standalone typed Archive still initializes
its own repository. Optional `git-config.json` files set a child policy of
`auto`, `new`, or `inherit`; lookup stops at the nearest repository so a policy
above it does not force nested repositories. Archive directories expose the
effective policy and its source, plus each directory's native `.gitignore`
path and presence. Existing repositories are not rewritten by this policy.

## Package layers

The general import direction is:

```text
adapters (`tarav.l3.cli`, `tarav.l3.daemon`)
                    ↓
            `tarav.l3.runtime`
                    ↓
    `tarav.l2` cross-workflow integrations
                    ↓
      `tarav.l1` workflow mechanics
                    ↓
            `tarav.l0.kernel`
                    ↓
             `tarav.l0._core`
```

This is a dependency direction, not a requirement that every module pass
through every layer. `l0` contains the foundation; `l1` contains independent
workflow mechanics; `l2` contains integrations and features that depend on other
workflows; `l3` contains the installed runtime and process adapters. Context and
SKW already span levels. A semantic workflow namespace can span levels; levels
do not establish Workflow parentage. Lower layers do not import higher layers.

- `tarav.l0._core` is the private utility package. It holds no workflow's
  mechanics; `_core.home` is the Tarav home (`~/.tarav`, its global config and
  storage). New shared utilities enter `_core` only after demonstrated reuse.
- The Project namespace spans layers. `tarav.l0.project` is its lowest part:
  marker, config, discovery, layout, storage scope, project selection and the
  project command log, usable by any workflow. `tarav.l1.project` holds the
  Project Type, `tarav.l2.project` its integrations with other workflows, and
  `tarav.l3.project` bootstrap and launch.
  <!-- tarav.breadcrumb 6d977147b5ef1427a82b4bd98151c7dc8581979853d8dae74631c18395befb29 -->
- `tarav.l0.kernel` contains Tarav's public semantic foundation: Types, Objects,
  Entities, Ships, class-owned Record interfaces, Explorer contracts,
  Record-space contracts, and trusted Type and Workflow registries. Kernel
  imports no application domain.
- `tarav.l1.records` owns `TaravRecords`: runtime-local mounts of workflow-
  contributed Record providers, a lazy `RecordsRoot`/`RecordsExplorer`, and
  on-demand Entity discovery. `RecordMap` is an optional typed, keyed store;
  `RecordRegistry` offers Workflow Ship partitions under
  `~/Documents/tarav/records/` or an explicitly selected root. Records sources
  keep their own storage layouts and need no per-Record global registration.
  <!-- tarav.breadcrumb 013cd36673190cd8c872889558b1cb8ac1236068984883faab3582e17d8db005 -->
- `tarav.l1.context` owns the Context Explorer, the identifier resolver
  service and the Context Workflow declaration, without loading Archive or
  runtime. The runtime composes the resolvers and configures `.context()`.
- `tarav.l1.cli` projects the built argparse tree as stable `Command` Entities
  and supplies command checks. These runtime-derived objects are resolved from
  the current parser tree, not loaded as standalone retained Records.
  `tarav.l1.usage` retains bounded, workflow-attributed
  traces in typed Archive folders with workflow-owned daily files. Callers
  choose their trace payloads and a `UsageTrace` subtype whose owner renders
  that payload. Newly written rows carry the Type name; older untyped rows
  remain queryable until they age out. `tarav.l1.live_help` renders source and
  recent usage leads on demand, selecting exactly the Type and subject named
  by its provider rather than interpreting CLI fields. The l3 CLI adapter
  records `CommandUse` traces; command owners supply concise descriptors of
  their calls.
  <!-- tarav.breadcrumb 4c65e8ba6ee4799e598a5973b7dbfc70858d934bd4e2abc9bc4c07ac06e9d207 -->
  <!-- tarav.breadcrumb 217080a6ff2b0b121aee1e55ec553d860ad1076d13b23db78882b78b1694e72f -->
  <!-- tarav.breadcrumb 5ede35bc5676515a281d72565d409ecb46bbe06adab48eedf903130170c49bcd -->
- Domain packages own their vocabulary, Records, storage, validation, and
  operations. Cross-domain imports remain acyclic.
- `tarav.l1.archive.records` implements Record Archive, nested beneath its parent
  Archive workflow. Artifact-registration Record definitions live separately in
  `tarav.l1.archive.artifact_records`; Archive's parent implementation does not
  import its Record Archive child. Its retained layout remains Archive-owned;
  it shares exact-type write and Git initialization mechanics with Records.
- `tarav.l1.loading` owns profile discovery and `tarav.l3.loading` owns the
  runtime-backed load facade. `tarav.l1.project` owns the minimal Project Type;
  `tarav.l2.project` adds Models and Wiki integrations. Archive uses the
  kernel-owned current Record registry.
- `tarav.l1.git` owns bounded repository mutation and preserves unrelated index
  state through isolated commit indexes. Immutable Git surface References stay
  in `tarav.l1.references.git`. `tarav.l2.git.breadcrumbs` composes Git and
  Breadcrumb evidence; `tarav.l3.git` exposes process adapters.
- `tarav.l1.git.hooks` owns Project Git hooks: the `git` config section,
  registered handlers, the scripts in `.tarav/git-hooks/`, in-process dispatch
  and the hooks check composed into every Project suite. It reads Project
  config, not the Project Type. Handlers such as `tarav.l1.git.change`
  (tarav-change IDs) are registered in runtime composition. Git hooks are
  synchronous and unrelated to the daemon's event hooks in `tarav.l1.hooks`.
  A handler may stop Git with `GitHookRefusal`, overruled through
  `TARAV_GIT_HOOKS_OVERRULE`. `tarav.l1.git.witness` keeps, outside the
  repositories, the tarav-change IDs each Project branch had; tarav-change
  stops commits that lost some and hands stops and overrules to
  `ProjectActions.register`, which registers actions without treating the
  results as a whole run of the Project's checks.
<!-- tarav.breadcrumb 547dbca6729188942ad14da5fa869377507896794295376fc49b060ca002ef48 -->
<!-- tarav.breadcrumb c61ceaf85a21dbe08b378bf6e378b6ac3e27aa499cb15654c8f2c67b22b7d00c -->
- `tarav.l1.skw.code` owns neutral typed document blocks, typed block-local
  objects, workflow-owned block annotations, retained content, common reading
  declarations, the abstract ReadingGraph analysis contract, and compilation.
  The compiled product is an ordinary surface; the reader does not interpret
  SKW source Records in a selected Project depot. `skw.skills` owns skill components,
  its concrete SkillReadingGraph package binding and rendering, deployment, and
  checks. ProjectReadingGraph is a Project-owned specialization point, not a
  claim that Project path declarations already exist. Trusted Type dispatch
  preserves the common source model without making skill conventions universal.
  <!-- tarav.breadcrumb f913f3d58def9bc67cd9b561a78e408fb2115c55f4dc786a34143215d1c80fa2 -->
  <!-- tarav.breadcrumb fd80d020457e9d3c90d4877cdc695a47a63cc284efa834ae686d95eba2e67ff7 -->
- Integration bundles compose independent domains without making either one
  depend on the other.
- `tarav.l3.runtime.create_runtime()` currently assembles the installed
  Workflow classes, services, Record Types, providers, hooks, and integrations.
  This is a library assembly facility, not a foundational Workflow contract.
- CLI and daemon packages translate external interaction into library calls.
  Lower layers neither import nor shell out to the umbrella CLI.

## Kernel contracts

`tarav.l1.lines.Block` is a storage-independent entity with a named topic and
ordered Line membership. Its Record retains Line Ships; explicit binding
resolves the ordered members without changing them. Membership does not change
a Line's scope. `tarav.l1.lines.Line` is a storage-independent entity with text and one
interpretive entity scope. Its Record retains the scope Ship; explicit binding
resolves that edge without changing it.

Archive exposes workflow membership through `ArchiveType` / `ArchiveObject`. Explorers are workflow
Types without requiring the Object Record contract. Their roots may be owned
leaf objects; listing or selection then raises `NotADirectoryError`. Shared
Explorer helpers check Folder/List capability and key typing. Workflow-specific
explorers enforce membership at roots and navigable destinations before moving.
Opening a foreign value remains valid and does not enter its graph.

The Kernel establishes only the common contracts needed for interoperability:

- `TaravType` provides class help, class context, and the `class_entity()` hook
  used to project the Python class into the Diagram.
- `TaravObject(TaravType)` adds an instance and a class-owned Record projection.
- Object namespaces are bound views: the host class selects an uppercase
  `NamespaceBase` subtype and a lowercase accessor exposes its path.
  When independent bases contribute the same namespace, the combined class
  explicitly selects a subtype of every contribution; class creation checks
  this instead of silently accepting Python's first MRO choice.
  `TaravObject.Records` is the selected class. Its `records` descriptor binds
  either an instance for `obj.records.to_record()` or the concrete class for
  `Type.records.from_record(record)`. Validation and examples also live in
  `Type.Records`; a Type specializing either operation selects a `Records`
  subclass of its parent Type's namespace. This preserves `super()` behavior
  while keeping the Record API on the qualified path. The protected
  `_from_record()` and `_to_record()` hooks remain on the Object Type.
  <!-- tarav.breadcrumb 2b4d0ce9f52ac6614285c0cb33affd22518ad2c0d09dec2e991a4a3a5abe3350 -->
  <!-- tarav.breadcrumb 6281d4ad34d874e60b28ba7685121b6fe4e82a3ca009fedd5f7e24c7d5029161 -->
  <!-- tarav.breadcrumb 78e31bb5c1cea43feb37bc863e871c7a37989518872a563facced759839b0eae -->
  <!-- tarav.breadcrumb 41d6e41fe955b0a983f42dd222805b0c3d1500ad9f0455ef74ed524d1797e80f -->
- `TaravEntity(TaravObject)` adds a stable `Ship` identity as class-owned
  runtime state and projects it through the Entity's Record interface.
- Every concrete Type has a class-local `class_entity()` definition. Its
  returned `TaravClass` carries a stable Type Ship; the human-readable name may
  evolve without changing identity.
- Every Object inherits a Pydantic `RecordInterface`. Classes may extend or
  deliberately replace representation ancestry.
- A Record is a projection, not the Object's runtime data model. `_record`
  retains loader-supplied material when it exists; runtime-created Objects need
  not populate it.
- `obj.records.to_record()` calls the class-owned `_to_record()` hook, then
  validates and detaches the result. `Type.records.from_record()` validates
  input before calling the class-owned `_from_record()` construction hook.
  When a Record supplies a Type reference, both boundaries require it to
  identify the object's exact class;
  a direct class call may also accept a Record without that reference. Dynamic
  loading requires a Type reference for dispatch.
- Types decide what their Records contain, how they keep runtime state, how
  they construct instances, and whether any representation is persisted.
- Loading selects only explicitly registered trusted classes. Records never
  select Python import paths; an external class path comes from a trusted
  environment binding. The binding can change during a runtime, while Python's
  module cache governs changes to installed code. Unknown JSON remains
  ordinary JSON.
- Record validation does not silently normalize, repair, or add defaults to
  retained data. Schema changes use explicit migrations.
- Ships are identity primitives. Their containing Type and relationships assign
  meaning; Kernel does not infer roles by scanning UUID-shaped values.
- `LiteRecord` snapshots small dictionary-shaped coordinates with deterministic
  JSON-compatible encoding. It accepts only explicitly supported native values
  and trusted exact-type serializers; it is not a TaravObject Record or a
  general persistence engine.
<!-- tarav.breadcrumb 8f350694aed09c2c604f1e905cc7a164af169548d4cc9d4861210ed25729723d -->
- `FileRecord` and `DirectoryRecord` classify retained shape without imposing
  one application storage model.
- `ExplorerEntry`, `ExplorerFolder`, `ExplorerList`, and `Explorer` give
  workflows a shared navigation language. `ls()` returns entries; `get()`
  selects one; `open()` returns its value without moving; `cd()` moves an
  explorer into a navigable value. Back/forward track visits, independently of
  parent traversal. Storage and relationships remain workflow-owned. External
  implementations subclass `tarav.l0.explorer_testing.ExplorerContractTests`
  and supply its abstract fixture and expected-value methods. Pytest runs the
  inherited tests without a registry or custom runner. Archive and Context use
  the same suite; checks cover current location and both history stacks.

Kernel supplies the shared language. It does not own workflow-specific
relationships, storage policies, or interpretation of domain payloads.

## Domain ownership

Project's optional Python harness spans `tarav.l2.project.harness` (inspection,
scaffolding, uv sync) and `tarav.l3.project` (trusted runtime bootstrap and child
launch). A Project's `.tarav/project.json` is its Record and the Project
workflow's own configuration: `project_id`, `created_at`, `project_name`,
`harness` and what its Type adds (a Root's `children`), validated by the
Type's RecordInterface. `harness.environment` is a uv environment, relative to
the Project and possibly another Project's; `harness.type` is the Project's
Type as `module:Class`, installed in that environment. The manifest sits
beside the environment and only installs packages. Inspection and runner
configuration read `harness` without importing anything; the launcher imports
`harness.type`, loads project.json with it and requires its type tag to name
the same class. `.tarav/config.json` holds one section per workflow that
configures a Project (`tarav.l1.project.config`: `agents`, `skills`,
`diagram`), each validated by its owner's model and registered by the
runtime. `ProjectFilesCheck` (`tarav.l1.project.files`), in every Project's
suite, reports undeclared fields, a missing harness or environment, a
`harness.type` that is not the Record's Type, and config sections no workflow
owns or that their owner rejects. Run never installs or selects a fallback
interpreter.
<!-- tarav.breadcrumb 8ffca46a4e978d081bb7a558f1ea51f3d807a474c4a46f1c92352463d7e1629d -->
<!-- tarav.breadcrumb 806fd99acd25e2fd66cf0c4509e4687ce68c7bf05f2b369e92692a3f499f325d -->
<!-- tarav.breadcrumb bc39462931a983db3b9c5c92904046a92839d3dc3ee4d7923899fd369d658267 -->

A machine has one Tarav System Project, an ordinary Project at
`~/Documents/tarav/system/` from which work over all Projects is done;
Projects never know about it. `TaravSystemProject` (`Tarav.Project.System`,
`tarav.l2.project.system`) is its base Type; the machine's own Type
subclasses it in its harness. Its record adds `active`, the Projects it works
on, kept by hand; its suite adds one `ActiveProjectCheck` per active Project,
which loads that Project through its own harness, in its own environment,
and reports one that is missing or does not load. `tarav init --system`
(`tarav.l3.project.system`) creates it once per machine: the folder, its
harness (`scaffold(base=...)`), its environment and a Git repository.
<!-- tarav.breadcrumb 91260ffaa49dae900702a655cdbbaeacab670134cdeec45099dfd6bfbfdf27b3 -->
<!-- tarav.breadcrumb f4f493ec99d35a8bef4ea8b09e87c6a0305d758e6412dd80d6309fc546d4af69 -->

`TaravProject` is a `CheckProvider` (`tarav.l1.checks`) whose base suite
checks its Skillware-produced agents file through `project.agents.agents_md`.
Subtypes compose that suite with `super().suite()` in their `Checks` namespace;
`project.checks.run()` executes it and reports typed bootstrap POIs.
<!-- tarav.breadcrumb b7370472b54dcbd8b1197f1213ba85bd1f81e661427b03739287f8c444921945 -->
<!-- tarav.breadcrumb 8fa3ca276796996a3fe4d571fb8cae3876778ffccaf5ee40a6510ca1e046dff0 -->
<!-- tarav.breadcrumb f6132fabb0037fce1edf20f899399f42f53277dae02a26475989bfa4e0d2c2e9 -->
<!-- tarav.breadcrumb 0bd03575af287c630888eba439224a79e98b04bb08e8371be586ba38c8416bbe -->

The Checks workflow owns `CheckSuite`. A suite is a detector: it does not
contain checks, it holds the code that runs them (`produce()`), because which
checks exist is only known while it runs. A provider returns a suite; its
`run(select=...)` runs it whole or filtered and returns the suite itself,
which holds the results of that one run and builds the summary and the
bounded report. There is no separate run object. A subclass is a suite with
its own Type id and a `key` binds an instance to a subject (`identity`); a
plain grouping has no identity and counts as part of the suite above it.
`exhausted` says the suite's own code ran to its end with nothing refused,
and `conclusive_for(check Type)` that its own checks of that Type also
completed; a nested suite with an identity answers for itself. `walk()` gives
each result with the identified suites above it. A suite may declare the
folders of the Git repositories its checks read (`repositories=`); when it
runs it first records their HEAD and whether they are clean (`suite.git`,
read through `tarav.l0._core.git_repository.repository_states`), and each
result carries the state of the nearest declaring suite (`result.git`). A
Project's suites declare `TaravProject.repositories()`, its root by default.
A class with `routine = False` is left out of the repeated run. `PyTestSuite`
(`tarav.l2.project.dev`) runs pytest once and yields one `PyTestFileSuite`
per test file. `tarav check --project` (`tarav.l3.check`) launches the
Project harness, binds the Project's Type, and prints the report rather than
every result; it and `tarav status` leave non-routine suites out
unless `--all` is given. `tarav status --project` (`tarav.l3.status`) is
about actions: `status_result()` builds one result from the Project's
status, and `status_text()` shows the open actions per Project, what the run
opened, reopened or closed, and one line about the checks; `--json` prints
the whole result, the check report included. The check report's text names
only what needs saying: checks that did not complete and suites left out.

`tarav.l1.project.index` keeps machine-local observations of portable Project
IDs and their locations under the Tarav home. Explicit Project CLI operations,
`tarav run --project`, and `tarav check --project` notify it on a best-effort
basis. `tarav project list --global` validates remembered locations without
discarding missing paths; an explicit `--root` scan can rediscover moved
Projects. The Project marker owns identity, while this index only helps locate
it. Concurrent live locations sharing one ID are reported as ambiguous.
<!-- tarav.breadcrumb 79bfd183bfe36bf3a301b38b727cb585b1c87039bfac199ef244b1e2b949cd12 -->

The generated package holds the code-owned Project TypeShip; project.json
retains the separate project-instance identity and names the class in
`harness.type`. Adoption of an existing base/untyped marker is explicit; a
marker with a harness or a specialized Type, and edited source, are not
overwritten. The sole CLI
runner is `tarav run [--project [PATH]] -- <python arguments>`. Bare
`--project` discovers the nearest parent Project and fails when absent;
omitting it uses the current Tarav interpreter even inside a Project. It executes
caller-supplied Python with current or selected Project configuration and does
not inject a runtime or Project object. The typed bootstrap remains a library
operation; the duplicate `project harness run` and `python run` CLI leaves are
absent.
<!-- tarav.breadcrumb e8ab00134f9f3d963f3a3a30cd96fc36190a12c2c2d6762cf992d9486ae3da9b -->
<!-- tarav.breadcrumb b79a8bbf9c2eb86e97adaa9e7580e6b44498aab5e61797662db178b846712288 -->

`tarav.l1.chatlas.sessions` exposes indexed conversations through an
`ExplorerFolder`: entries construct a portable `ChatSession` without capture or
normalization. Native-ID keys require unambiguous provider/instance scope;
an explicit identity-hash view handles collisions. `ChatSession.model()` delegates
to the existing Normal Model reader and cache. The depot root is runtime
configuration, not retained Session identity or part of its portable Record.

`tarav.l1.programs` declares `ProgramsWorkflow` and the minimal
`TaravProgram(TaravEntity)` family. `tarav.l2.project.programs.ProjectProgram`
provides a distinct project-oriented subtype without adding fields or behavior.
Both are currently owned by ProgramsWorkflow and registered for ordinary Record
loading. This bootstrap deliberately leaves Project attachment, runs, lifecycle,
checks and derivation undefined; package placement does not imply an attachment
schema or an additional Workflow identity.

`tarav.l1.operator_context` declares `OperatorContextWorkflow`: the standard
place where an operator puts the typed objects it hands to other workflows.
`OperatorContext` is the base Record Type and `OperatorContextStore.take()`
gives a consumer the object with the hash of the record it read. `tarav.l1.actions`
declares `ActionsWorkflow`: the near-empty `Action` root, `StepAction` (an
opening test, operations, and named exits with their tests, each taken by an
operator, the loop or a suite), the recorded `ActionRun` and `StepRunner`, which
takes every operator input from the Operator Context and sweeps loop-taken
exits. A run has a tape (`tarav.l1.actions.tape`): its important events as
typed entries, appended and never changed (`Opened`, `Closed`, `Reopened`,
`ClosingAttempt`, `Clean`). Its state, exit and times are read from it;
closing a run puts on its `Closed` entry a typed `Closing` record, of the
Type its exit names, so a reopened run keeps how it closed before.
<!-- tarav.breadcrumb 570734881cadb156371432ad993da91655d1a1e196c8ad45d5bff00f74284305 -->
<!-- tarav.breadcrumb 00b84f42127c802526915a6b38a81e64cfe2c348179505a74512b7b8893fdf7f -->
Actions and their runs keep
their Records in their own Record Registry partitions, outside any Project.
Action Types are made startable by explicit `register_action()`; the runtime
registers them. `tarav.l1.actions.pois` holds what follows a POI:
`ActionablePOI`, the `POIResolutionAction` with the closing paths `gone`
and `blessed`, and what that Type does with a run of its Project's checks
(`on_checks`). `tarav.l1.actions.project` holds `ProjectActions`, reached as
`project.actions`: the actions registered under one Project. The Project
composes the two in `project.status()`: it runs its own checks and hands the
results to its actions, and a container asks each member Project to do the
same for itself. A POI a Project's checks no longer produce closes its
action as `gone`. While `<project>/.tarav/tests/` exists, the l2 `Project` adds
`TestFixturesSuite` (`tarav.l2.tests.actions`): its files raise test POIs
whose actions are real actions of the Project, for trying the action loop on
the live path. Each status entry of the tape holds the state of the
repositories the suites above the action's checks declare, and per
repository the first clean state after it is a `Clean` entry; `tarav status`
names the repositories that were not clean. The instance of a POI's action
is derived from the POI's identity; its tape holds its status history and
every other change is in the registry's Git history. Checks do not import Actions and
give the owner no meaning; a run that no owned suite produced is momentary
and resolves nothing. Programs and Actions are not yet related in code.
<!-- tarav.breadcrumb 58b3f302d6feb1b9dae016d622a4e167c5e3feee3ddf367a1d80f7a407090c34 -->
<!-- tarav.breadcrumb 65f4b92f79c26cf5c9ee82a2b078a07544de789b0048398b49220ebfb1a2deaf -->
<!-- tarav.breadcrumb 30efa0fe92a4ac9a03ca66694ed3c3c8ce91e1c266e56e7023a995e0ab42e85d -->
<!-- tarav.breadcrumb 929afad70096e02099ff49b90d972f977d4fe6d461aad33cb206b91490e8c905 -->
<!-- tarav.breadcrumb 8f83b152a5ae963ef35445d9aa3bc877077e7d780b5658434fe7343fc77815ca -->
<!-- tarav.breadcrumb 79c4b2ba1ae60b9c354194f6019851a30bd082d3f144adac272728093277e5df -->
<!-- tarav.breadcrumb 9ee4d9dcc84f3fe51b675d28058a032060fb73abc4cc794542649b33aec1eb74 -->
<!-- tarav.breadcrumb 2d9d5a81415b516dd8e6f4906bdb3917d37b71ca15ceb895eef1ff8f02d4ce1f -->
<!-- tarav.breadcrumb 2955673512f98334e8762754e2942b0b414a003b1a934b0f5e95255350bee784 -->
<!-- tarav.breadcrumb 603b695bea90466baff80405c3dcd835ba2c264f5dfd89c3798f6f4c953ec87f -->

| Package | Architectural responsibility |
| --- | --- |
| `agent` | AgentsWorkflow. Provider-neutral agent, account, session, and monitoring behavior; concrete providers (Claude Code, Codex, Copilot) live below `agent.providers`. `agent.current_session` names the running agent's session through the adapters that inherit `ReportsCurrentSession`. |
| `archive` | Artifact identity, retained Archive Records, and Archive-specific location history. |
| `archive.records` | Optional typed Folder and List Archives for storing class-owned Records at explicit roots; the stored Type keeps its domain meaning. |
| `records` | TaravRecords workflow: contributed Record-source navigation, on-demand Entity view, and optional standard keyed RecordRegistry partitions. |
| `search` | SearchWorkflow owns typed incremental queries and a registry-backed meta engine. SearchEngine Types contribute a bound `.search` namespace; the runtime holds one SearchService per composition. Engine registration does not imply storing queries or hits. |
<!-- tarav.breadcrumb 4597f1786f7c1c0b1fce993a19bef717743bb666489fd98b1b2fcad2d4f8e253 -->
<!-- tarav.breadcrumb 9b87f84163c1777984484c0543b3e3011a5bea09e1c24833b15527175c4f9e52 -->
| `l1.context`, `l3.context` | The Context Workflow: ObjectContext construction, ordered hooks, the Explorer and resolvers, and the `tarav context` command. |
| `references` | Shared typed locator, check, hints, and resolution mechanics. |
| `chatlas` | Provider-native chat capture, Session Index, provider-neutral Normal Model, bounded Query, and rendering. |
| `breadcrumbs` | Opaque Product.Surface anchors, position observations, attachment storage, and generic annotation transactions. |
| `breadcrumb_workflows` | Independent integrations between Breadcrumbs and producer domains such as Chatlas. |
| `l1.git`, `l2.git`, `l3.git` | The Git Workflow spans repository mechanics, commit-message Breadcrumb integration, and installed CLI composition. |
| `lines` | LinesWorkflow owns Line, Block, Collection, their editions and relationships, projections, rendering, and LineGroundingAssertion semantics. |
| `models` | ModelsWorkflow owns the Model handler, ModelShipRecord, and ModelEditionRecord. Project associations do not imply ownership; several projects may share one Model. |
| `unsorted` | UnsortedWorkflow provisionally owns legacy capture, generic storage interpreters, assessment, Draft, and View types awaiting classification. |
| `assertions` | AssertionsWorkflow owns the shallow TaravAssertion root and Assertable capability. The base imposes no case-production method. |
| `scoring` | ScoringWorkflow owns the identified, case-producing Assertion subtype, closed AssessmentCase contract, shallow Score root, and retained evaluation mechanics. Scoring Records are entities with explicit Context reference edges. |
| `scoring.ranking` | RankingWorkflow is a Scoring subtype and child workflow. It owns pairwise cases, singleton Tribunal entities, pairwise operations and Checks, and ephemeral RankingScore results. |
| `poi` | POIWorkflow owns neutral, identified, and notification POI foundations plus shared collection and notification delivery. Identified POIs derive identity from their concrete Type Ship and explicit producer-supplied situation; collector-local indexes address repeated emissions. Producing workflows own their concrete POI types. |
| `actions` | ActionsWorkflow keeps typed Actions and one record per action in its Record Registry partition, outside any Project. `StepAction` has named exits taken by an operator, the loop or a Project; each exit names the `Closing` record Type it leaves on the run's tape, and that Type decides whether the POI raised again reopens the action. `tarav.l1.actions.pois` is what follows a POI: an `ActionablePOI` (the capability lives in `tarav.l1.poi.actionable` and is extended by `CheckPOI`) spins the `POIResolutionAction`, whose instance is derived from the POI's identity. Check code carries no Project: `project.checks` only runs checks. `ProjectActions` (`project.actions`, `tarav.l1.actions.project`) never runs one: `start(run)` registers under the Project the action of each POI not registered there (a new one is built by its Type, one of another Project moves), `refresh(run)` hands the results to every registered action, open or closed, and `update(run)` does both and records them. `Action.on_checks(run, update)` is what a Type does with them; the base ignores them. `POIResolutionAction.on_checks` marks the situation present and reopens when the closing says so. An action keeps the identified suites above the check that raised its POI (`event.suites`); when the POI is not raised, the nearest of them that is in the run decides, and the suite handed over does when none is. That suite is conclusive for the POI's Type of check: the situation is absent and an open action closes as `gone`. Otherwise the action stays, with the situation `check failed` when a check failed and `not run` when the suite was left out. A removed check, a removed suite and a check that no longer raises anything are the same case: a detector that ran no longer reports it. `project.status()` (`ProjectStatus`) composes checks and actions; `tarav status` runs it. A run that no Project hands over is momentary; `tarav skw skills check` records no action. Status is three axes, `axes(run)`: the situation (`present`, `absent`, `check failed`), the action, and the closing. `blessed` is an operator's exit with a reason from the Operator Context, allowed for a `BlessablePOI`. `tarav status` is settled when every check that ran completed and no action is open: it reads only actions. A Project sees the actions of the Projects it lists as children (`tarav.l1.project.scope.project_scope`, read from the markers): `project.actions.list()` and `tarav action list --project` include them, each action still naming the Project it belongs to, and `own=True` or `--own` leaves them out. Checks never write to the registry. The resolver that finds an action by id lives in `actions.views`. |
| `decisions` | DecisionsWorkflow owns the shared attributed Decision contract and prescribes no concrete subtype of its own; consuming workflows define theirs. It owns no storage. The common actor field is exposed as `decider`; subtype schemas keep their own fields and optional POI links. l2 builds an inspectable main Assertion for generic Decisions; assessment cases and attention policy are not yet prescribed. A Blessing is not a Decision: it is the closing record of an action. |
| `blessings` | BlessingsWorkflow owns the `Blessing`: the closing record of a POI action closed although its situation still exists, with the actor, the reason, the offered support and the POI as it stood. The Type is defined in `l1.actions.blessing`, beside the Actions code it is built from, with `BlessingInput` and the test of that exit; the `BlessablePOI` capability is in `l1.poi.actionable`. A Blessing is Assertable; its Assertion and read-only score providers are composed in runtime from the l2 Blessings integration. A blessed POI is still raised and reported; its action stays closed. There is no separate blessing store. |
| `checks` | Independently runnable bound Checks, CheckPOIs coupled to their Check objects, optional subject providers, and result snapshots. SituationChecks evaluate a detached Situation and use that same snapshot as the POI acceptance scope. Execution completion and a POI's failure signal are separate. |
| `l2.tests` | TestsWorkflow is a shallow parent in `tests.workflow`. `tests.navigation` owns disposable Context/Archive fixtures; `tests.scoring` owns a fixed synthetic User chat, ten Lines Blocks, fifty scoped candidate Lines, a Line-support Assertion/Case, and a dedicated ranking Tribunal. The scenario closes cases from the synthetic evidence; tests exercise judgment and derived scores without a live agent. |
<!-- tarav.breadcrumb b750afdefcc38c23df01af9ca67d4f9d81f2795c8e12860d22ddc28782038a74 -->
<!-- tarav.breadcrumb 28df20317b527872af6eb271a0ede8e2a1c30d0b8fc98201f63e8cb564ec6183 -->
| `skw`, `skw.code`, `skw.skills` | Skillware umbrella, common source/compilation and ReadingGraph contract, and deployable-skill specialization. Blocks are Entities with Ships and separate labels; source blocks own typed reading declarations. SkillReadingGraph exposes route facts, while skill-owned Checks turn those facts into POIs. |
| `surfaces` | SurfacesWorkflow owns MarkdownNormalModel, its strict LineMarkdownModel subtype, and PythonNormalModel TaravObjects. Their from_text/from_path methods parse native syntax; Records preserve parsed structures without reparsing. LineMarkdownModel is a floor for owned formats: it raises at the first dialect violation instead of returning a partial model. Consumers assign domain meaning. |
| `wiki` | Folder-based Markdown Wiki and WikiNote objects, parsing through surfaces, and Wiki-scoped Git closure. No Project dependency. |
| `project` | ProjectWorkflow owns minimal TaravProject and featured Project. Existing project_id is the Ship identity; discovered location stays outside the portable marker. Every Project has checked agents-file and skill-availability bootstrap under `project.agents`; its agents-file Skillware source is `.tarav/skillware/src/AGENTS.skw.json`. Skill checks search Project and home `.agents/skills` by declared `SKILL.md` name, require `tarav-pkg` and the Project's `agents.package_skill`, and verify `.claude/skills` resolves to the same directory at both scopes. |
<!-- tarav.breadcrumb d3ca6d771b341182eaeb1d0e40e66fd170c16a48b632d1ac6c700bbfdf7b521c -->
| `project.models`, `project.wiki` | Specialized child workflows own Project associations. The featured Project exposes `project.models` and `project.docs.wiki`; the minimal base imports neither integration. |
| `workspaces` | Identified manifest-backed working folders under the Tarav data root. Exact worktree commits and retained file seeds define reproducible setup; a separate setup Record retains observed hashes and allocated branches. Workspace checks report POIs. The l1 workflow calls l1 Git for every worktree operation; l2 Project offers an optional view over the independent depot. |
<!-- tarav.breadcrumb 28d74cb87df8e2cd06518e6e21e63155236c88bedc83944c038fb1e1405943c1 -->
| `skills` | SkillsWorkflow: the abstract base Skill type, `TaravSkill` (a folder a harness loads through its `SKILL.md`; entrypoint, frontmatter, name, description), folder-backed `FolderSkill`, and skill discovery. Independent of Projects. Every kind of skill subtypes `TaravSkill`; `skw.skills`' `SkwSkill`, with its blocks, reading relationships and checks, is the one other workflows commonly use. |
<!-- tarav.breadcrumb 653af09b96035601ef5d332103371b28d24a22ca431ea077e29e123f3209064a -->
| `project.skills` | How a Project selects skills from its sources and profiles, installs them into the folders its agents read, and reports their status (`tarav project skills`). |
<!-- tarav.breadcrumb 80841d3434804e80c9fea866d78bdbb7642359e2f58de218e9a4ca46ed323b0d -->
| `hooks`, `daemon` | Hook validation and dispatch, plus daemon-owned delivery adapters. |
| `stdlib` | Small reusable library and CLI primitives. |
<!-- tarav.breadcrumb 5390bce98b91f130684fb3322d8ee0022a5e60bd1d5390e7e05c8c53b6718e01 -->

Other cohesive command domains follow the same rule: they own their behavior
and use Kernel contracts without moving their semantics into Kernel.

`TaravProject.from_path()` discovers the nearest marker and explicitly interprets
it; fields no model declares are kept and reported by `ProjectFilesCheck`.
Entity identity is
serialized as `project_id`, not a second `id`. Records loaded without a source
remain detached: their location cannot be inferred from identity. Untyped
markers are not rewritten; newly constructed Project projections carry the
ordinary `type` reference for generic dispatch. Explicit
`SomeProject.from_path()` constructs that selected class, reprojecting any
retained Type tag in memory without changing the file. Generic from_record()
and load_object() retain exact Type checks. Project-local code is never
automatically imported by discovery. Subtypes define class_entity() normally.

`Project.models` exposes the bound ProjectModels handler. Its `ls()` reads named
associations from the `diagram` section of the Project config; Model resolution through `get()` and
`main()` remains disconnected pending the Models redesign. `Project.docs.wiki`
returns the conventional notes/wiki folder without creating data.
<!-- tarav.breadcrumb a4389802948e1c2e30453b151e3436b217f6fbcff361475b4297284f7a80397e -->

## Integration invariants

Lines consumes provisional low-level contracts and Record bases in Unsorted.
Unsorted also owns the mixed legacy CLI adapters, preserving the public
`tarav diagram` command without a `tarav.diagram` Python package.
Higher-level Unsorted storage and capture compose Lines. These dependencies
must remain acyclic at module level; collapsing all provisional Unsorted
modules into one graph node would hide this distinction. Architecture tests
therefore inspect Lines and Unsorted at module granularity.

Models and Project are also checked at module granularity. Model's retained
Record definitions depend only on provisional low-level foundations. Project
associations belong to project.models; the public Model handler does not import
Project or legacy storage composition. `tarav.l2.models.Model` replaces
the old `tarav.lines.model.DiagramModel` Python path; retained TypeShips,
Record labels, Model UUIDs, and `diagram.main_model` associations are unchanged.

Assertions owns the common Assertable and shallow TaravAssertion contracts.
Scoring's `assertions` module supplies its identified, case-producing Assertion
subtype and the AssessmentCase contract without
importing consumer workflows. `lines.assertions` specializes it for exact Line
editions and supplies two case producers with different payloads. A case is a
JSON snapshot of its claim, question, and supplied material; the scorer does
not acquire source handles or search for further evidence. Unsupported case
Types and supported Types lacking sufficient material fail distinctly. The
runtime registers concrete case Types for Record round-trips. `scoring.tasks` is the existing
ranking composition layer; it imports that specialization, while the scoring
package's base exports do not import tasks. Import ranking adapters explicitly
from `tarav.l2.scoring.tasks`. Architecture checks inspect Scoring at module
granularity too, distinguishing foundations from composition.
<!-- tarav.breadcrumb 9d28b8a71a32f7309fe03c9f8d1c1eb9ee3d8802d2f973f679e9b85ab9561bb9 -->

`scoring.ranking.tribunals` is the cross-workflow pairwise path. Each concrete
Tribunal class constructs one identified singleton Tribunal entity. Its class
representative's Type Ship and its object's Ship remain distinct; existing
`tribunal_type_id` records still identify the class. Tribunal Types define
population membership, question, and instructions; case subtypes keep their
own payload schemas. The common ranker freezes a two-case prompt, retains an
attributed A/B/tie/abstain judgment in the existing ScoringRepository, and
derives an ephemeral RankingScore with separate comparison and coverage data.
Its Check emits POIs for unassessed, sparse, and weakly supported Assertions.
One enrolled case alone has no relative score, and a low score is not a
falsity verdict. No consumer workflow is imported by this shared module.
<!-- tarav.breadcrumb 1d37ba88764215a6fe2ba19ce8b60bd618215f3ef92de30de942dacb95d616db -->
<!-- tarav.breadcrumb afa385a96aeaf2ae558a4214fba859e9208c161d50405f1aa658112468efafa7 -->

The `Assertable` capability lives in `l1.assertions`, so
`l1.actions.blessing.Blessing` can declare it without an `l1 → l2` import.
Scoring's Workflow Ship remains in `l1.scoring`; `l2.scoring.assertions`
retains the identified Assertion and closed
case mechanics; `l2.blessings.assertions` supplies Blessing-owned producers.
Runtime composition binds the pure provider functions to the Blessing
Type. A primary `main` Assertion addresses the exact blessing and POI
situation; a `grounds` Assertion appears only when support is offered. Cases
include the retained POI snapshot, reason, actor, and resolved source
passages. A blessing can still be recorded with no support; unresolved offered
references make a case incomplete rather than inviting the scorer to research.
The read-only score vector queries scorer-owned tribunal results by Assertion
reference. Scores are never kept on the Blessing.

Decision records share attributed fields; `Decision.decider` reads the actor
role. A Decision subtype can refer to tracked POIs but does not require
one. The generic `main` Assertion identifies the retained intervention; no
scoring case is claimed yet. `project.actions.list()` reads a Project's
actions from the central Actions registry. `tarav status --project`
updates them from a run of the Project's checks; `tarav check --project` only
runs the checks. The
machine-local check-report cache stays separate: it holds what a surface last
showed, so that a printed identifier can be opened.
<!-- tarav.breadcrumb 903d50edc16c9a21d196b1271302c63a2574659e7adb9bda716b62a9314de7a3 -->
<!-- tarav.breadcrumb b6bdfb5131dd4eb553fce00b71dc1f8557188d614541a26666481bc6853125c0 -->

`l2.blessings.attention` composes the current POI collector, the POI actions
and l2 ScoringRepository into a separate, pageable due/deferred view. It does
not change check output or any record. A POI whose action is blessed is
deferred from the time of its Blessing, longer when the Blessing offers
support and its acceptance is well scored. A changed situation has a new POI
identity; a mechanically absent POI is never scheduled. The derived score
remains relative rather than a truth scalar.
<!-- tarav.breadcrumb d6e3d0827437513471422c2b746bb86ae468ccd2ebeb05292beb44d65d785dee -->
<!-- tarav.breadcrumb dc5c60cd5793d3b5adfee34f6fc6c811c17b005ca1313178cb0b23f13306175a -->

Assertions identify typed subjects; their subtypes define evidence and check
semantics. Scores are separate judgments, not Assertion identity. Scoring
reference Context entries resolve only through an explicitly supplied
repository or trusted Assertion registry. Existing grounding references,
ranking Record formats, and frozen prompt hashes are preserved. The provisional
mechanical assertion engine under Unsorted is not folded into this model yet.

- The subsystem import graph is acyclic outside runtime composition.
- Domains normally receive dependencies through composition. Record Archive
  uses Kernel's selected Record registry at its write/load boundaries without
  importing the assembled runtime.
- References is lower than Archive and other specialized Reference producers.
- Breadcrumbs and Chatlas remain independent. Their contextual annotation
  behavior lives in `breadcrumb_workflows.chatlas_context`.
- Commit evidence registers Breadcrumb identity and typed attachments before
  Git mutation, then appends the exact commit-message position as an observation.
  The commit retains a versioned evidence envelope so registration can recover
  without the temporary manifest.
- Native surface parsers expose syntax and source positions without knowing SKW
  or annotation policy.
- Chatlas capture and Session Index remain usable without importing the Normal
  Model. Consumers import the public `tarav.l1.chatlas.normal_model` surface.
- Query owns selection; renderers own presentation.
- Hooks owns validation and dispatch; daemon adapters own delivery.
- Workflow-specific retained data and operational event logs remain domain
  data. Generic logging transport does not become their authority.
- A shared physical data root does not create one repository, schema, or
  authority. Each domain owns its storage contract.

`tests/test_architecture.py` enforces the import graph and the most important
boundaries. When a new integration needs to reverse an existing dependency,
the default solution is a runtime adapter or independent integration package.

## Sources of truth

`TaravProject.load_project(path=...)` combines upward Project discovery with
the Project's harness: it imports `harness.type`, binds it in the configured
current registry and loads project.json, whose type tag must name the same
class; the calling Project class checks the resulting family. A Project
without a harness does not load this way. This is separate from `from_path()`, which retains explicit
caller-class construction, and from generic loading, which does not discover
enclosing Projects. Import the runtime assembly or configure the registry hook
before using `load_project()`. Discovery does not execute project-local code.

- This file owns the system shape and durable dependency rules.
- `AGENTS.md` owns development constraints for this repository.
- Public classes and `RecordInterface`s own exact library behavior and schemas.
- `tarav --help` and subcommand help own the installed CLI surface.
- Tests own mechanically enforced invariants.
- The Project Wiki in `tarav-md` retains design rationale, alternatives,
  subsystem narratives, and implementation history that would obscure this
  overview.

The architecture document should change when those boundaries change. It
should not duplicate class APIs, command references, migration procedures, or
complete subsystem designs that are clearer beside their owning code or in the
Project Wiki.

Runtime provider wiring lives in `tarav.l3.runtime`, not the package root.
Import that assembly module before using current-registry or Workflow-instance
resolution, or explicitly configure the lower-level hooks in a custom host.
Importing `tarav` alone initializes no services or layered modules.

## Import entry points

Tarav has two import doors over the same library. The `tarav` console command,
the daemon console command, and `tarav_bypass` set an inherited process mark
before importing `tarav`. A plain import without that mark raises an error
directing scripts to `tarav run`, whose child process inherits the mark and
uses the selected Python environment. `tarav_bypass` is the explicit entry for
developers and tests that import Tarav directly; its module import does not
import `tarav`. The mark is a usability guard, not a security boundary, and
does not appear in the error message.
<!-- tarav.breadcrumb d85bcbec96c2c33b21a12ac57fc844ce0fdcb1a428026756ff13ec5d3e8041a2 -->
<!-- tarav.breadcrumb fb964adb1a2f8cfbdef9fabf07f33c12806155d2ff7c24a42fbe5329e9e59da2 -->

### Run registry

`tarav run` retains the code it executes so agents can study recent Tarav
scripts. `tarav.l1.python_env.registry.RunRegistry` owns the store under
`~/.tarav/run-registry/` (`TARAV_RUN_REGISTRY` relocates it for tests). Each run
gets one folder holding `entry.json` and, when there is source, `source.py`: a
copy of the script file, the `-c` text, or standard input, which the command
reads fully and replays to the child. A `-m` run keeps the module name only.
Runs with `--project` are partitioned by the Project's id and the rest go to
`global`. The entry is written before the child starts and completed with its
exit status. Size is the only retention rule: a source beyond 1 MB is cut and
marked, and a partition beyond 50 MB loses its oldest entries during the write.
The registry is best effort; a failure is logged and the run is unchanged.
<!-- tarav.breadcrumb 04da500bc54214879fa3a0f8232b112490cda176917b4db38c121fcbefc7bd84 -->
<!-- tarav.breadcrumb 649ec18a1017f2ff0525ba9bc96eb1f33a319556bf9e2789f24eb9d5ec2287e3 -->

### Context queries; the POI is a flag

`tarav context --id <identifier> [--json]` is the shell door to the same
Explorer that scripts open with `obj.context()`: it prints the subject and
the edges at it. `tarav.l1.context.query` owns the typed `ContextQuery` (an
identity query by default) and a `ContextQueryService` whose resolvers are
Search engines; the runtime composes the installed ones. One match opens,
several are listed, and a unique prefix is enough. `--view` is kept only to
fail: named views, such as the former object group, are not implemented in
the graph model and come back as queries when needed.
<!-- tarav.breadcrumb 2c617b4d656b44c0c0e7bdc5c0fcf1f69767a972143f195f29c01fdbc973d469 -->

A POI is a flag between detecting and working: what a check returns. It is
momentary and owns nothing; nothing stores a POI that was printed. It gives
an action its identity, it keeps detection apart from work, and inside a
step it is the reason the step could not close. The model is three classes
deep and has no optional parts. `POI` has a Type and a message.
`SituationPOI` adds a situation, an object describing what was found, whose
content each line of POIs decides; the Type plus the situation is the
identity. A specialization adds fields of its own Type, named for what they
hold: `CheckPOI` adds `check`, `details` and `failure`, and other lines
declare theirs, such as `hints` on a reference resolution POI or `entry` on
a skills status POI. A POI becomes data in one way, the Record system:
`poi.records.to_record()` gives its Type, message, situation and the fields
its Type adds, and `from_record()` loads it back. The record holds the
occurrence only; what the Type says (its description, where it is defined)
is read from the class. A consumer decides what
happens to a POI. Printing (`tarav check`, `tarav skw skills`, the
breadcrumbs and Diagram commands) is how a person looks at checks directly.
The Project status escalates: each POI its checks raise becomes an action
registered under the Project, which keeps `describe()` in `event.source`. A
running step keeps the POIs of its tests as the reason it could not close.
What integrates several workflows, such as blessing or asking how an action
stands for a POI, is modeled on the Project (`project.actions.of(poi)`,
`standing(poi)`, `blessing(poi)`); POI listings say nothing about actions.
`ActionResolver` (`tarav.l1.actions.views`) finds an action by its id or by
the id of the POI it follows, so `tarav context --id <id>` opens it. `tarav.l1.poi.rendering` owns named renderers for a selected
page of POIs; the default and JSON-lines renderers expose the `line` and
`record` levels. `tarav.l1.checks.poi_contract` checks that every POI Type
renders a meaningful line.
<!-- tarav.breadcrumb 0f987fcde26031c37c5760d787340675b644c752fb3410bb7e8b98183f5fd71f -->
<!-- tarav.breadcrumb 5c2663eff9561ef3a40b8394241107400cd89fa7942dee0a3037aa987699ff79 -->
<!-- tarav.breadcrumb 991c6bf77c55b2771e7572d07530f5c5b1a4abb64adddb3a2c966c06ee52f442 -->

### Atomic POI types

A POI has no `code`. Each POI Type describes exactly one situation, so the
Type alone says what was found; identity remains the Type plus the situation.
Where one check can find several related situations, each is its own class
under a family parent that is never raised (for example
`TaravSystemPromptPOI` over `TaravSystemPromptSourceUnavailable`, `Missing`,
`Duplicated` and `Stale`), so a family can still be selected with
`isinstance`. An analysis that runs outside a check says what it found with
the POI Type that states it: a Skillware finding (`tarav.l1.skw.pois.Finding`)
holds the class, and the Skillware POI Types live beside that analysis in
layer 1. The agents file of a Project is a Skillware document, so its check
raises those same Types. A Breadcrumb audit concern holds its POI Type in
the same way. There is no second name for a Type.
Reports group and filter by
Type, check or identity. Breadcrumb, Reference resolution, and Diagram
validation use atomic identified POI families. Diagram Draft schema 2 retains
POI records in Capture Receipts; a Draft of another schema is refused.
<!-- tarav.breadcrumb 0158b0cc8222cc39930e1e704ceceb0e1fb70dc4a95f5feebc6f356544fc08ac -->
<!-- tarav.breadcrumb 0d39e5ec3a25287e419935d916d0a7c9d270b87dfc428775b346dfa162fb7483 -->
<!-- tarav.breadcrumb c84140acad62e5b48e8b95892c1a749f806863a560f1bfeb08e13596ee2a9286 -->
<!-- tarav.breadcrumb 4bf190d70e6ffac17923764dc3e93dc2ba5bba11a5de09e38a7fe7fd927af7d3 -->

### Settings capability

`tarav.l1.settings` gives capabilities one declared, checked place for their
controls. A Type extends `SettingsProvider` and declares a nested pydantic
`SettingsInterface` whose fields, all with defaults, are its settings; its
objects then have a bound `.settings`. The partition is named by the declaring
Type. A Type gets another Type's partition only by listing it in
`settings_include`; neither declaration is inherited implicitly. Values arrive
as a `SettingsValues` object at construction (`settings.apply`), by
`settings.set` afterwards, or from a file loaded through the record registry
(`SettingsValues.from_path`). Unknown partitions, unknown keys and values of
the wrong type raise `SettingsError`. Each value records its origin. The
runtime's context opener adds a `settings` entry to such objects, and a
provider Type's class view has `settings-template`. Settings are controls on
how an object operates, not the data it represents, and the capability does
not regulate how a workflow uses, combines or locks the values it reads.
`AgentsMd` is the first consumer: its two prompt switches are settings stored
in the `agents` section of the Project config, while the main file and aliases
remain data.
<!-- tarav.breadcrumb 7d19421b22e7d9441b869a48ee3faca7ad6a058c4ecd8345680c1a5d14248da8 -->
<!-- tarav.breadcrumb 23058407e5e3820b5a3c4fa83c924e2c60c44a4dda63253889c6d327265e0ceb -->
