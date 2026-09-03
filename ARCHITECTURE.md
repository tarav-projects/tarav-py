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

- `tarav.agent` owns provider-neutral agents, accounts, sessions, monitoring,
  and provider adapters under `tarav.agent.providers`.
- `tarav.chatlas` owns the chat data train from provider-native capture through
  Session Index to the provider-neutral Normal Model. It preserves source
  traceability but does not own search, interpretation, annotation,
  contextualization, or workflow products.
- `tarav.archive` owns stable Artifact identity, retained Archive Records, and
  portable references to retained or externally located data.
- `tarav.diagram` owns flat Namespace collections of typed semantic Ships and
  separate Annotation claim lineages, their recursive projections, Assertion
  evaluation, read-only renderers over Archive-grounded data, and retained
  `Diagram.View` context selections. Views are separate Git-backed WIP surfaces:
  they materialize Diagram data but never mutate the semantic database.
- `tarav.bloberia` owns the hosted global `Tarav.Bloberia` registry. The public
  `tarav bloberia` command addresses that registry directly; its private JSON
  storage is not a second Tarav system or command surface.
- `tarav.index_model` owns only the written form of an Index line: label grammar
  and the identity hashes asserted over the `Line.Type + body + anchor` triplet.
  It does not model the Index.
- `tarav.surfaces` owns deliberately thin native Python and Markdown models.
  It exposes host-language structure, not Skillware attachment policy or Index
  policy.
- `tarav.skillware` maps native surface models into annotations, managed
  blocks, builds, checks, context projections, and edition history.
- `tarav.skw` owns backend-neutral network algorithms shared by consumers; it
  does not own Skillware policy.
- `tarav.poi` owns the shared finding model and resolution adapters. Producers
  retain their check classes and POI class definitions. The shared runner
  instantiates selected checks with one domain context; ordinary earlier check
  results express execution dependencies.
- `tarav.anchory` remains a legacy importable primitive for retained consumers;
  it has no public umbrella-CLI command.
- `tarav.stdlib` contains reusable `mdblocks`, `prefix`, `refs`, and `utils`
  primitives matching the `tarav stdlib` CLI.
- `tarav.project` owns the public `tarav project` namespace and composes its
  initialization, discovery, resolution, verification, and project-local
  Skills operations. `tarav.skills` remains the cohesive domain that owns
  Skills behavior.
- `tarav.hooks`, `tarav.daemon`, `tarav.tournament`, and `tarav.workspaces` are
  cohesive domains.
- `tarav.iterante` and `tarav.iterante2` are separate runtimes; only behavior
  proven identical belongs in `tarav.iterante._shared`.

## Project and surface resolution

`.tarav/project.json` identifies a Tarav project. Project identity is portable;
machine-local path resolution is operational evidence owned outside that file.

The Project Surface Model is a composed read model. Native parsers describe a
file's syntax. Project-aware discovery supplies context and surface membership.
Domain adapters interpret those facts. A file parser must not infer domain
meaning from its path or current working directory.

Annotated code is discovered through the project's `.skw/skw.json`.

## Integration boundaries

- Hooks owns validation and dispatch; runtime injects daemon delivery and
  exposes submission as `tarav daemon hook`.
- Wayfinder owns generic reference resolution and is exposed publicly as
  `tarav reference`; domains provide resolvers for the resources they
  understand.
- Skillware consumes native surface models through adapters. Nothing reparses
  Python.
- Chatlas consumers import the public `tarav.chatlas.normal_model` package, not its
  internal modules. Only Chatlas command composition reaches into that layer
  to register its CLI.
- Diagram consumes Chatlas's public Normal Model for producer and support
  evidence. Chatlas does not import Diagram.

Retained Chatlas raw artifacts are authoritative evidence. Its Session Index
and Normal Model cache are derived surfaces and may be rebuilt.

`tests/test_architecture.py` enforces the import graph and the most important
ownership boundaries.
