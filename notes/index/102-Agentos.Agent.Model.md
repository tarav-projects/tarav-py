# Agentos.Agent.Model

`Agentos.Agent.Model` defines how Agentos represents provider-native agents and sessions.

The model uses three provider-native anchors:

- `<Provider>.Agent` — the provider-native configured actor
- `<Provider>.SessionRef` — a lightweight provider-native reference to one session
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
  -> discover native session refs
  -> returns <Provider>.SessionRef

<Provider>.Agent
  -> load a native session ref
  -> returns <Provider>.Session
```

This means session discovery is not a separate generic provider-session model. If Agentos needs to enumerate sessions for Codex, it asks `Codex.Agent` to produce `Codex.SessionRef` objects. If Agentos needs the full session, it asks `Codex.Agent` to load a `Codex.Session` from the selected ref.

## Provider SessionRef

`<Provider>.SessionRef` is the lightweight provider-native reference to one session.

Examples:

- `Codex.SessionRef`
- `Claude.SessionRef`
- `Pi.SessionRef`
- `OpenCode.SessionRef`

It is not the full session content. It carries enough metadata to identify, list, sort, query, and later load the full `<Provider>.Session`.

It may include provider-native facts such as:

- native session id
- configured agent identity
- display or thread title
- created or updated timestamps
- primary artifact ref
- lightweight native locator or index facts

`<Provider>.SessionRef` is safe for registries and indexes because it describes session identity and basic metadata, not the full provider-native session content.

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
  -> <Provider>.SessionRef
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
  -> each agent discovers provider-native session refs
  -> Agentos coordinates lists, registries, queries, or exports
  -> selected refs are loaded through their provider agent when full sessions are needed
```

Cross-provider querying, registry maintenance, indexing, and resolution are Agentos coordination concerns. They work over provider-native session refs and are not responsibilities of `<Provider>.Session`.

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

## Relocation.Function

`Relocation.Function` is a private function created primarily to relocate or contain an implementation block in a more natural module/file location.

It does not introduce a new public interface, reusable abstraction, domain concept, or independent capability. The original caller remains the semantic interface; the relocation function is only the implementation body placed elsewhere.

Name a relocation function so it does not imply a new semantic level. The name should signal implementation placement, not a new concept.

Python example:

```python
def account_status(self):
    return _codex_account_status_impl(self)
```

Here, `agent.account_status()` is the capability. `_codex_account_status_impl(agent)` is the relocation function holding the provider-local implementation.

Use this pattern when it improves agent navigation and natural placement without pretending the extracted block is a deeper abstraction.

## Design Rules

- Prefer three provider-native anchors: `<Provider>.Agent`, `<Provider>.SessionRef`, and `<Provider>.Session`.
- Provider-specific objects are the source of provider-specific truth.
- `<Provider>.Agent` models one configured provider actor.
- `<Provider>.Agent` owns access to that provider's native capabilities, including session ref discovery and session loading when supported.
- `<Provider>.SessionRef` models one lightweight provider-native session reference for registries, indexes, and selection.
- `<Provider>.Session` models one native session and contains all provider-relevant facts about that session.
- Keep `Agentos.Session` provider-agnostic.
- Normalize provider-native sessions through explicit provider normalizers.
- Provider quirks belong in raw artifacts or `<Provider>.Session`, not in `Session.Model`.
- Cross-provider coordination belongs to Agentos-level services, not to provider sessions.
- Shared Agentos primitives are allowed only when they do not become a forced schema for every provider.
- Use `Relocation.Function` for private extracted implementation bodies that only exist to place code in a more natural file or module.
- Do not prescribe implementation mechanics in the concept model.

## Relationship To Current Implementation

The current `ProviderInstance` shape is transitional. It mixes configured actor data, launch config, home topology, session discovery, account behavior, and Chatlas behavior.

The target direction is to reduce `ProviderInstance` into a config/input bridge while moving durable model responsibility toward provider-native agents, provider-native sessions, and explicit normalizers.

## Related Concepts

- `Session.Model`
- `Chatlas.Standard.Model.Contract`
- `Project.Selection.Protocol`
- `Relocation.Function`

## Provenance

Promoted from `../live/560-agentos-agent-session-model-design-summary.md`.
