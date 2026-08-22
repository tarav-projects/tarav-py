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
    native surfaces and domain foundations
                    |
               `tarav._core`
```

- Entrypoints parse input and render results. They do not own domain behavior.
- `tarav.runtime` is the composition root for registries and cross-domain
  adapters.
- Domain foundations do not import the runtime or CLI to obtain dependencies.
- `tarav._core` contains dependency-free infrastructure only after multiple
  domains have demonstrated identical semantics.
- Cross-domain imports must remain acyclic outside the composition root.

## Ownership map

- `tarav.agent` owns provider-neutral agents, accounts, sessions, monitoring,
  and provider adapters under `tarav.agent.providers`.
- `tarav.chatlas` owns the retained chat dataset. Its `lossless` package owns
  normalization, the provider-neutral Normal Model, compact caches, and
  content queries. It is a layer of Chatlas, not a second Chatlas product.
- `tarav.index` owns Index records, standing, capture, gates, lint execution,
  and the Index CLI. `tarav.index_model` owns small shared Index-line identity
  and label primitives.
- `tarav.surfaces` owns deliberately thin native Python and Markdown models.
  It exposes host-language structure, not Skillware attachment policy or Index
  policy.
- `tarav.skillware` maps native surface models into annotations, managed
  blocks, builds, checks, context projections, and edition history.
- `tarav.skw` owns backend-neutral network algorithms shared by consumers; it
  does not own Skillware policy.
- `tarav.poi` owns the shared finding model and resolution adapters. Producers
  retain their checks and class definitions.
- `tarav.anchory`, `tarav.bloberia`, and `tarav.wayfinder` own anchor,
  record-depot, and portable-reference primitives respectively.
- `tarav.stdlib` contains reusable `mdblocks`, `prefix`, `refs`, and `utils`
  primitives matching the `tarav stdlib` CLI.
- `tarav.canvas`, `tarav.hooks`, `tarav.daemon`, `tarav.skills`,
  `tarav.tournament`, and `tarav.workspaces` are cohesive domains.
- `tarav.iterante` and `tarav.iterante2` are separate runtimes; only behavior
  proven identical belongs in `tarav.iterante._shared`.

## Project and surface resolution

`.tarav/project.json` identifies a Tarav project. Project identity is portable;
machine-local path resolution is operational evidence owned outside that file.

The Project Surface Model is a composed read model. Native parsers describe a
file's syntax. Project-aware discovery supplies context and surface membership.
Domain adapters interpret those facts. A file parser must not infer domain
meaning from its path or current working directory.

Index evaluation requires an explicit `--project` selection. It discovers
native Index depots structurally and annotated code through the project's
`.skw/skw.json`. The same project data must produce the same verdict regardless
of the evaluator's working directory.

## Integration boundaries

- Hooks owns validation and dispatch; runtime injects daemon delivery.
- Wayfinder owns generic reference resolution; domains provide resolvers for
  the resources they understand.
- Skillware consumes native surface models through adapters. Neither Skillware
  nor Index reparses Python or Markdown independently.
- Index findings use the shared POI runtime model. One JSON-serializable run
  model drives every renderer and limit/filter contract.
- POI class documentation may be an Index block naturally placed beside its
  emitting check. Static discovery reads annotations; it never imports checker
  modules merely to discover POIs.
- `tarav.index.capture_manifest` drives preview and landing from one validated
  plan. Chat evidence, surface changes, LineRecords, and audit output derive
  from that same plan.
- Chatlas consumers import the public `tarav.chatlas.lossless` package, not its
  internal modules. Only Chatlas command composition reaches into that layer
  to register its CLI.

Persisted `agentos.*` and `tarav.chatlas2.*` identifiers are storage contracts,
not current Python namespace declarations. Renaming them requires an explicit
data migration; prose and imports should use current `tarav.*` names.

`tests/test_architecture.py` enforces the import graph and the most important
ownership boundaries.
