# Tarav Python Architecture

`tarav-py` is one modular-monolith distribution. Subsystems remain importable
and testable namespaces, while one runtime composes cross-domain behavior.

## Dependency direction

```text
entrypoints (`tarav.cli`, `tarav.daemon`)
                    |
              `tarav.runtime`
                    |
       domains and integration adapters
                    |
              `tarav.harness`
                    |
    native surfaces and domain foundations
                    |
               `tarav._core`
```

- Entrypoints parse input and render results. They do not own domain behavior.
- `tarav.runtime` is the composition root for registries and cross-domain
  adapters.
- Domain foundations do not import the runtime or CLI to obtain dependencies.
- `tarav.harness` contains semantic roles, class-owned record interfaces, Ship identity
  primitives, and the explicit, trusted Record Type registry used by
  applications. Applications import Harness; Harness never imports an
  application.
- `tarav._core` contains dependency-free infrastructure only after multiple
  domains have demonstrated identical semantics.
- Cross-domain imports must remain acyclic outside the composition root.

`tarav._core.operational_logging` is the shared diagnostic transport used by
multiple domains. Libraries emit namespaced records; Tarav CLI and daemon
entrypoints configure private, best-effort JSONL persistence and quiet console
reporting. Durable daemon, account, monitor, and activity event logs remain
domain-owned semantic records rather than logging backends.

`tarav._core.data_root` supplies the common default physical depot
`~/Documents/tarav/`. Its use by several domains does not make that directory
one repository or authority; each child system retains its own storage
contract and Git boundaries.

## Ownership map

`tarav.poi.primitives` provides application-owned POI subclasses, immutable
finding snapshots, non-throwing collection, and bounded reports.
`tarav.poi.blessings` records explicit acceptance/assessment actions at a path
supplied by the application. It imports no SKW domain. `tarav.skw.pois` owns
SKW class policy and evidence assembly; SKW selects `.skw/blessings/`.
Class paths are obtained through inherited `help()`. Missing assessments stay
visible independently of blessing applicability and detector results.

`tarav.skw.skills` specializes the general `tarav.skw.document` engine
for deployable skill packages. `SkwSkill` specializes the `SkwDepot`
DirectoryRecord; `.skw/main.json` declares its registered type. Ordinary
Tarav loading returns the actionable object. It owns developer/consumer
dependency purposes, product selection, and package checks. General Skillware
does not import this specialization; runtime composes its CLI and Record types.
`skw.skills` is a composition leaf above the generic document engine.
`skw.publication` belongs to that composition layer and consumes Diagram's
public Model projection and Kernel renderer. Explicit selections publish
Markdown without generation; the publication lock records source/model/product
fingerprints. Diagram never imports SKW for publication.
`skw.loading` owns static consumer-context analysis for instruction surfaces.
Its typed `.skw` declarations bind existing SKW blocks through StructuredFile
references, attach parents, and declare links, inclusions, and requirements.
Loading mechanics never infer graph edges from Markdown. Output parsing is
only a conformance check. Runtime injects the skill document factory into the
generic document CLI; generic Skillware never imports the specialization.
Deployment copies declared consumer files to a fresh directory and reports
external consumer skill requirements; it does not install dependencies.

Chatlas owns `chatlas.references.ChatlasTurnReference`, a Normal Model consumer
exposing exact Turn coordinates and messages through the shared Reference API.
Runtime registers it; the references foundation does not import Chatlas.
Skillware composes that reference with its context roles. `maintenance` provides
context, `dependency` enables target-change tracking, and `user-grounding`
checks User-Turn evidence without claiming approval or semantic fidelity.

- `tarav.harness` owns the small application-facing semantic base classes,
  the `Ship` identity primitives, and retained Type-reference to trusted Python
  class dispatch. A `Ship` wraps one UUID and nothing else, so identity comparison
  ignores the specialized class. Every `TaravObject` subclass, including
  intermediate bases, declares a class-local `type_ship` beside its
  human-facing `type_name`; the registry indexes both and treats the Type Ship
  as authoritative, so a known Type keeps resolving after a rename. A retained
  Type reference may be a legacy label or a structural `{uuid, label}`
  value, and the registry reports absent, unknown, or conflicting
  components rather than guessing. `TYPE_RESOLUTION_PATH` is the single Harness-owned ordered sequence
  of literal key paths locating that reference — `__tarav__.type`, then root
  `type`. It is not configurable by applications, registries, Record families,
  or concrete Types: the first path that exists is selected even when its value
  is null or empty, so a malformed reference fails at its own location instead
  of being shadowed by a later one. `__tarav__` is the reserved namespace an
  application uses when its own records already give `type` another meaning.
  `TaravObject` is the semantic root; a Record is its JSON representation,
  particularly when retained in storage. Objects expose `from_json(value)`,
  `to_json()`, and a storage-independent `json_example()`. Registry dispatch,
  file loading, and directory loading construct through the selected class's
  `from_json`; `json_load(file)` remains the stream entry point. Records expose
  the Ships they semantically recognize through `ships()`, which
  a subclass extends by returning concrete `Ship` instances; the projection
  carries no serialized paths, and Harness never infers a Ship by scanning
  UUID-shaped data. `TypeRegistry.json_load(file)` loads a JSON object and
  constructs its exact registered class. The inherited
  `RecordClass.json_load(file, registry=...)` instead constructs the calling
  class only when it is that registered authority or a subclass. Harness has
  no opaque fallback Record wrapper: uninterpreted JSON remains ordinary JSON.
  It does not impose a writer or application storage model. Skillware's
  `SkwBlock` uses the same object contract while remaining inline in its
  document's JSON.
  Every object inherits a Pydantic `RecordInterface`. The base contract is
  strict and open to additional fields; concrete classes declare required
  fields and may close their own interface. Type dispatch remains separate
  from these field contracts. `issubrecord(B, A)` checks interface inheritance
  alone, while `isrecordsubclass(B, A)` requires both Python and interface
  inheritance. `preserves_parent_record_interface()` checks the combined
  relationship against all direct Tarav parents (true when there are none).
  Independent interfaces are explicit class declarations, without an extra
  flag. These queries describe ancestry, not proofs of field-override
  compatibility.
  `from_json` and `to_json` validate without replacing retained data with
  Pydantic output. Transforming or dropping supplied fields is rejected;
  defaults are not inserted into stored representations. `record_data` gives
  a fresh typed view, including interface defaults, whose edits do not mutate
  the retained record. Direct constructors remain class-owned; use
  `validate_record` to check a representation independently. Schema tooling
  uses `RecordInterface.model_json_schema()`.
- `tarav.agent` owns provider-neutral agents, accounts, sessions, monitoring,
  and provider adapters under `tarav.agent.providers`.
- `tarav.chatlas` owns the chat data train from provider-native capture through
  Session Index to the provider-neutral Normal Model, bounded structural Query
  over that Model, and named presentation of Query findings. Query owns
  selection and record assembly; Renderers own presentation. Chatlas preserves
  source traceability but does not own semantic interpretation, annotation,
  contextualization, or workflow products.
- `tarav.archive` owns stable Artifact identity, retained Archive Records, and
  portable references to retained or externally located data.
- `tarav.diagram` owns flat Namespace collections of typed semantic Ships and
  separate Annotation claim lineages, recursive organizational Collections,
  their projections, Assertion evaluation, read-only renderers over
  Archive-grounded data, retained `Diagram.View` reading workspaces, and
  durable `Diagram.Draft` writing workspaces. Views never mutate the semantic
  database. Drafts reconcile proposed changes and apply them through the
  ordinary Diagram capture boundary.
- `tarav.scoring` owns named Assertion Pools, explicit Pool Enrollments,
  Ranking Tasks, exact Agent Runs, retained Results, live derived Scores, and
  compact per-Assertion Scoring Traces in the independent Git-backed
  `~/Documents/tarav/scoring/` Record repository. Each Pool directory is the
  default comparability boundary and owns its Enrollments, Tasks, Runs, and
  Results. Assertion Classes declare compatible concrete Pool Types and adapt
  exact Assertion instances into the candidate material those Pools require.
  Each Pool Record declares that concrete Type directly; its registered class
  owns instance creation, comparison mechanics, validation, and Task assembly.
  Named Pool instances own their enrolled population and evidence history. Pools do not discover
  participants: Assertion instances enroll explicitly and may join several
  Pools, while several Pool instances may use one Pool Class. A Task CLI call
  creates the Task and one compact frozen unresolved Run, then prints the
  blinded prompt for an arbitrary Agent. The Run retains exact Task identity,
  opaque candidate order, known or unknown Runner provenance, renderer/code
  provenance, submission location, and prompt hash without duplicating the
  prompt. A Result is submitted against exactly one previously registered Run;
  submission never mutates that Run. Score methods may select Results from
  several Pools and are code, not retained definitions.
  Explicit scoring executions append typed Events to one Trace per Assertion;
  each Event records Pool selection, the Results Git state, code provenance,
  value, and supporting statistics. Read-only renderers expose current values
  and history without interpreting trends. A disposable reverse-reference
  index keeps the Record graph navigable without stored backlinks. Diagram
  owns the Assertions being evaluated; Scoring owns evaluation evidence and
  derived interpretations. Runner code executes a rendered Task but does not
  define Assertion semantics.
- `tarav.bloberia` owns the hosted global `Tarav.Bloberia` registry. The public
  `tarav bloberia` command addresses that registry directly; its private JSON
  storage is not a second Tarav system or command surface.
- `tarav.reading_club` owns the thin, read-only logistical model and public
  navigation CLI for Git-tracked Reading Projects under the independent
  `~/Documents/tarav/reading-club/` data surface. It does not identify
  documents, interpret reading content, or own Agent reading workflows.
- `tarav.surfaces` owns deliberately thin native Python and Markdown models.
  It exposes host-language structure, not Skillware attachment policy or Index
  policy. Its standalone CLI is disconnected; parsers remain in place for
  future source-aware workflows and current `stdlib.mdblocks` consumption.
  See `src/tarav/surfaces/README.md` for retained intent.
- `tarav.skw.generation` owns the independent generation MVP: typed
  template blocks, invocation snapshots, output dependencies, and read-only
  findings. Its mechanics use only the standard library and do not query
  Index, Diagram, or contextualization. See `notes/skillware-generation.md`.
- `tarav.skw.document` composes those helpers into typed document sources,
  generation annotations, and locks. It owns whole-document assembly and
  source linting. Runtime registers its Record authorities; CLI operations at
  `tarav skw document` delegate to the library.
  Context listings inspect reference addresses without loading target bodies;
  explicit reads select one entry. Structured references own source-relative
  address resolution. Lint/record retain full fingerprint checks independently.
- `tarav.skw` owns typed document compilation and skill-package specialization.
  The retired Skillware annotation and compiler stack is preserved only in
  Archive.Attic.
- `tarav.poi` owns application-defined POI primitives, immutable finding
  snapshots, non-throwing collection, bounded reports, and append-only
  blessing/assessment records at caller-owned paths. Producers retain their
  check classes and decide how to respond to findings.
- `tarav.python_env` owns the public `tarav python` namespace, which exposes
  the interpreter already running Tarav so an external script can import it
  without locating or installing the distribution. The environment is reported,
  never provisioned: `interpreter()` is `sys.executable`, so a tool install and
  a project run each answer honestly for their own process. A script is named
  explicitly, as `--file` or as `--src`, so nothing about the command line is
  positional and arguments belonging to the script stay behind a `--`
  separator. Callers that need more than `python run` use `python path` and
  drive the interpreter directly.
- `tarav.stdlib` contains reusable `mdblocks`, `prefix`, `refs`, and `utils`
  primitives matching the `tarav stdlib` CLI.
- `tarav.project` owns the public `tarav project` namespace and composes its
  initialization, discovery, resolution, verification, and project-local
  Skills operations. `tarav.skills` remains the cohesive domain that owns
  Skills behavior.
- `tarav.hooks`, `tarav.daemon`, and `tarav.workspaces` are cohesive domains.
- The former Tournament implementation is retained only under
  `_DEPRECATED/tournament/` for design archaeology. It is neither importable
  maintained code nor a public command surface.
- `tarav.iterante` and `tarav.iterante2` are separate runtimes; only behavior
  proven identical belongs in `tarav.iterante._shared`.

## Project and surface resolution

`.tarav/project.json` identifies a Tarav project. Project identity is portable;
machine-local path resolution is operational evidence owned outside that file.

The Project Surface Model is a composed read model. Native parsers describe a
file's syntax. Project-aware discovery supplies context and surface membership.
Domain adapters interpret those facts. A file parser must not infer domain
meaning from its path or current working directory.


## Integration boundaries

- Hooks owns validation and dispatch; runtime injects daemon delivery and
  exposes submission as `tarav daemon hook`.
- `tarav.references` owns shared typed reference mechanics; runtime registers
  domain reference classes explicitly. There is no top-level `tarav reference`
  command.
- Native surface parsers remain independent of workflow annotation semantics.
- Chatlas consumers import the public `tarav.chatlas.normal_model` package, not its
  internal modules. Only Chatlas command composition reaches into that layer
  to register its CLI.
- Chatlas Query consumes streamable Normal Model collections. Named Chatlas
  Renderers consume structured Query results and never reimplement selection.
- Diagram consumes Chatlas's public Normal Model for producer and support
  evidence. Chatlas does not import Diagram.
- Diagram specializes Harness roles and uses its trusted Type registry for
  Ship and Annotation Record dispatch. It is the first consumer of Type Ships:
  its record classes declare them, every Type reference read goes through
  `TYPE_RESOLUTION_PATH` rather than Diagram reading root `type` itself, and
  its registered Record classes accept their retained Record directly. A
  Diagram storage binding may additionally supply the identity derived from a
  file address and the Namespace derived from its repository; those facts are
  not forced into the retained JSON. Generic storage bindings do not interpret
  Type-owned fields: registered classes own validation, score-vector layout,
  Ship projection, and other semantic behavior. Gate and Assertion payloads
  keep their own nested `type` keys; the resolution path addresses Records,
  not cargo. Retained label-only Records are not rewritten. Diagram retains
  its object schemas, projections, Ships, Assertions, and storage semantics.
- Scoring consumes Diagram's public projection and Chatlas-backed support when
  an Assertion-owned task builder constructs an `Index.Line` grounding case.
  Diagram does not import Scoring; score discovery can be rebuilt from the
  Scoring Record repository.

Retained Chatlas raw artifacts are authoritative evidence. Its Session Index
and Normal Model cache are derived surfaces and may be rebuilt.

`tests/test_architecture.py` enforces the import graph and the most important
ownership boundaries.

## Record network library

The library is the operating surface; scripts and CLI commands are consumers.
Using its Records, references, navigation and checks supplies the implicit
harness graph. There is no required action-graph executor.

`RecordClass.help()` (also callable as `record.help()`) is the inherited
class-level context entry point. It returns a dictionary with `class` (the
qualified Python name), `source_path` (an absolute code file path),
`source_line` (one-based), and `hints` (opaque diagnostic context).
Missing-source explanations live under `hints.unavailable` as a field-to-reason
mapping; successful discovery returns empty hints. Mechanics use the source
fields, not the diagnostic explanations.
Unavailable values are `None`; a missing definition line does not discard a
known file path. This information comes from Python inspection, not generated
prose. Classes can override and extend it to expose documentation, skills and
further context. The method returns information without printing or mutating
Records; its code location is distinct from a Record instance's storage path.

- `tarav.harness.records` classifies FileRecord and DirectoryRecord and owns
  path loading. Directory entry discovery checks `__tarav.json`, `main.json`,
  `type.json`, `archive.json`, then `registration.json`. The latter two are
  Archive's concrete entry conventions. The first present entry wins even if
  malformed. Its ordinary type declaration selects the registered authority;
  `record.source` supplies the retained file location, and DirectoryRecord
  exposes its parent directory. Payload files need not be Records.
- `tarav.references` owns locator/check/hints roles. FileReference
  resolves a path and optionally checks SHA-256. Hints are never read by
  mechanical location or checking. ReferenceResult exposes findings without
  repairing data. `Reference.RecordInterface` requires the retained Type and
  locator; concrete interfaces declare locator and check structures for File,
  Git, Structured File, Archive, and Chatlas Turn references. Checks and hints
  are optional and producers omit them when absent. Concrete domain references
  own further semantics.
- `tarav.harness.workflows` owns explicit Workflow registration and trusted
  Python-file entry points. It does not execute workflows or inspect arbitrary
  Record payloads for code. Registered Record classes remain authoritative.
- `tarav.navigation` owns typed provider interfaces and a virtual root of
  mounted collections. Provider errors and invalid responses become POIs.
  FilesystemProvider uses the common loader; ArchiveProvider exposes JSONL
  collections and DiagramProvider preserves Namespace/address bindings.
- `create_runtime(workflows=..., config=...)` composes built-in Archive,
  Diagram, and Navigation workflows. Scripts use `runtime.records`,
  `runtime.navigation`, `runtime.load(path)`, and `runtime.source_root`.
  Optional explicit configuration declares `workflow_files` and `providers`
  (`name`, `workflow`, `root`); paths are relative to the configuration file.
- Archive Records now declare `type` under schema 2 and use Harness dispatch.
  Artifact registration directories retain a DOI contract and can be loaded
  as DirectoryRecords. Retirement appends evidence and preserves the DOI.
  Archive references contain `locator: {archive, doi}` plus optional `check`
  and opaque `hints`; the old flat reference schema is not accepted as this
  type.

Schema migration is explicit developer work, never a reader fallback.
`tooling/migrate_793_archive_records.py` validates a complete clean Archive
Record repository before updating it, retaining the prior Git checkpoint.
Historical Archive observations and Artifact IDs are unchanged.

### Reference construction and resolution

Scripts construct `FileReference(path)` from `tarav.references` or
`GitFileReference(repository=..., commit=..., path=...)` from
`tarav.references.git`. File construction observes name, size and modification
time when available. Git construction resolves the revision to an exact commit
and records its blob check and mechanical hints. Neither generates prose.
Passing a retained mapping loads it without refreshing hints or selecting new
defaults. Reference Type Ships and serialized type names survive the module
move; callers must import the new module directly.

`runtime.references` is the registered ReferenceWorkflow. Its `load(record)`
uses the shared Type registry and constructs through the selected class's
`from_json()`, enforcing its RecordInterface. `resolve(reference_or_record)`
dispatches to the owning class. Unknown types and invalid interfaces return
findings rather than triggering imports. Resolution does not itself search for
annotations or equate targets.

Archive imports shared reference/Git mechanics; the reference foundation never
imports Archive. `ArchiveReference(doi=...)` selects the library's
`default_archive_root()` unless `archive=...` is supplied. The selected absolute
location is retained in the locator so a later machine default does not retarget
the saved reference. `Archive.open()` and the CLI use the same default.
