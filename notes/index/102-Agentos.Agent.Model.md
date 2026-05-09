# Agentos.Agent.Model

`Agentos.Agent.Model` defines how Agentos represents provider-native agents and sessions.

The model uses two provider-native anchors:

- `<Provider>.Agent` — the provider-native configured actor
- `<Provider>.Session` — the provider-native session artifact model

Agentos keeps provider-specific shape in those native anchors and derives provider-agnostic outputs through explicit conversion boundaries.

## Provider Agent

`<Provider>.Agent` is the Agentos model of one configured provider actor.

Examples:

- `Codex.Agent`
- `Claude.Agent`
- `Pi.Agent`
- `OpenCode.Agent`

It is not a new runtime and it is not a generic `Agent.Instance`. It represents the installed or configured agent as that provider exposes it: home roots, command/runtime identity, native configuration, account/runtime facts where relevant, and provider-native capabilities Agentos needs to use.

Provider agents are provider-specific. `Codex.Agent` and `Claude.Agent` do not need to have the same fields. They only need to satisfy the Agentos-level tasks they actually support.

A provider agent owns provider-native access to its sessions:

```text
<Provider>.Agent
  -> discover/load native sessions
  -> returns <Provider>.Session
```

This means session discovery is not a separate generic provider-session model. If Agentos needs to enumerate sessions for Codex, it asks `Codex.Agent` to produce `Codex.Session` objects.

## Provider Session

`<Provider>.Session` is the Agentos model of one provider-native session.

Examples:

- `Codex.Session`
- `Claude.Session`
- `Pi.Session`
- `OpenCode.Session`

It contains all provider-relevant facts about that one session:

- native session id
- native transcript or artifact paths
- native index refs or locators
- timestamps
- title, thread, or workspace hints
- raw artifact refs
- provider-specific metadata needed to understand or normalize the session

`<Provider>.Session` is not the provider-agnostic Agentos session model.

`Codex.Session` and `Claude.Session` may have different fields because Codex and Claude store sessions differently.

## Agentos Session

`Agentos.Session` is the provider-agnostic normalized session model.

In the current index surface, `Session.Model` is the concrete standard data model for `Agentos.Session`.

`Session.Model` is derived output. It is not the native runtime or session object for any provider.

Boundary:

```text
raw provider artifacts
  -> <Provider>.Session
  -> Agentos.Session / Session.Model
```

Provider-native quirks should stay in raw artifacts or `<Provider>.Session`. Provider-agnostic facts belong in `Agentos.Session` / `Session.Model`.

## Normalizer

A provider normalizer is the provider-specific conversion boundary.

It converts:

```text
<Provider>.Session -> Agentos.Session / Session.Model
```

Examples:

```text
Codex.Session -> Codex.Normalizer -> Session.Model
Claude.Session -> Claude.Normalizer -> Session.Model
```

The normalizer is where provider-specific raw/session meaning becomes provider-neutral session data.

## Coordination

Agentos may coordinate across many provider agents:

```text
configured agents
  -> each agent discovers provider-native sessions
  -> Agentos coordinates lists, registries, queries, or exports
```

Cross-provider querying, registry maintenance, indexing, and resolution are Agentos coordination concerns. They are not responsibilities of `<Provider>.Session`.

A provider session should expose its facts. It should not own global search semantics.

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
- Provider-specific objects are the source of provider-specific truth.
- `<Provider>.Agent` models one configured provider actor.
- `<Provider>.Agent` owns access to that provider's native capabilities, including session discovery/loading when supported.
- `<Provider>.Session` models one native session and contains all provider-relevant facts about that session.
- Keep `Agentos.Session` provider-agnostic.
- Normalize provider-native sessions through explicit provider normalizers.
- Provider quirks belong in raw artifacts or `<Provider>.Session`, not in `Session.Model`.
- Cross-provider coordination belongs to Agentos-level services, not to provider sessions.
- Shared Agentos primitives are allowed only when they do not become a forced schema for every provider.
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
