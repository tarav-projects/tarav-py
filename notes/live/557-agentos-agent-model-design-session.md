# Agentos Agent Model - design-session

## Motivation

Design an Agentos agent/session model that can manage provider-native agents and sessions while keeping provider-agnostic outputs explicit.

The current converged direction is captured in `notes/live/560-agentos-agent-session-model-design-summary.md`: use two provider-native anchors, `<Provider>.Agent` and `<Provider>.Session`, with subsystem extensions under those anchors where useful.

## Items

- Agentos.Agent / Provider.Agent: [converging] provider-native configured actor; replaces Agent.Instance
- Provider.Session: [converging] provider-native session artifact model
- Agentos.Session / Session.Model: [converging] provider-agnostic normalized session model
- Chatlas.Normalizer: [converging] provider-specific conversion from Provider.Session to Agentos.Session
- Provider.Agent extensions: [in-progress] subsystem extensions such as Runner, Chatlas, Accounts, and Home

## Agentos.Agent / Provider.Agent

Agentos.Agent is the abstract Agentos concept for a provider-native configured actor. The concrete model is provider-specific:

```text
Codex.Agent
Claude.Agent
Gemini.Agent
Pi.Agent
...
```

It is not a new agent runtime. It is the Agentos model for a configured provider actor that can support provider-specific tasks such as running, Chatlas capture, account checks, home resolution, and session discovery.

Core meaning:

```text
<Provider>.Agent = provider-native configured actor
```

The base provider agent should stay small. Subsystem-specific data and behavior can attach as provider-agent extensions when useful:

```text
<Provider>.Agent.Runner
<Provider>.Agent.Chatlas
<Provider>.Agent.Accounts
<Provider>.Agent.Home
```

This keeps the model from spreading into many sibling top-level objects while preserving room for provider-specific complexity.

## Provider.Session

Provider.Session is the provider-native session artifact model.

It is the missing middle layer between raw provider files/events and the provider-agnostic Agentos session model. It captures native provider facts such as ids, paths, event streams, SQLite rows, timestamps, workspace hints, and raw artifact references where those exist.

Core meaning:

```text
<Provider>.Session = provider-native session facts
```

Examples:

```text
Codex.Session
Claude.Session
Pi.Session
OpenCode.Session
```

Provider.Session is not the normalized standard model.

## Agentos.Session / Session.Model

Agentos.Session is the provider-agnostic normalized session model. In the current index surface, this is represented by `Session.Model`.

It is derived from provider-native sessions through provider-specific normalization. It should not absorb provider-native quirks that belong in `<Provider>.Session` or raw artifacts.

Boundary:

```text
raw provider artifacts
  -> <Provider>.Session
  -> Agentos.Session / Session.Model
```

## Chatlas.Normalizer

Chatlas.Normalizer is the provider-specific conversion boundary.

It converts:

```text
<Provider>.Session -> Agentos.Session / Session.Model
```

This keeps native session shape out of the normalized model while preserving a clear conversion point for Codex, Claude, Pi, Copilot, OpenCode, and other providers.

## Provider.Agent Extensions

Subsystem behavior can extend the provider agent when useful:

```text
<Provider>.Agent.Runner
<Provider>.Agent.Chatlas
<Provider>.Agent.Accounts
<Provider>.Agent.Home
```

These are not separate top-level model anchors. They are focused extensions of the provider agent for specific Agentos subsystems.

## Notes

- Current code already has an overloaded `agent.instances[]` / `ProviderInstance` shape that mixes launch config, home topology, session discovery, and account behavior.
- Current design direction is to replace `Agent.Instance` with provider-native `<Provider>.Agent` as the configured actor.
- Provider infra implementation request: `notes/live/558-agent-provider-infra-redesign-impl-req.md`.
- Converged design summary: `notes/live/560-agentos-agent-session-model-design-summary.md`.

## End Log

- 2026-05-06: Created session with initial component list approved in chat.
- 2026-05-06: Updated Agentos.Agent and Agent.Provider to in-progress; captured provider subsystem-adapter direction and linked provider infra impl-req.
- 2026-05-08: Reconciled session with the converged design summary. Superseded the earlier sibling-object framing (`Provider.Account`, `Agent.Home`, `Agent.Session`, `Agent.RunProfile`) with provider-native `Agent` and `Session` anchors plus provider-agent subsystem extensions.
