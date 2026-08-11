# Agentos Python Architecture

`agentos-py` is one modular-monolith distribution. Subsystems are importable
namespaces, but one release and one composition root keep their contracts aligned.

## Dependency direction

```text
entrypoints (agentos.cli, agentos.daemon)
                    |
              agentos.runtime
                    |
      domain systems and integration adapters
                    |
       agentos.stdlib and domain foundations
                    |
               agentos._core
```

- `agentos.runtime` constructs registries and injects cross-domain adapters.
- Domain foundations do not import runtime or CLI composition to obtain defaults.
- `_core` contains dependency-free infrastructure with proven multiple consumers;
  it does not contain product policy.
- `stdlib` contains reusable user-facing primitives matching the existing
  `agentos stdlib ...` CLI namespace.

## Namespace map

- `agentos.agent`: provider-neutral agent, account, session, and monitor behavior.
- `agentos.agent.providers`: provider registry, home/extraction infrastructure,
  and concrete adapters under one package per provider.
- `agentos.chatlas`, `canvas`, `index`, `poi`, `wayfinder`, `skillware`,
  `anchory`, `bloberia`, `hooks`, `daemon`, and `tournament`: cohesive domains.
- `agentos.stdlib.mdblocks|prefix|refs|utils`: reusable CLI/library primitives.
- `agentos.iterante` and `agentos.iterante2`: distinct runtimes sharing only
  mechanics whose behavior is identical under `agentos.iterante._shared`.
- `agentos.skw`: backend-neutral network algorithms consumed by Index and
  Skillware; it is intentionally independent from either consumer.

Provider-specific code belongs at
`agentos.agent.providers.<provider>`. For example, Codex quota hooks and session
models live under `agentos.agent.providers.codex`; they do not occupy a top-level
`agentos.codex` package.

## Integration boundaries

- Hooks owns validation and sequential dispatch. Runtime injects Daemon delivery.
- Wayfinder owns reference models, registry memory, and generic resolver dispatch.
  Index owns the `index.block` resolver and POI catalog discovery; runtime injects
  the composed resolver and catalog into commands and report adapters.
- POI adapters live under `agentos.poi.adapters` when they bridge a producer
  domain to the common reporting model.
- Chatlas command behavior lives in `_command_support.py`; `commands.py` owns the
  public parser composition and registrar.

## Shared infrastructure rule

Promote code to `_core` only after matching semantics exist in multiple domains.
`_core.persistence` is the model: it owns same-directory, fsynced atomic text and
JSON replacement, while each caller retains its schema, validation, and locking.

Architecture tests in `tests/test_architecture.py` enforce namespace placement,
the Hooks/Daemon boundary, and an acyclic top-level subsystem graph.
