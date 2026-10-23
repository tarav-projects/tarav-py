# Tarav Python Architecture

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
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
Nothing of a loaded Record stays on the instance; `to_record()` projects
state.
<!-- tarav.breadcrumb 020e9873510e -->

Loading a Record is the record loading workflow (`tarav.l0.kernel.loading`),
the official road from a Record to an instance. One `RecordLoadingContext`
carries the `RecordLoadingConfig` and is filled step by step: read (from a
file, or the given dict), resolve the Type, check the Type reference, parse,
build. Parsing is one strict pass of the Type's `RecordInterface` over the
given dict (`Type.records.parse_record`), without copies or a comparison of
the result. The builder, `_from_record(loaded)`, receives a `LoadedRecord`:
the parsed pydantic model, not copied, and `LoadingMetadata` (by default
`source`, which only Types declaring `keeps_source`, such as `FileRecord`,
`DirectoryRecord` and Projects, keep). `TypeRegistry.load_context()` returns
the context of a failed load; the public paths raise the original error with
a note naming the step. `RecordLoadingConfig.level` selects how much parsing
checks: `none` builds without checks, `lite` and `full` are the Type's own
`Records._parse_lite` / `_parse_full`, `default` its RecordInterface; the
level never reaches the builder. Writing checks the Record the Type provides
with the same parse. Types whose whole state is their typed data use the
`TypedState` mixin, which keeps the parsed model as `typed` and writes it
back; Types whose state is a JSON document (Skillware blocks, References,
and scoring records) keep that document as their own `_fields`.
<!-- tarav.breadcrumb 7282e7b6e826 -->
<!-- tarav.breadcrumb cb24741cb86d -->
<!-- tarav.breadcrumb fa2aeb9f5a96 -->

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
registry (`runtime.contexts.register(name, hook)` / `unregister(name)`).
External contributors extend the public `ContextHook` abstract Python
interface and implement `run(cxt)`. Register explicitly constructed instances;
the instance bundles its own dependencies, configuration and state and is
reused across builds. Each hook decides whether the subject concerns it;
there is no target-class routing. Namespace class/instance hooks remain bound
methods. All hooks share the mutable result, including its options and opaque hints.
Registrations are snapshotted before construction; changes take effect on
the next build. `ObjectContext.runs` records stage entry points, elapsed
time, triple counts and errors; it does not trace individual super calls.
`ContextBuildError` retains the failed partial context and cause. Results
are runtime data, with no persistence contract.
<!-- tarav.breadcrumb d2fc001a48cd -->

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
<!-- tarav.breadcrumb f4ee4baa75c2 -->
<!-- tarav.breadcrumb 31740a0af808 -->
<!-- tarav.breadcrumb 786354609782 -->

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
  <!-- tarav.breadcrumb 6d977147b5ef -->
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
  <!-- tarav.breadcrumb 013cd3667319 -->
- `tarav.l1.context` owns the Context Explorer, the identifier resolver
  service and the Context Workflow declaration, without loading Archive or
  runtime. The runtime composes the resolvers and configures `.context()`.
- `tarav.l1.cli` projects the built argparse tree as stable `Command` Entities
  and supplies command checks. These runtime-derived objects are resolved from
  the current parser tree, not loaded as standalone retained Records.
  Its `routing` module reads global `cli-routes.json`, matches exact command
  tokens and constructs target argv. The l3 CLI adapter dispatches routes before
  local parser construction, announces the actual invocation on stderr, and
  inherits streams and cwd. Optional shell-command serialization quotes one
  argv string for consumers such as SSH; it does not introduce an SSH workflow
  or local shell execution. See `src/tarav/l1/cli/README.md` for configuration.
  <!-- tarav.breadcrumb 1b93799797f0 -->
  `tarav.l2.chatlas_typesense` consumes only stored Chatlas Normal Model files
  to project text and exact source references into an external Typesense index.
  It owns client configuration, bounded text slicing and disposable sync
  checkpoints; Typesense owns embedding generation and retrieval. Runtime
  composition injects its commands into the Chatlas registrar without reversing
  Chatlas dependencies. Host selection and SSH remain in the global CLI router.
  <!-- tarav.breadcrumb 8743c79945da -->
  <!-- tarav.breadcrumb e977371fe89a -->
  `tarav.l1.usage` retains bounded, workflow-attributed
  traces in typed Archive folders with workflow-owned daily files. Callers
  choose their trace payloads and a `UsageTrace` subtype whose owner renders
  that payload. Newly written rows carry the Type name; older untyped rows
  remain queryable until they age out. `tarav.l1.live_help` renders source and
  recent usage leads on demand, selecting exactly the Type and subject named
  by its provider rather than interpreting CLI fields. The l3 CLI adapter
  records `CommandUse` traces; command owners supply concise descriptors of
  their calls.
  <!-- tarav.breadcrumb 4c65e8ba6ee4 -->
  <!-- tarav.breadcrumb 217080a6ff2b -->
  <!-- tarav.breadcrumb 5ede35bc5676 -->
- Domain packages own their vocabulary, Records, storage, validation, and
  operations. Cross-domain imports remain acyclic.
- `tarav.l1.archive` owns the typed DOI registry. `model` defines DOI contracts,
  local/remote locators and bounded repository recognition hints. `Archive`
  uses the standard `l1.records.registry.RecordMap` partition under its Workflow
  Ship; lookup returns maintained objects without accessing external resources.
  `archive.references.DOIReference` loads a DOI declaration, while direct Git
  references can retain exact declaration editions. `archive.checks` separately
  observes local paths and bounded HTTP HEAD responses. Its Situation Chain
  raises Archive-owned actions through the System Project; unassessed locations
  never establish success. A scan checkpoint protects earlier findings when
  discovery is incomplete. Checks never repair locations or gate lookup.
<!-- tarav.breadcrumb 4f95380b66f7 -->
<!-- tarav.breadcrumb 8eadede851af -->
- `tarav.l1.archive.records` remains the independent Record Archive child.
  Archive's parent implementation does not import that child. Its existing
  storage layout, identities and consumers remain unchanged.
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
  repositories, the tarav-change IDs each repository DOI and branch had; tarav-change
  stops commits that lost some and hands stops and overrules to
  `ActionManager.register`, which registers actions without treating the
  results as a whole run of the Project's checks.
<!-- tarav.breadcrumb 547dbca67291 -->
<!-- tarav.breadcrumb c61ceaf85a21 -->
- `tarav.l1.archive.references.RepositoryReference` records a repository DOI,
  exact commit and tree, optional Change-ID and relative file path. Lookup
  returns its maintained declaration and coordinates. `tarav.l2.git.archive`
  explicitly consumes local Git: capture pins those coordinates; resolution
  prefers the original commit, otherwise accepts exactly one Change-ID candidate
  with the captured tree. Ambiguous or changed trees fail without rewriting the
  reference. The tree includes `.tarav/changes`.
- Hook installation binds repository identity independently of action ownership:
  `tarav git hooks install --repo PATH --owner-project PATH --handler tarav-change`.
  Witnesses use `git-changes/repositories/<doi>/`, with no Project-key fallback.
  `OwnedRepositorySuite` in the featured Project rediscovers bound repositories
  through Archive and rechecks their changes for the owner. Inaccessible local
  repositories prevent discovery completion from falsely closing past findings.
<!-- tarav.breadcrumb 3e2e99a09755 -->
- `tarav.l1.git.gitleaks` integrates the gitleaks binary: gitleaks detects,
  Tarav keeps each run's raw report in a depot outside the repositories and
  a repository's `GitleaksSuite` (keyed by the repository, the detector of its
  findings) yields atomic `SituationCheck`s: the binary, the scan, and one per
  reported finding, sharing one read of the history. Each is bound to its POI
  by a Situation Chain. Owner resolution reads
  Project markers, not the Project Type, and falls back to the System Project,
  whose suite checks the scanned repositories no Project owns. Staged reports
  from the hook are raised by `GitleaksStagedCheck` over `{repository, run}`,
  which runs in no Project suite, so their actions close only by hand.
<!-- tarav.breadcrumb da564609c81e -->
- `tarav.l1.skw.code` owns neutral typed document blocks, typed block-local
  objects, workflow-owned block annotations, retained content, common reading
  declarations, the abstract ReadingGraph analysis contract, and compilation.
  The compiled product is an ordinary surface; the reader does not interpret
  SKW source Records in a selected Project depot. `skw.skills` owns skill components,
  its concrete SkillReadingGraph package binding and rendering, deployment, and
  checks. ProjectReadingGraph is a Project-owned specialization point, not a
  claim that Project path declarations already exist. Trusted Type dispatch
  preserves the common source model without making skill conventions universal.
  <!-- tarav.breadcrumb f913f3d58def -->
  <!-- tarav.breadcrumb fd80d020457e -->
- Integration bundles compose independent domains without making either one
  depend on the other.
- `tarav.l3.runtime.create_runtime()` currently assembles the installed
  Workflow classes, services, Record Types, providers, hooks, and integrations.
  This is a library assembly facility, not a foundational Workflow contract.
- CLI and daemon packages translate external interaction into library calls.
  Lower layers neither import nor shell out to the umbrella CLI.

## Kernel contracts

`tarav.l1.lines.Block` is a storage-independent entity with one ordered
`contents` collection of Lines or nested Blocks. Its Record retains the mixed
order as `content_ships`; explicit binding resolves those members without
changing them. A Block's Lines confer its meaning; the base has no topic field.
`tarav.l1.lines.Line` has text and one authoring Block, whose ancestry supplies
its interpretive context. Membership does not change a Line's scope. Its Record
retains the scope Ship; explicit binding resolves that edge without changing it.
`l0.label_formats.Label` accepts the union of declared formats: citable dotted
labels such as `Kernel.Writing`, and RFC 6901 JSON Pointers such as
`/properties/text` (including the empty root). Format rules are shared by Type
names, `LabelLine` wording and PathRegistry pointer validation. Label subclasses
can restrict their format tuple. Label is an immutable value, not an identity.
`l1.label_formats.LabelFormatsWorkflow` owns this vocabulary; it depends on
Kernel while the l0 value module does not, avoiding a reverse import.
`LabelLine` validates on construction, editing and Record loading. Labels live
in `contents`; dots and slashes do not declare Block ancestry. `ReviewedLabel`
composes label syntax with Notebook support and review. Existing Type Ships and
wire Record names are preserved so Git-pinned evidence remains readable; the
old BlockTitle Python API is removed.
For adding a Block, `l2.notebook_capture.NotebookReviewFrame` binds an approved
Markdown frame (location, title, ordered bullets and token) to captured states.
It reviews displayed wording and location; it does not claim the User saw hidden
UUIDs or Types. The existing snapshot presentation remains a distinct contract.
<!-- tarav.breadcrumb 9ef1979dfc58 -->
<!-- tarav.breadcrumb 03c727288326 -->
<!-- tarav.breadcrumb 5762ccad0b95 -->

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
  <!-- tarav.breadcrumb 2b4d0ce9f52a -->
  <!-- tarav.breadcrumb 6281d4ad34d8 -->
  <!-- tarav.breadcrumb 78e31bb5c1ce -->
  <!-- tarav.breadcrumb 41d6e41fe955 -->
- `TaravEntity(TaravObject)` adds a stable `Ship` identity as class-owned
  runtime state and projects it through the Entity's Record interface.
- Every concrete Type has a class-local `class_entity()` definition. Its
  returned `TaravClass` carries a stable Type Ship; the human-readable name may
  evolve without changing identity.
- Every Object inherits a Pydantic `RecordInterface`. Classes may extend or
  deliberately replace representation ancestry.
- A Record is a projection, not the Object's runtime data model. No Object
  keeps the Record it was loaded from (`tests/test_architecture.py`).
- `obj.records.to_record()` calls the class-owned `_to_record()` hook, then
  detaches and parses the result. `Type.records.from_record()` parses input
  in the record loading workflow before calling the class-owned
  `_from_record()` builder.
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
<!-- tarav.breadcrumb 8f350694aed0 -->
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

`tarav.l1.product_mapping` maintains byte-chunk coordinates at selected Git
commits. Exact states (blob, range, fingerprint) are separate from persistent
chunk IDs and attributed continuity decisions. Editable endpoint proposals do
not advance the map; explicit confirmation validates full byte coverage and
records an immutable map in the standard Record Registry. Intermediate commits
are evidence, not mandatory checkpoints. The workflow has no Project or review
dependency. `l2.project.product_mapping.MappingManager`, selected by featured
Projects as `Mapping` / `mapping`, owns configuration and maintenance-check
integration. One stable update action follows missing or stale maps with newer
committed work; checks never initialize or advance mapping. See the workflow's
README and `tests/test_product_mapping.py` for the agent loop and contract.

File selection is Project policy: the `product_mapping.include` and `exclude`
globs in `.tarav/config.json` enter the generic mapper through the Project
manager and the runtime's CLI adapter. Confirmed maps retain their actual
selection for historical auditing. A changed selection requests a map update
and cannot silently reinterpret an earlier map.
<!-- tarav.breadcrumb 3f25b9a97a19 -->
<!-- tarav.breadcrumb 67f797198aa6 -->
<!-- tarav.breadcrumb a69fa15a978b -->

`tarav.l1.product_review` owns stable Batch identities, immutable BatchRevision
Records and separate ReviewCompletion evidence. `tarav.l2.product_review`
integrates those records with existing Product Maps and exact Chatlas Turns.
Completeness is chunk membership in at least one live batch; review currency is
independent for every batch revision, including overlapping batches. A completion
token confirms that the review happened and its outcomes were captured, without
endorsing content or closing follow-up work. Earlier revisions and their reviews
remain available. Reads never provision the workflow's Record Registry partition.
Featured `Project.Review` / `project.review` owns the configuration and suite
integration. `product_review` in `.tarav/config.json` selects enabled state and
review horizon (five days by default). Runtime registers `product-review` as a
thin CLI over the same tracker. Completeness has one repository-level Action;
each batch has an independent stable review Action. Scan checkpoints prevent
disabled or unavailable scans from falsely closing existing findings.
<!-- tarav.breadcrumb f39b6d5d518f -->
<!-- tarav.breadcrumb e8d7f87de016 -->

`Batch.subject` is a generic existing Ship UUID, pinned into each revision's
review frame. Tarav's `ClassBatch` specializes it to a class TypeShip and
`ClassReviewTracker` resolves attachments through the trusted existing Type graph.
The linked TaravClass supplies its own bases, Workflow and Context; the tracker
stores no parallel class hierarchy. The Project and installed CLI select this
class specialization; generic Python consumers keep arbitrary subject UUIDs.
<!-- tarav.breadcrumb 2511fc0604d4 -->
<!-- tarav.breadcrumb 880b94d167f6 -->

`product_review.max_chunks` bounds a batch to eight chunks by default. Create,
revise and complete enforce the current limit. A configuration reduction
reports oversized saved batches through their existing review Action without
rewriting membership or dropping historical reviews.
<!-- tarav.breadcrumb 4b4fcb2c56e1 -->

`tarav.l1.attic` owns cheap conservation of opaque displaced material.
`AtticWorkflow` is an explicit Archive child, separate from Artifact
registration. `Attic` and `Deposit` are path handlers with ordinary Tarav
Records; `deposit.json` is a separate, self-declared orientation format, and
its UUID does not identify an Archive Artifact or promise an available Entity.
The identified `AtticSuite` reads immediate deposit directories and manifests
only. Situation Chains report listing failure, missing/unreadable/invalid
metadata, and duplicate UUID declarations through Attic-owned resolution
actions. Format validation never inspects, traverses, hashes, or requires the
existence of retained contents, verifies depositor claims, or repairs metadata.
`TaravSystemProject` composes this suite; incomplete discovery cannot establish
that previously reported deposit situations disappeared. Agents perform
depositing and recovery under `tarav-pkg --attic`; no payload operation is
implicit in workflow discovery or checking.
<!-- tarav.breadcrumb c1e8d482d837 -->

The featured `l2.project.Project.attic()` selects the Project-relative `_ATTIC`
depot or the `attic.path` override in `.tarav/config.json`. Its Project checks
compose that depot's existing suite lazily; malformed configuration leaves the
Attic scan incomplete while other checks continue. Root Projects aggregate their
own and their children's Attics through ordinary check composition. Minimal
`l1.project.TaravProject` does not import Attic, and Attic has no dependency on
Project. Missing unused depots stay absent. The System Project additionally
checks the general Tarav Attic, independently of its local one.
<!-- tarav.breadcrumb 6f53edfca5e7 -->

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
configures a Project (`tarav.l1.project.config`: `agents`, `skills`),
each validated by its owner's model and registered by the
runtime. `ProjectFilesCheck` (`tarav.l1.project.files`), in every Project's
suite, reports undeclared fields, a missing harness or environment, a
`harness.type` that is not the Record's Type, and config sections no workflow
owns or that their owner rejects. Run never installs or selects a fallback
interpreter.
<!-- tarav.breadcrumb 8ffca46a4e97 -->
<!-- tarav.breadcrumb 806fd99acd25 -->
<!-- tarav.breadcrumb bc39462931a9 -->

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
<!-- tarav.breadcrumb 91260ffaa49d -->
<!-- tarav.breadcrumb f4f493ec99d3 -->

`TaravProject` is a `CheckProvider` (`tarav.l1.checks`) whose base suite
checks its Skillware-produced agents file through `project.agents.agents_md`.
Subtypes compose that suite with `super().suite()` in their `Checks` namespace;
`project.checks.run()` executes it and reports typed bootstrap POIs.
<!-- tarav.breadcrumb b7370472b54d -->
<!-- tarav.breadcrumb 8fa3ca276796 -->
<!-- tarav.breadcrumb f6132fabb003 -->
<!-- tarav.breadcrumb 0bd03575af28 -->

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
completed; a nested suite with an identity answers for itself.

A dynamic producer declares `checkpoint_types={name: (CheckType, ...)}`
on its suite and yields `SuiteCheckpoint(name)` after its scan. The run records
that named checkpoint and attaches its declaration to results of the certified
Check Types. For a POI Action raised by one of those
results, absence is conclusive only if a later run reaches the same checkpoint
and its Checks of that Type completed. A branch that skips the scan leaves the
checkpoint unreached even when the suite itself ends; filtering that Check Type
also prevents a `gone` conclusion. Other Check Types after the checkpoint do
not affect that local completion claim.
<!-- tarav.breadcrumb 8aefbfde8e68 -->

`walk()` gives each result with the identified suites above it. A suite may declare the
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
<!-- tarav.breadcrumb 79bfd183bfe3 -->

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
<!-- tarav.breadcrumb e8ab00134f9f -->
<!-- tarav.breadcrumb b79a8bbf9c2e -->

`tarav.l1.chatlas.sessions` exposes indexed conversations through an
`ExplorerFolder`: entries construct a portable `ChatSession` without capture or
normalization. Native-ID keys require unambiguous provider/instance scope;
an explicit identity-hash view handles collisions. `ChatSession.model()` delegates
to the existing Normal Model reader and cache. The depot root is runtime
configuration, not retained Session identity or part of its portable Record.

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

Cache freshness depends only on the raw data. The Session Index row carries
`raw_version`, a hash of its transcript sources' paths, sizes and modification
times (`index_writer.raw_version`). `normal_model_cache.NormalModelCache`
records the version each part was built from (`main` and the four
collections) and reports every part as present, fresh or stale without
building; its `model()` returns what is stored. The safe path,
`provide_normal_model_reader(parts=…)` and `ChatSession.model(parts=…)`,
builds when a requested part is missing or stale. Code changes do not
invalidate the cache; after a normalizer change, maintainers delete the
derived `normal-model/` directories.
<!-- tarav.breadcrumb 704f9f515ebc -->
<!-- tarav.breadcrumb 0dbcd88f7c41 -->

`tarav.l1.chatlas.search` is Chatlas's engine for the Search workflow, which
knows nothing of Chatlas. A `ChatlasSearchQuery` names its target (turns by
default, or messages), how text matches (`text` as a phrase of words, `match`
as an FTS5 expression, `contains` as a substring), side, and session filters
(provider, project path prefix, activity window). The engine reads the Normal
Models index as it is, newest session first, and yields `ChatlasSearchHit`s
carrying the session's facts and the turn or message as the index holds them;
full records stay in the JSON cache. Turn start times need events and are
opt-in on `ChatlasQuery` (`times`). The runtime registers the engine in
`runtime.search` as `chatlas`.
<!-- tarav.breadcrumb 292f5d687a12 -->
<!-- tarav.breadcrumb f8efe0be8a26 -->

Chatlas derives three stages from the native provider folders: capture (raw,
`chatlas_update`), the JSON Normal Model cache (`NormalModelCache`), and the
Normal Models index, a SQLite database at `index/normal-models.sqlite`
(`tarav.l1.chatlas.normal_models_index.NormalModelsIndex`) holding sessions,
messages, Turns and a full-text table, but no JSON records. Each stage records
the version of its input: the cache the `raw_version` of each part, the index
the cache version of each part it consumed; a stage is fresh while those
match. `NormalModelsIndex.query` and `rows` run read-only SQL for any
consumer. `tarav.l1.chatlas.stages.ChatlasStages` lets a consumer control the
pipeline: select sessions by Session Index facts, read each stage's standing
(missing, stale, fresh), and update chosen stages with a policy (`missing`,
`stale`, `all`). Nothing runs implicitly; search runs stages only when its
`capture`, `cache` or `index` flags ask.
<!-- tarav.breadcrumb b8e7529c17e6 -->
<!-- tarav.breadcrumb d98c94ab0799 -->
<!-- tarav.breadcrumb ad19e746fc5d -->

`tarav.l1.programs` owns `ProgramsWorkflow`, `TaravProgram(TaravEntity)`,
NodeActions, EdgeActions, Transition declarations and the durable ProgramRun.
The Program defines a graph in trusted Project code and selects checks through
`checks(run, occurrence, operation=...)` for enter/status/complete. Check
ownership and meaning are Program policy; the runner does not impose reuse of
node status checks for departure or arrival. Node/edge Types are ordinary
Actions outside operator StepRunner. There is no explicit State Type.
<!-- tarav.breadcrumb 3151d77692a0 -->
<!-- tarav.breadcrumb 00848755a7fe -->
<!-- tarav.breadcrumb 441ef8f81951 -->
<!-- tarav.breadcrumb 7957c85143f7 -->

`tarav.l2.project.programs` retains ProjectProgram and binds ProgramsManager to
the featured `Project.programs`. It selects registered Program Types owned by
the Project; `tarav program` uses the existing Project harness, without a script
loader. ProgramRun is authoritative in the external Programs Registry partition;
its retained ActionRun snapshots project the overall execution and child actions
into the Actions partition. Explicit recovery repairs an interrupted projection,
without advancing or reissuing a token. ProgramRun retains an active collection
of Action occurrences with their individual tokens. Node→edge and edge→node
movement each consume one occurrence and open another; graph permission and
current-token validation are mandatory, including on cycles. Multiple initial
occurrences progress independently. Terminal NodeActions close explicitly;
closing the last completes the overall execution. `tarav status --program-token`
checks the selected active occurrence, with occurrence-scoped checkpoints. An
unselected active context is not resolved; normal status retires warnings for
closed occurrences using recorded closure facts. Current trusted class code
defines checks; runs do not snapshot code or claim exclusive token access.
<!-- tarav.breadcrumb f5179cb980d0 -->
<!-- tarav.breadcrumb c40f6fecb83c -->
<!-- tarav.breadcrumb 77881a7792d4 -->

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
<!-- tarav.breadcrumb 570734881cad -->
<!-- tarav.breadcrumb 00b84f42127c -->
Actions and their runs keep
their Records in their own Record Registry partitions, outside any Project.
Action Types are made startable by explicit `register_action()`; the runtime
registers them. `tarav.l1.actions.pois` holds what follows a POI:
`ActionablePOI`, the `POIResolutionAction` with the closing paths `gone`
and `blessed`, and what that Type does with a run of its Project's checks
(`on_checks`). `tarav.l1.project.actions.ActionManager`, reached as
`project.actions`, owns the Project integration and status loop. Its `status()`
runs the Project checks, hands their results to its actions, and visits each
member Project through that member's selected action manager. `project.status()`
is the convenience entry point to this manager-owned loop. A POI-resolution Action with the `gone` closing path closes
only when the suite that detected its POI, or an identified ancestor of that
suite, ran conclusively without it. A standalone identified sibling suite
has no authority over the Action. An unscoped Project suite remains
authoritative over children it no longer yields. When the Action event records
a checkpoint, the matching suite must reach it for the relevant Check Type;
an absent POI in a skipped dynamic scan is `not run`, not `gone`.
<!-- tarav.breadcrumb ad451ba0f3a9 -->

While `<project>/.tarav/tests/` exists, the l2 `Project` adds
`TestFixturesSuite` (`tarav.l2.tests.actions`): its files raise test POIs
whose actions are real actions of the Project, for trying the action loop on
the live path. Each status entry of the tape holds the state of the
repositories the suites above the action's checks declare, and per
repository the first clean state after it is a `Clean` entry; `tarav status`
names the repositories that were not clean. The instance of a POI's action
is derived from the POI's identity; its tape holds its status history and
every other change is in the registry's Git history. Checks do not import Actions and
give the owner no meaning; a run that no owned suite produced is momentary
and resolves nothing. Program executions and their active NodeActions/EdgeActions use
the same Action registry while the Program runner owns their checked lifecycle.
<!-- tarav.breadcrumb 58b3f302d6fe -->
<!-- tarav.breadcrumb 65f4b92f79c2 -->
<!-- tarav.breadcrumb 30efa0fe92a4 -->
<!-- tarav.breadcrumb 929afad70096 -->
<!-- tarav.breadcrumb 8f83b152a5ae -->
<!-- tarav.breadcrumb 79c4b2ba1ae6 -->
<!-- tarav.breadcrumb 9ee4d9dcc84f -->
<!-- tarav.breadcrumb 2d9d5a81415b -->
<!-- tarav.breadcrumb 2955673512f9 -->
<!-- tarav.breadcrumb 603b695bea90 -->

| Package | Architectural responsibility |
| --- | --- |
| `agent` | AgentsWorkflow. Provider-neutral agent, account, session, and monitoring behavior; concrete providers (Claude Code, Codex, Copilot) live below `agent.providers`. `agent.current_session` names the running agent's session through the adapters that inherit `ReportsCurrentSession`. Its operational logs under `~/.tarav/agent/` carry `tarav.agent.*` classes; the usage registry still reads records written as `agentos.agent.usage-record`. |
| `l2.agent_setup` | Integration of `agent` with Checks and Actions: `AgentSetup` reports monitor-config loading, profile loading, and each agent's `profile_check()` checkpoints as POIs under the Agents workflow. It sits in l2 because `actions` already depends on `agent.current_session`. `TaravSystemProject` composes its suite. |
| `archive` | Typed DOI resource declarations, maintained locators and recognition hints, registry references and independent locator checks. |
| `archive.records` | Optional typed Folder and List Archives for storing class-owned Records at explicit roots; the stored Type keeps its domain meaning. |
| `records` | TaravRecords workflow: contributed Record-source navigation, on-demand Entity view, and optional standard keyed RecordRegistry partitions. |
| `search` | SearchWorkflow owns typed incremental queries and a registry-backed meta engine. SearchEngine Types contribute a bound `.search` namespace; the runtime holds one SearchService per composition. Engine registration does not imply storing queries or hits. |
<!-- tarav.breadcrumb f973b051579a -->
<!-- tarav.breadcrumb 4597f1786f7c -->
<!-- tarav.breadcrumb 9b87f84163c1 -->
| `l1.context`, `l3.context` | The Context Workflow: ObjectContext construction, ordered hooks, the Explorer and resolvers, and the `tarav context` command. |
| `l1.neighborhood` | NeighborhoodWorkflow: the objects an object is shown with, for documentation only. A class names its neighbors as `NEIGHBOR` triples in its context hook; `neighborhood(obj)` is the object itself, then those neighbors. By default it is just the object, which adds no triple. Nothing decides anything from it; where a neighbor's Type lives is read by following its Type's `workflow` link, not stored. |
| `references` | Shared typed locator, check, hints, and resolution mechanics. |
| `chatlas` | Provider-native chat capture, Session Index, provider-neutral Normal Model, bounded Query, and rendering. |
| `breadcrumbs` | Opaque Product.Surface anchors, position observations, attachment storage, and generic annotation transactions. |
| `breadcrumb_workflows` | Independent integrations between Breadcrumbs and producer domains such as Chatlas. |
| `l1.git`, `l2.git`, `l3.git` | The Git Workflow spans repository mechanics, commit-message Breadcrumb integration, and installed CLI composition. |
| `l1.lines` | LinesWorkflow owns identified natural-language Lines and recursive typed Blocks. Each Line has one authoring Block; its direct Block and parent chain bound interpretation. A Block's Lines confer its meaning; its single contents collection preserves mixed Line/Block order. The Python class supplies Block type; external graph relationships supply uses such as specification. |
| `l1.notebook`, `l2.notebook`, `l2.project.notebook` | The l1 Notebook is storage; the l2 Notebook is a typed Block integrating capture, evidence and checks. Project.notebook() returns its actual ProjectBlock. New Project notebooks are nested under TaravNotebook; explicit create seeds the selected sibling layout once. Reads preserve existing records and parent links. |
| `assertions` | AssertionsWorkflow owns the shallow TaravAssertion root and Assertable capability. The base imposes no case-production method. |
| `scoring` | ScoringWorkflow owns the identified, case-producing Assertion subtype, closed AssessmentCase contract, shallow Score root, and retained evaluation mechanics. Scoring Records are entities with explicit Context reference edges. |
| `scoring.ranking` | RankingWorkflow is a Scoring subtype and child workflow. It owns pairwise cases, singleton Tribunal entities, pairwise operations and Checks, and ephemeral RankingScore results. |
| `poi` | POIWorkflow owns neutral, identified, and notification POI foundations plus shared collection and notification delivery. Identified POIs derive identity from their concrete Type Ship and explicit producer-supplied situation; collector-local indexes address repeated emissions. Producing workflows own their concrete POI types. |
| `actions` | ActionsWorkflow keeps typed Actions and one record per action in its Record Registry partition, outside any Project. `StepAction` has named exits taken by an operator, the loop or a Project; each exit names the `Closing` record Type it leaves on the run's tape, and that Type's `reopens` says whether the POI raised again reopens the action (gone: yes; blessed: no). `tarav.l1.actions.pois` is what follows a POI: an `ActionablePOI` (the capability lives in `tarav.l1.poi.actionable` and is extended by `CheckPOI`) spins the Action Type its `action` names, a `POIResolutionAction` (exit `gone`) or a `BlessableResolution` (adds `blessed`); its instance is derived from the Action Type and the POI's identity. A POI Type that may be blessed, or one in a chain, names its own Action Type. Check code carries no Project: `project.checks` only runs checks. `ActionManager` (`project.actions`, `tarav.l1.project.actions`) receives completed check results: `start(run)` registers under the Project the action of each POI not registered there (a new one is built by its Type, one of another Project moves), `refresh(run)` hands the results to every registered action, open or closed, and `update(run)` does both and records them. `Action.on_checks(run, update)` is what a Type does with them; the base ignores them. `POIResolutionAction.on_checks` marks the situation present and reopens when the closing says so. An action keeps the identified suites above the check that raised its POI (`event.suites`); when the POI is not raised, the nearest of them that is in the run decides. If none ran, the suite handed over decides only when it is unscoped or an identified ancestor recorded in `event.suites`; a sibling suite means `not run`. The deciding suite is conclusive for the POI's Type of check: the situation is absent and an open action closes as `gone`. Otherwise the action stays, with the situation `check failed` when a check failed and `not run` when the suite was left out. A removed check, a removed suite and a check that no longer raises anything are the same case: a detector that ran no longer reports it. `project.actions.status()` (`ProjectStatus`) owns the checks-to-actions loop; `project.status()` delegates to it; `tarav status` runs it. A run that no Project hands over is momentary; `tarav skw skills check` records no action. Status is three axes, `axes(run)`: the situation (`present`, `absent`, `check failed`), the action, and the closing. `blessed` is an operator's exit with a reason from the Operator Context, offered only by `BlessableResolution` Action Types; closing by an exit the Type lacks is an `ActionError`. `tarav status` is settled when every check that ran completed and no action is open: it reads only actions. A Project sees the actions of the Projects it lists as children (`tarav.l1.project.scope.project_scope`, read from the markers): `project.actions.list()` and `tarav action list --project` include them, each action still naming the Project it belongs to, and `own=True` or `--own` leaves them out. Checks never write to the registry. The resolver that finds an action by id lives in `actions.views`. |
| `decisions` | DecisionsWorkflow owns the shared attributed Decision contract and prescribes no concrete subtype of its own; consuming workflows define theirs. It owns no storage. The common actor field is exposed as `decider`; subtype schemas keep their own fields and optional POI links. l2 builds an inspectable main Assertion for generic Decisions; assessment cases and attention policy are not yet prescribed. A Blessing is not a Decision: it is the closing record of an action. |
| `blessings` | BlessingsWorkflow owns the `Blessing`: the closing record of a POI action closed although its situation still exists, with the actor, the reason, the offered support and the POI as it stood. It is one closing path of a Situation Chain's action, not a general model. The Type is defined in `l1.actions.blessing`, beside the Actions code it is built from, with `BlessingInput` and the test of that exit; `BlessableResolution` in `l1.actions.pois` is the Action family that offers it. A Blessing is Assertable; its Assertion and read-only score providers are composed in runtime from the l2 Blessings integration. A blessed POI is still raised and reported; its action stays closed. A blessing accepts a situation: the situation holds every fact that makes the problem what it is, so when one of them changes the check raises a different POI, which the blessing does not cover. Details carry no meaning for identity or blessings. There is no separate blessing store. |
| `checks` | Independently runnable bound Checks, CheckPOIs coupled to their Check objects, optional subject providers, and result snapshots. SituationChecks evaluate a detached Situation, created by their caller, and use that same snapshot as the POI acceptance scope. Execution completion and a POI's failure signal are separate. `chains.SituationChain` models Situation → Check → POI → Action → Closing as one thing: it names its atomic SituationCheck and POI Types and binds them (`chain`); a chain's Check raises only its POIs; an instance is one situation, identified, like its objects, by its Type and that situation. A chain's Types are named `<chain>.<extras>.<kind>` (`chain_type_name`, the kind one of `CHAIN_KINDS`: Chain, Check, POI, Action); a POI and the Action it opens share their problem as the extra, and defining a chain refuses other names. A Suite finds the situations and runs their Checks. POI Types name their Action Types, so chains do not import Actions. |
| `l2.tests` | TestsWorkflow is a shallow parent in `tests.workflow`. `tests.navigation` owns disposable Context/Archive fixtures; `tests.scoring` owns a fixed synthetic User chat, ten Lines Blocks, fifty scoped candidate Lines, a Line-support Assertion/Case, and a dedicated ranking Tribunal. The scenario closes cases from the synthetic evidence; tests exercise judgment and derived scores without a live agent. |
<!-- tarav.breadcrumb b750afdefcc3 -->
<!-- tarav.breadcrumb 28df20317b52 -->
| `skw`, `skw.code`, `skw.skills` | Skillware umbrella, common source/compilation and ReadingGraph contract, and deployable-skill specialization. Blocks are Entities with Ships and separate labels; source blocks own typed reading declarations. SkillReadingGraph exposes route facts, while skill-owned Checks turn those facts into POIs. A skill's depot lives in the Project that builds it, `.tarav/skillware/skills/<name>/`, and names the skill folder (`product`) and its `skill_id`; `load_skill(folder)` finds it through the nearest Project marker. Sources are named relative to their depot, products relative to the skill folder; skw POIs name a skill by its UUID and an agents file by its Project's. The package analysis is a set of Situation Chains (`l2.skw.chains`): `SkwSkillSuite` loads a skill once (`SkillLoad`) and runs one atomic Check per skill, source, product, block, consumer file, link and dependency, each with the situation it built, and per node, declaration, source-block binding, requirement, reading path and prose link of the reading graph: `ReadingAnalysis` runs the one traversal reachability and paths need, and each reading Check reads its subject's part (a missing context keeps the path that misses it); the rules stay in the l1 analysis, split per subject (`Document.block_findings`, `source_findings`, the product reading), and `lint()` composes them. Chain Types are named `Tarav.SKW.<chain>.<extras>.<kind>`; every Skillware POI Type names its own Action Type, its name ending in `Action` instead of `POI` (`l2.skw.pois`). |
| `surfaces` | SurfacesWorkflow owns MarkdownNormalModel, its strict LineMarkdownModel subtype, and PythonNormalModel TaravObjects. Their from_text/from_path methods parse native syntax; Records preserve parsed structures without reparsing. LineMarkdownModel is a floor for owned formats: it raises at the first dialect violation instead of returning a partial model. Consumers assign domain meaning. |
| `wiki` | Folder-based Markdown Wiki and WikiNote objects, parsing through surfaces, and Wiki-scoped Git closure. No Project dependency. |
| `project` | ProjectWorkflow owns minimal TaravProject and featured Project. Existing project_id is the Ship identity; discovered location stays outside the portable marker. Every Project has checked agents-file and skill-availability bootstrap under `project.agents`; its agents-file Skillware source is `.tarav/skillware/src/AGENTS.skw.json`. Skill checks search Project and home `.agents/skills` by declared `SKILL.md` name, require `tarav-pkg` and the Project's `agents.package_skill`, and verify `.claude/skills` resolves to the same directory at both scopes. |
<!-- tarav.breadcrumb d3ca6d771b34 -->
| `project.wiki` | The featured Project exposes `project.docs.wiki`; the minimal base does not import this integration. |
| `workspaces` | Identified manifest-backed working folders under the Tarav data root. Exact worktree commits and retained file seeds define reproducible setup; a separate setup Record retains observed hashes and allocated branches. Workspace checks report POIs. The l1 workflow calls l1 Git for every worktree operation; l2 Project offers an optional view over the independent depot. |
<!-- tarav.breadcrumb 28d74cb87df8 -->
| `skills` | SkillsWorkflow: the abstract base Skill type, `TaravSkill` (a folder a harness loads through its `SKILL.md`; entrypoint, frontmatter, name, description), folder-backed `FolderSkill`, and skill discovery. Independent of Projects. Every kind of skill subtypes `TaravSkill`; `skw.skills`' `SkwSkill`, with its blocks, reading relationships and checks, is the one other workflows commonly use. `SkillMarker` is `.tarav/skill.json`, the UUID a skill keeps in its folder so every copy carries it; a skill is not a Project and belongs to the one whose depot builds it. |
<!-- tarav.breadcrumb 653af09b9603 -->
| `project.skills` | How a Project selects skills from its sources and profiles, installs them into the folders its agents read, and reports their status (`tarav project skills`). |
<!-- tarav.breadcrumb 80841d343480 -->
| `hooks`, `daemon` | Hook validation and dispatch, plus daemon-owned delivery adapters. |
| `stdlib` | Small reusable library and CLI primitives. |
<!-- tarav.breadcrumb 5390bce98b91 -->

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

`Project.docs.wiki` returns the conventional notes/wiki folder without
creating data.
<!-- tarav.breadcrumb a4389802948e -->

## Integration invariants

The `l1.lines` primitives and their local Context hooks depend only on Kernel.
Their `Line.scope_ship`
names a Block, not a general entity; Block parentage is the bounded authoring
context. The former l2 Diagram application, including Models, Drafts, Views,
and its CLI, is retired. Git history retains that implementation. The new Lines
workflow supplies authoring primitives and their graph contributions; relationships between Blocks and
other Tarav objects belong to the broader Diagram.
<!-- tarav.breadcrumb 81853af57d52 -->

Notebook storage imports Lines and the general RecordMap mechanics; it does
not import Project. The Project association lives in l2. Its default root Ship
derives from the Project Ship, while typed branch Ships derive from the root
and their Types. These rules locate the initial objects; later reads load the
stored membership and text without regeneration. Discussion, Model, and Archive
are typed Notebook Blocks with explanatory Lines and reusable operations.
`l1.notebook.blocks.NotebookBlock` carries only transient storage binding;
storage binds it during loading without importing the l2 integrations.
`l2.notebook.Notebook` is a CheckProvider whose local suite is composed with
each nearest nested Notebook's suite, so subtype checks run and Lines are
checked once. The Project composes an access suite and its Notebook's checks;
it retains status/action ownership. Existing TypeShips and serialized block
Type names remain stable; no read-time data migration changes old ancestry.
New Project notebooks can share the deterministic TaravNotebook root.
`Notebook.draft()` stages add/amend capture through `l2.notebook_draft` without
writing candidate content. Its temporary JSON plan retains operations, source
Line/context baselines and an exact token presentation. Reviewed landing
restores against fresh data, checks the actual approval and full presentation,
then uses existing support/review records. Independent child-Block additions
can merge; changed authoring context requires a new proposal. Amendments retain
Ship and concrete Type. This is bounded optimistic preflight, not a database
transaction, retained draft registry, removal workflow or lineage mechanism.
<!-- tarav.breadcrumb 6724f2d70994 -->
<!-- tarav.breadcrumb 2baf3744e64b -->
<!-- tarav.breadcrumb 6b8104da86a8 -->
<!-- tarav.breadcrumb 785a4a323c9c -->

Lines contribute `urn:tarav:lines:` text, scope, parent and containment predicates,
plus RDF ordinal membership edges for mixed order. The optional
`l1.lines.context.explore(root)` adapter uses Context to collect a complete
subtree and ancestor direct Lines. It keeps the selected root in focus and
does not open sibling payloads. `l2.notebook_context.NotebookContext` selects the
Project's ModelBlock by default; explicit branches or Block Ships broaden that
scope. Queries run through the existing ContextExplorer, with no Notebook
text-search engine or retained session View. The runtime's Notebook resolver
opens stored Block/Line Ships, and its Project hook exposes existing Notebook
roots without provisioning. `l3.notebook` owns the read-only `tarav notebook`
ls/read/query CLI. Notebook storage remains independent of these consumers.
<!-- tarav.breadcrumb 4ada1653d6c0 -->
<!-- tarav.breadcrumb 1d76273569fc -->

`l1.grounding` retains subject References and attributed SupportSets;
SubjectState snapshots are computed in memory for comparison and presentation.
`l2.notebook_references.NotebookStateReference` pins a Line through a repository
DOI, exact commit/tree, optional Change-ID and record path. The explicit Git
consumer accepts a recovered commit only when the repository resolver verifies
one matching tree. It reconstructs the Line's bounded context from that commit,
without embedding text or ancestor snapshots in support and review Records.
`l1.review` retains tokenized VerbatimReview records independently of support.
`l1.notebook.evidence` specializes Lines and Blocks with explicit support and
review requirements. Base Lines remain mutable, identified authoring primitives.
`Block.walk()` supplies ordered structural traversal to navigation and checks.
<!-- tarav.breadcrumb 71b926552258 -->

`l2.notebook_capture.NotebookCapture` captures and inspects evidence through
existing Chatlas Turn references and append-only inserts in the Grounding and
Review Record Registry partitions. Its explicit create initializes only those
partitions. Explicit checkpoints bind/install tarav-change on these repositories,
owned by the System Project unless an owner is selected. Capture commits Notebook
state before linking evidence; support/review writes then commit their evidence
and the Notebook links. Repository metadata and records are selected explicitly,
preserving unrelated staged paths. Old commits without Change-IDs retain exact
commit/tree coordinates. No legacy state-reference reader is retained.
Reads do not commit or provision. Subject fingerprints include wording, concrete Types and direct
Lines of authoring ancestors, excluding evidence attachments. Historical claims
remain retained after edits; they do not approve the current state. Protocol
verification checks destination, operation, bounded before/after wording,
proposal/approval roles, order and explicit token approval. Whitespace wrapping
is normalized; semantic equivalence is not inferred. Proposals include target
state digests, so unchanged words cannot be approved under a different context
by attaching an older proposal later.
<!-- tarav.breadcrumb edc13a28dd56 -->

`l2.notebook_checks` supplies atomic support/review/access Situation Chains and
NotebookEvidenceSuite over one Notebook's local Lines. The featured Notebook
recurses into child Notebook suites; `l2.project.notebook_checks` handles
access and composes them into Project checks. Types and ancestry
can require support and review; inheritance cannot silently weaken either.
Missing or invalid evidence produces POIs after recording. Unavailable evidence
leaves the check incomplete, so prior actions are not closed without a conclusive
run. Existing untyped Archive material and seed Lines are not retrofitted.
This integration imports neither scoring nor runtime and supplies no semantic
Assertion evaluator, claim propagation or LineTrace implementation.

The Notebook's capture/support methods accept one root Reference and its
neighborhood, producing one SupportMember per independent SupportSet. Multiple
sets may support the same Line. The existing evidence checker requires a User
turn root for conversational support and permits Agent turns as neighbors;
capture retains invalid/missing evidence for later checks. Notebook operations
are bounded to their subtree and delegate to NotebookCapture; review still
requires actual proposal/approval evidence in chat. Notebook subtypes can
specialize their evidence service and Checks namespace. Storage remains the
separate l1 transport, and its record contains only its location.
<!-- tarav.breadcrumb 9bb1e4364b2b -->
<!-- tarav.breadcrumb f897176d2e28 -->

Assertions owns the common Assertable and shallow TaravAssertion contracts.
Scoring's `assertions` module supplies its identified, case-producing Assertion
subtype and the AssessmentCase contract without
importing consumer workflows. A case is a
JSON snapshot of its claim, question, and supplied material; the scorer does
not acquire source handles or search for further evidence. Unsupported case
Types and supported Types lacking sufficient material fail distinctly. The
runtime registers concrete case Types for Record round-trips. The retired Line
grounding adapter no longer composes a case from Diagram storage.
<!-- tarav.breadcrumb 9d28b8a71a32 -->

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
<!-- tarav.breadcrumb 1d37ba887642 -->
<!-- tarav.breadcrumb afa385a96aea -->

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
<!-- tarav.breadcrumb 903d50edc16c -->
<!-- tarav.breadcrumb b6bdfb5131dd -->

`l2.blessings.attention` composes the current POI collector, the POI actions
and l2 ScoringRepository into a separate, pageable due/deferred view. It does
not change check output or any record. A POI whose action is blessed is
deferred from the time of its Blessing, longer when the Blessing offers
support and its acceptance is well scored. A changed situation has a new POI
identity; a mechanically absent POI is never scheduled. The derived score
remains relative rather than a truth scalar.
<!-- tarav.breadcrumb d6e3d0827437 -->
<!-- tarav.breadcrumb dc5c60cd5793 -->

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
- Breadcrumbs have embedded and external placement in the same registry.
  Embedded placement uses native Markdown/Python/TypeScript/TOML comments.
  External observations retain a file, line and exact single-line fragment;
  reads check the latest line, then search that file, exposing ambiguity or a
  missing external anchor without deleting identity or attachments. Maintainers
  explicitly append replacement locations. JSON is read-only for the workflow;
  its former `tarav.breadcrumbs` metadata convention remains inspectable.
  <!-- tarav.breadcrumb ecfe9c89b344 -->
  <!-- tarav.breadcrumb 2a5832c3c7cc -->
- Chatlas retains distinct native payloads when rollouts reuse an Event address;
  exact copies merge observations. Dependent Messages and Contexts follow their
  own payload variant. Cited Turns are retained with hash-checked Messages,
  Events and raw-source observations in the Chatlas Record Registry partition.
  References identify the same exact coordinates and explicitly report a
  `retained-snapshot` representation when resolved there. Replaceable current
  Normal Models and immutable cited evidence have separate roles.
  <!-- tarav.breadcrumb 7a57d9033198 -->
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

## Project integration managers

Project Classes select bound `Actions`, `Checks`, `Skw` and `Records` manager
classes, exposed as `project.actions`, `project.checks`, `project.skw` and
`project.records`. Derived Project Classes extend those classes through ordinary
Python inheritance. Managers own integration behavior, including loops and hooks;
workflow primitives retain their own mechanics and semantics. Managers are bound
namespaces, not additional retained Entities or Workflow identities.
<!-- tarav.breadcrumb ad750503c968 -->
<!-- tarav.breadcrumb 21af60c53d08 -->
<!-- tarav.breadcrumb c86857d992b1 -->

The base managers live in `l1.project`. `ChecksManager` composes and runs checks
without updating actions. `ActionManager` owns registration, updates and the
status loop, preserving POI action identity and conclusive-detector closing.
`RecordsManager` retains the existing class/object Record projection and loading
API while selecting type dispatch and standard Record storage for integrations.
It does not provision storage on access. `SkwManager` binds source Documents;
its `l2.project.skw` specialization discovers skill depots and contributes their
checks. The featured Project selects that specialization; DocsProject composes
its checks through its Checks manager. Higher-layer integration stays above the
independent workflow mechanics. See `tests/test_project_managers.py` for a
Project subtype overriding all four managers and its status loop.

## Sources of truth

### Project Types and PathRegistry

`TaravObject.view_schemas()` supplies default Record and partial instance schema
Views through declaration-only introspection in `l0.kernel.json_views`; Types
may override it. Record schemas come from RecordInterface, with the separate
Type-dispatch field exposed. Instance projection never invokes constructors,
property getters or evaluates annotation strings.

`Project.Types` selects `l1.project.types.TypesManager`; `project.types.all()`
filters already registered classes by their defining source under the Project
root by default. Overrides own alternative membership policy. Dispatch remains
`project.records.types`, independent of Project ownership.

`l1.path_registry` owns JSONView, PathEntry and PathRegistry.
Paths are JSON Pointers into a View value, with Ships maintained independently
of path spelling. Other workflows reference these Ships and own their associations
and documentation. The registry stores no attachments or documentation Types.
Explicit enrollment,
reassignment, addition, retirement and acceptance are distinct from computation.
`l2.project.paths.PathsManager`, selected as `Project.Paths`, keeps the normal
typed registry Record in `.tarav/paths.json` and composes read-only checks into
Project status. Absence never provisions; unavailable scans never certify old
findings gone. Git supplies history. See `l1/path_registry/README.md` for usage.
<!-- tarav.breadcrumb 7576042d6588 -->
<!-- tarav.breadcrumb 4f32bc5b3178 -->

`l2.notebook.PathNotebook` is a child of an existing ProjectBlock, selected by
`project.notebook().paths` or `project.paths.notebook()`. Explicit Project
Notebook creation adds that child, including to an existing edited layout;
selection never writes. `l1.notebook.paths.SchemaBlock` and `PathBlock` retain
schema/path Ships and ordinary Lines. Schema, root-path and parent-path Blocks
provide the inherited context for a subpath note. Notes use existing Notebook
storage and capture; PathRegistry owns no Lines or attachments. Current-path
access reports stale ancestry after a path move instead of silently reparenting.
See `l1/notebook/PATHS.md` for the explicit add/save/read API.
<!-- tarav.breadcrumb 2fefc98aa307 -->

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
<!-- tarav.breadcrumb d85bcbec96c2 -->
<!-- tarav.breadcrumb fb964adb1a2f -->

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
<!-- tarav.breadcrumb 04da500bc542 -->
<!-- tarav.breadcrumb 649ec18a1017 -->

### Context queries; the POI is a flag

`tarav context --id <identifier> [--json]` is the shell door to the same
Explorer that scripts open with `obj.context()`: it prints the subject and
the edges at it. `tarav.l1.context.query` owns the typed `ContextQuery` (an
identity query by default) and a `ContextQueryService` whose resolvers are
Search engines; the runtime composes the installed ones. One match opens,
several are listed, and a unique prefix is enough. `--view` is kept only to
fail: named views, such as the former object group, are not implemented in
the graph model and come back as queries when needed.
<!-- tarav.breadcrumb 2c617b4d656b -->

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
breadcrumbs commands) is how a person looks at checks directly.
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
<!-- tarav.breadcrumb 0f987fcde260 -->
<!-- tarav.breadcrumb 5c2663eff956 -->
<!-- tarav.breadcrumb 991c6bf77c55 -->

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
Type, check or identity. Breadcrumb and Reference resolution use atomic
identified POI families.
<!-- tarav.breadcrumb 0158b0cc8222 -->
<!-- tarav.breadcrumb 0d39e5ec3a25 -->
<!-- tarav.breadcrumb c84140acad62 -->
<!-- tarav.breadcrumb 4bf190d70e6f -->

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
<!-- tarav.breadcrumb 7d19421b22e7 -->
<!-- tarav.breadcrumb 23058407e5e3 -->
