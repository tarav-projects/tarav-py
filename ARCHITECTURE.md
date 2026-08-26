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

## Ownership map

- `tarav.agent` owns provider-neutral agents, accounts, sessions, monitoring,
  and provider adapters under `tarav.agent.providers`.
- `tarav.chatlas` owns the chat data train from provider-native capture through
  Session Index to the provider-neutral Normal Model. It preserves source
  traceability but does not own search, interpretation, annotation,
  contextualization, or workflow products.
- `tarav.indexlab` owns the Index: an ordered stream of `Index.Record`s, the
  semantic projection folded from it, one `IndexResolver` that every consumer
  reads through, rendering, and lint execution. Its explicit `IndexLibrary`
  resolves independently configured `IndexWorkspace` roots; each workspace is
  also its Bloberia depot and Git repository root.
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
- `tarav.anchory`, `tarav.bloberia`, and `tarav.wayfinder` own anchor,
  record-depot, and portable-reference primitives respectively.
- `tarav.stdlib` contains reusable `mdblocks`, `prefix`, `refs`, and `utils`
  primitives matching the `tarav stdlib` CLI.
- `tarav.canvas`, `tarav.hooks`, `tarav.daemon`, `tarav.skills`,
  `tarav.tournament`, and `tarav.workspaces` are cohesive domains.
- `tarav.iterante` and `tarav.iterante2` are separate runtimes; only behavior
  proven identical belongs in `tarav.iterante._shared`.
- `tarav.tarav2` is the isolated experimental redesign namespace. Existing
  domains and `tarav.runtime` do not import it; only the umbrella CLI adapter
  exposes it through the dedicated `tarav tarav2` command branch.

## Project and surface resolution

`.tarav/project.json` identifies a Tarav project. Project identity is portable;
machine-local path resolution is operational evidence owned outside that file.

The Project Surface Model is a composed read model. Native parsers describe a
file's syntax. Project-aware discovery supplies context and surface membership.
Domain adapters interpret those facts. A file parser must not infer domain
meaning from its path or current working directory.

Index reads resolve through the library and workspace named by
`.tarav/project.json`. Resolution is global within that one workspace, so the
same records must produce the same answer regardless of the reader's working
directory. Annotated code is discovered through the project's `.skw/skw.json`.

## Integration boundaries

- Hooks owns validation and dispatch; runtime injects daemon delivery.
- Wayfinder owns generic reference resolution; domains provide resolvers for
  the resources they understand.
- Skillware consumes native surface models through adapters and reads the Index
  through `IndexResolver`. Nothing reparses Python, and nothing parses Markdown
  as the Index.
- Index findings use the shared POI runtime model. One JSON-serializable run
  model drives every renderer and limit/filter contract.
- POI class documentation may be an Index block naturally placed beside its
  emitting check. Static discovery reads annotations; it never imports checker
  modules merely to discover POIs.
- Chatlas consumers import the public `tarav.chatlas.normal_model` package, not its
  internal modules. Only Chatlas command composition reaches into that layer
  to register its CLI.

Retained Chatlas raw artifacts are authoritative evidence. Its Session Index
and Normal Model cache are derived surfaces and may be rebuilt.

`tests/test_architecture.py` enforces the import graph and the most important
ownership boundaries.
