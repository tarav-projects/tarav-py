# Agentos.Agent.Model

`Agentos.Agent.Model` defines how Agentos represents provider integration for runnable agents and sessions.

The model uses two provider-native anchors:

- `<Provider>.Agent` — the provider-native configured actor
- `<Provider>.Session` — the provider-native session artifact model

Agentos keeps provider-specific shape in those native anchors and derives provider-agnostic outputs through explicit conversion boundaries.

## Provider Agent

`<Provider>.Agent` is the configured provider actor.

Examples:

- `Codex.Agent`
- `Claude.Agent`
- `Pi.Agent`
- `OpenCode.Agent`

It is not a new runtime. It is the Agentos model for a configured provider actor that may support tasks such as running, Chatlas capture, account checks, home resolution, and session discovery.

Subsystem behavior may attach as focused provider-agent extensions:

- `<Provider>.Agent.Runner`
- `<Provider>.Agent.Chatlas`
- `<Provider>.Agent.Accounts`
- `<Provider>.Agent.Home`

These extensions are not separate top-level model anchors. They keep the base provider agent small while leaving room for provider-specific complexity.

A provider agent is the composition point for task-specific provider behavior.

It may start from a minimal configuration and be resolved or enriched for a specific task by combining the provider-native agent anchor with the relevant subsystem extension data. For example, running an agent may use runner, home, account, and terminal-command facts, while Chatlas capture may use home, raw-artifact, and session-discovery facts.

Subsystem extensions contribute the facts needed for a task without becoming separate top-level model anchors.

## Provider Session

`<Provider>.Session` is the native session artifact model for a provider.

Examples:

- `Codex.Session`
- `Claude.Session`
- `Pi.Session`
- `OpenCode.Session`

It captures provider-native facts such as ids, file paths, event streams, SQLite rows, timestamps, workspace hints, and raw artifact references where those exist.

`<Provider>.Session` is not the provider-agnostic Agentos session model.

## Agentos Session

`Agentos.Session` is the provider-agnostic normalized session model.

In the current index surface, `Session.Model` is the concrete standard data model for `Agentos.Session`.

Boundary:

```text
raw provider artifacts
  -> <Provider>.Session
  -> Agentos.Session / Session.Model
```

Provider-native quirks should stay in raw artifacts or `<Provider>.Session`. Provider-agnostic facts belong in `Agentos.Session` / `Session.Model`.

## Chatlas Normalizer

`Chatlas.Normalizer` is the provider-specific conversion boundary.

It converts:

```text
<Provider>.Session -> Agentos.Session / Session.Model
```

Provider-specific normalizers may exist for Codex, Claude, Pi, Copilot, OpenCode, and other providers.

## Shared Primitives

Agentos may share primitives where they genuinely fit:

- `ProviderFamily`
- `ConfigSource`
- `HomeSlot`
- terminal command data
- run request/result data
- raw artifact policy

These are reusable primitives, not a forced object hierarchy. Provider-specific objects decide how the primitives apply.

## Design Rules

- Prefer two provider-native anchors: `<Provider>.Agent` and `<Provider>.Session`.
- Keep `Agentos.Session` provider-agnostic.
- Normalize provider-native sessions through explicit provider normalizers.
- Treat `<Provider>.Agent` as the composition point for task-specific subsystem data.
- Use provider-agent extensions for subsystem behavior when useful.
- Do not turn every subsystem concern into a separate top-level model object.
- Do not prescribe implementation mechanics in the concept model.

## Relationship To Current Implementation

The current `ProviderInstance` shape is transitional. It mixes configured actor data, launch config, home topology, session discovery, account behavior, and Chatlas behavior.

The target direction is to reduce `ProviderInstance` into a config/input bridge while moving durable model responsibility toward provider-native agents, provider-native sessions, and explicit normalizers.

## Related Concepts

- `Session.Model`
- `Chatlas.Standard.Model.Contract`
- `Project.Selection.Protocol`

## Provenance

Promoted from `../live/560-agentos-agent-session-model-design-summary.md`.
