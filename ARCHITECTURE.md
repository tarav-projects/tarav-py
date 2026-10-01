# Tarav Python Architecture

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
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
- **Context** is a progressively navigable view rooted at a Type or Object.

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
order, omitting non-Tarav mixins. Its Context exposes `bases` and a `target`
route to the represented class context, preserving ancestor context rather
than merging it. Detached class Records cannot infer live bases or targets.
`KernelWorkflow` owns the remaining foundational Types; each concrete
Workflow entity retains its established WorkflowShip address. Each concrete
Workflow declares that fixed identity independently through `_workflow_id()`;
`WorkflowClass()` returns the same process-wide entity on repeated calls.
`entity(WorkflowClass)` represents only the implementation class, retaining its
separate TypeShip. Its `workflow` field declares ownership, not instance identity.
Class and object Context therefore have separate subject addresses. Both UUIDs
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
- Runtime-local state lives in `ContextService`, `ReferenceService`,
  `BreadcrumbService`, and `NavigationService`, not Workflow instances or mutable
  Workflow class attributes. Separate runtimes receive separate service objects.
- Runtime composition verifies that every registered Type's Workflow Ship
  resolves to a registered Workflow.

`tarav.l1.context.explore()` exposes standalone navigation and accepts explicit
contributors. `tarav.l3.context.context()` adds the current runtime's retained
entries. Both invoke `class_context()` for a Type and `obj_context()` for an
Object, then return a
`ContextExplorer`: a stateful explorer with history across nested folders and
jumps to other subjects. A `Context` is a read-only `TaravObject` folder with
named or positional entries and no cursor state. Each `ContextEntry` is an
attachment point at one path; `open()` returns its value, either another Context
folder or any other `TaravObject`. Folder status follows the opened value,
without a separate entry flag. Entries produced by an explorer remember their
origin. `context(entry)` follows its value in that same explorer; calling
`context(subject)` directly starts a new one. Runtime and retained entries
share the subject root's namespace.

The Context Workflow uses Record Archive for durable roots under
`~/Documents/tarav/archive/<context-workflow-ship>/<subject-ship>/`. The root is
a generic Dictionary Archive; a separate Context-owned `context.json` Record
binds its Ship to the Entity or class Ship. Nested Dictionary and Vector
Archives provide arbitrary organization. The Archive owns retention, placement,
and Git policy; Context owns entry attachments, folder objects, and runtime
composition. A retained leaf ArchiveEntry stores a ContextEntry whose cargo is
another typed Record. A retained folder ArchiveEntry stores a typed Archive;
its `context.json` attachment is a ContextEntry whose cargo is a typed Context
folder Record identifying that Archive. This lets either ContextEntry open its
value without making Context inherit Archive behavior. A Context writer chooses
leaf cargo explicitly or creates a folder with a Context attachment.
Plain unidentified Objects can still contribute runtime entries without
Archive backing. Opening a Context never creates retained data; the Test
Workflow explicitly seeds synthetic Archives for end-to-end tests.

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
`ProjectLaunchConfiguration` read from common marker fields without concrete
Project Type dispatch. Environment selection is explicit and never participates
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

- `tarav.l0._core` is the moved private utility package. It currently includes
  project-specific helpers alongside broadly shared mechanics; those modules
  have not yet been classified into later layers. New shared utilities enter
  `_core` only after demonstrated reuse.
- `tarav.l0.kernel` contains Tarav's public semantic foundation: Types, Objects,
  Entities, Ships, class-owned Record interfaces, Explorer contracts,
  Record-space contracts, and trusted Type and Workflow registries. Kernel
  imports no application domain.
- `tarav.l1.context` owns Context types, standalone navigation, class-bases
  presentation, and the Context Workflow declaration. `explore()` accepts
  explicit contributors without loading Archive or runtime.
- `tarav.l2.context` owns Archive-backed Context Types and `ContextService`;
  `tarav.l3.context` owns the runtime-aware `context()` convenience. Runtime
  assembly constructs its service directly; the l1 Workflow has no service factory. Kernel retains
  extensible context hooks with opaque builder arguments, not Context imports.
- Domain packages own their vocabulary, Records, storage, validation, and
  operations. Cross-domain imports remain acyclic.
- `tarav.l1.archive.records` implements Record Archive, nested beneath its parent
  Archive workflow. Artifact-registration Record definitions live separately in
  `tarav.l1.archive.artifact_records`; Archive's parent implementation does not
  import its Record Archive child.
- `tarav.l1.loading` owns profile discovery and `tarav.l3.loading` owns the
  runtime-backed load facade. `tarav.l1.project` owns the minimal Project Type;
  `tarav.l2.project` adds Models and Wiki integrations. Archive uses the
  kernel-owned current Record registry; retained Context owns its service lookup.
- `tarav.l1.git` owns bounded repository mutation and preserves unrelated index
  state through isolated commit indexes. Immutable Git surface References stay
  in `tarav.l1.references.git`. `tarav.l2.git.breadcrumbs` composes Git and
  Breadcrumb evidence; `tarav.l3.git` exposes process adapters.
- `tarav.l1.skw` owns typed document blocks, retained output, and declared
  loading/slot mechanics. Trusted Type dispatch selects each nested block;
  code producers write source output explicitly while compilation only assembles
  retained output. `tarav.l2.skw` owns deployable skill-package operations,
  publication, and Diagram-dependent checks.
- Integration bundles compose independent domains without making either one
  depend on the other.
- `tarav.l3.runtime.create_runtime()` currently assembles the installed
  Workflow classes, services, Record Types, providers, hooks, and integrations.
  This is a library assembly facility, not a foundational Workflow contract.
- CLI and daemon packages translate external interaction into library calls.
  Lower layers neither import nor shell out to the umbrella CLI.

## Kernel contracts

`tarav.l1.lines.Line` is a storage-independent entity with text and one
interpretive entity scope. Its Record retains the scope Ship; explicit binding
resolves that edge without changing it. `LineScope` is a read-only Context
specialization. `explore(subject, type=LineScope)` and the runtime context
entry points select it explicitly; unsupported context types fail. With no
selector, existing general ContextExplorer behavior remains unchanged.
Object `.context(type=...)` uses a host-configured Kernel hook, avoiding upward
Kernel imports. Specialized Context factories own subject compatibility.

Archive and Context expose workflow membership through `ArchiveType` /
`ArchiveObject` and `ContextType` / `ContextObject`. Explorers are workflow
Types without requiring the Object Record contract. Their roots may be owned
leaf objects; listing or selection then raises `NotADirectoryError`. Shared
Explorer helpers check Folder/List capability and key typing. Workflow-specific
explorers enforce membership at roots and navigable destinations before moving.
Opening a foreign value remains valid and does not enter its graph.

The Kernel establishes only the common contracts needed for interoperability:

- `TaravType` provides class help, class context, and the `class_entity()` hook
  used to project the Python class into the Diagram.
- `TaravObject(TaravType)` adds an instance and a class-owned Record projection.
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
- `to_record()` calls the class-owned `_to_record()` hook, then validates and
  detaches the result. `from_record()` validates input before calling the
  class-owned `_from_record()` construction hook. When a Record supplies a Type
  reference, both boundaries require it to identify the object's exact class;
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
launch). Without a marker declaration, `.tarav/pyproject.toml` and `.tarav/env`
remain the generated defaults. A marker may instead declare a product manifest
and environment using Project-relative paths; inspection and runner
configuration read these common fields without importing the product package or
dispatching the marker's concrete Type. Sync targets exactly the selected
environment. Paths cannot escape the Project root, and run never installs or
selects a fallback interpreter.

The generated package keeps its code-owned Project TypeShip and package
bootstrap metadata in `.tarav/pyproject.toml`, while the marker retains its
separate project-instance identity. Adoption of an existing base/untyped marker
is explicit; specialized markers and edited source are not overwritten.
Package execution binds the trusted class before dynamic loading. The generic
`tarav run` command executes caller-supplied Python with current or explicit
Project configuration and does not inject a runtime or Project object.

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

| Package | Architectural responsibility |
| --- | --- |
| `agent` | Provider-neutral agent, account, session, and monitoring behavior; concrete providers live below `agent.providers`. |
| `archive` | Artifact identity, retained Archive Records, and Archive-specific location history. |
| `archive.records` | Optional typed Folder and List Archives for storing class-owned Records at explicit roots; the stored Type keeps its domain meaning. |
| `l1.context`, `l2.context`, `l3.context` | The same Context Workflow spans standalone navigation, Archive-backed retention, and runtime selection. |
| `references` | Shared typed locator, check, hints, and resolution mechanics. |
| `chatlas` | Provider-native chat capture, Session Index, provider-neutral Normal Model, bounded Query, and rendering. |
| `breadcrumbs` | Opaque Product.Surface anchors, position observations, attachment storage, and generic annotation transactions. |
| `breadcrumb_workflows` | Independent integrations between Breadcrumbs and producer domains such as Chatlas. |
| `l1.git`, `l2.git`, `l3.git` | The Git Workflow spans repository mechanics, commit-message Breadcrumb integration, and installed CLI composition. |
| `lines` | LinesWorkflow owns Line, Block, Collection, their editions and relationships, projections, rendering, and LineGroundingAssertion semantics. |
| `models` | ModelsWorkflow owns the Model handler, ModelShipRecord, and ModelEditionRecord. Project associations do not imply ownership; several projects may share one Model. |
| `unsorted` | UnsortedWorkflow provisionally owns legacy capture, generic storage interpreters, assessment, Draft, and View types awaiting classification. |
| `scoring` | Common Assertion entities and evaluation mechanics: pools, tasks, runs, results, derived scores, and traces. Existing scoring Records are entities with explicit Context reference edges. |
| `poi` | POIWorkflow owns neutral, identified, and notification POI foundations plus shared collection and notification delivery. Identified POIs derive identity from their concrete Type Ship and explicit producer-supplied situation; collector-local indexes address repeated emissions. Producing workflows own their concrete POI types. |
| `blessings` | BlessingsWorkflow owns the BlessablePOI capability and attributed blessing and assessment Records. Blessability is declared only through subtype composition; blessings match situation identity directly and never suppress a POI. |
| `checks` | Independently runnable bound Checks, CheckPOIs coupled to their Check objects, optional subject providers, and result snapshots. Execution completion and a POI's failure signal are separate. |
<!-- tarav.breadcrumb 28df20317b527872af6eb271a0ede8e2a1c30d0b8fc98201f63e8cb564ec6183 -->
| `skw` | Typed document compilation, generation mechanics, and skill-package specialization. Blocks are Entities with Ships and separate labels; source blocks own typed reading declarations. Loading analysis exposes route facts, while SKW Checks turn those facts into POIs. |
| `surfaces` | SurfacesWorkflow owns MarkdownNormalModel and PythonNormalModel TaravObjects. Their from_text/from_path methods parse native syntax; Records preserve parsed structures without reparsing. Consumers assign domain meaning. |
| `wiki` | Folder-based Markdown Wiki and WikiNote objects, parsing through surfaces, and Wiki-scoped Git closure. No Project dependency. |
| `project` | ProjectWorkflow owns minimal TaravProject and featured Project. Existing project_id is the Ship identity; discovered location stays outside the portable marker. |
| `project.models`, `project.wiki` | Specialized child workflows own Project associations. Project lazily delegates models() and wiki(); the minimal base imports neither integration. |
| `skills`, `workspaces` | User-facing skill and workspace operations. |
| `hooks`, `daemon` | Hook validation and dispatch, plus daemon-owned delivery adapters. |
| `stdlib` | Small reusable library and CLI primitives. |
| `iterante`, `iterante2` | Independently maintained mission runtimes; shared behavior is promoted only after convergence. |
<!-- tarav.breadcrumb 5390bce98b91f130684fb3322d8ee0022a5e60bd1d5390e7e05c8c53b6718e01 -->

Other cohesive command domains follow the same rule: they own their behavior
and use Kernel contracts without moving their semantics into Kernel.

`TaravProject.from_path()` discovers the nearest marker and explicitly interprets
its existing schema, preserving every retained field. Entity identity is
serialized as `project_id`, not a second `id`. Records loaded without a source
remain detached: their location cannot be inferred from identity. Existing
untyped markers are not rewritten; newly constructed Project projections carry
the ordinary `type` reference for generic dispatch. Explicit
`SomeProject.from_path()` constructs that selected class, reprojecting any
retained Type tag in memory without changing the file. Generic from_record()
and load_object() retain exact Type checks. Project-local code is never
automatically imported by discovery. Subtypes define class_entity() normally.

ProjectModels.main() resolves through existing Diagram configuration by default;
an explicit resolver is optional for isolated integrations. ProjectWiki.open()
returns the conventional notes/wiki folder. Neither operation creates data.
Project.models() returns its integration handler; Project.wiki() returns a Wiki.

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

Scoring's `assertions` module supplies the common Assertion contract without
importing consumer workflows. `lines.assertions` specializes it for exact Line
editions and supplies evidence presentation. `scoring.tasks` is the existing
ranking composition layer; it imports that specialization, while the scoring
package's base exports do not import tasks. Import ranking adapters explicitly
from `tarav.l2.scoring.tasks`. Architecture checks inspect Scoring at module
granularity too, distinguishing foundations from composition.

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
trusted Record dispatch through the configured current registry. The marker's
declared Type selects the concrete class; the calling Project class checks the
resulting family without substituting its own Type. Untyped markers require
explicit migration. This is separate from `from_path()`, which retains explicit
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
