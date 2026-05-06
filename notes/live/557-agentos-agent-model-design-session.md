# Agentos Agent Model - design-session

## Motivation

Design a provider-neutral Agentos agent model that can manage runnable agents across providers, accounts, homes, run profiles, and sessions.

The MVP should support running a simple prompt such as `say hi` on any accessible configured agent/provider/account/home combination, while keeping session tracking and auxiliary homes explicit so operational probes do not pollute tracked Chatlas history.

## Items

- Agentos.Agent: [in-progress] runnable configured agent; replaces Agent.Instance
  - Agent.Provider: [in-progress] provider family/spec, adapter responsibilities, capability declarations
  - Provider.Account: [fresh] auth/account identity, usage/account stats, secret boundaries
  - Agent.Home: [fresh] filesystem home roots, session storage, tracking policy, auxiliary homes
  - Agent.Session: [fresh] launched run/session identity, run file, transcript linkage, Chatlas relationship
  - Agent.RunProfile: [fresh] command/env/model/prompt execution profile for a runnable agent

## Agentos.Agent

Agentos.Agent is Agentos' internal model for a runnable provider CLI configuration.

It is not a new agent runtime. It is a provider-specific configuration object that lets Agentos correctly run an existing terminal interface such as `codex`, `claude`, `gemini`, or `pi`.

Core meaning:

```text
Agentos.Agent = enough provider-specific config to build and run the right command
```

Running an Agentos.Agent means:

```text
resolve config
build provider-native command
prepare env/home/account context
execute terminal command
record enough run metadata to relate the result to a session
```

Implementation is provider-specific:

```text
Codex.Agent
Claude.Agent
Gemini.Agent
Pi.Agent
...
```

The common layer should normalize Agentos control concepts: run request, resolved command, environment, home/account selection, run result, and session tracking policy.

It should not pretend providers share the same native account model, command syntax, session storage, or auth behavior.

The design direction is: config stays provider-neutral at the top level where possible, but loading that config produces a provider-specific Agentos.Agent object that knows how to run itself.

## Agent.Provider

Provider family/spec, adapter responsibilities, and capability declarations.

Agent.Provider is Agentos' provider-family definition and adapter boundary.

It is not a configured runnable agent, account, or home. It defines what Agentos knows about a provider family and which provider-specific services exist for that family.

Core meaning:

```text
Agent.Provider = provider-family spec + provider-specific adapter entrypoints
```

Provider behavior should be organized by subsystem using the conceptual shape:

```text
<Subsystem>.<family>.Provider
```

Examples:

```text
Agent.Codex.Provider
Home.Codex.Provider
Session.Codex.Provider
Account.Codex.Provider
Chatlas.Codex.Provider
```

These names are examples, not final API names.

It may define or route to provider-specific knowledge such as supported home slots, default run profile shape, session discovery support, account stats support, Chatlas/raw retention defaults, capability declarations, and provider-specific validation rules.

It should not contain user-specific configuration. User-specific provider usage belongs to Agentos.Agent, Provider.Account, Agent.Home, or Agent.Session.

## Provider.Account

Auth/account identity, usage/account stats, and secret boundaries.

Early framing: account represents the provider-side credential or billing identity. It should be explicit instead of inferred only from environment variables or home directory contents.

## Agent.Home

Filesystem home roots, session storage, tracking policy, and auxiliary homes.

Early framing: home is the provider filesystem/state root used by an agent. It should support durable tracked homes and auxiliary homes for probes, stats refreshes, and disposable sessions.

## Agent.Session

Launched run/session identity, run file, transcript linkage, and Chatlas relationship.

Early framing: session is the result of running an `Agentos.Agent`. It should link the run request, provider-native session artifacts, and any Chatlas/session-model representation without making Chatlas the runtime authority.

## Agent.RunProfile

Command/env/model/prompt execution profile for a runnable agent.

Early framing: run profile owns launch mechanics such as executable, fixed args, prompt passing, model flags, environment rendering, and run modes. It prevents `Agentos.Agent` from becoming a flat provider-specific launch blob.

## Notes

- Current code already has an overloaded `agent.instances[]` / `ProviderInstance` shape that mixes launch config, home topology, session discovery, and account behavior.
- Current design direction is to replace `Agent.Instance` with `Agentos.Agent` as the runnable object.
- Provider infra implementation request: `notes/live/558-agent-provider-infra-redesign-impl-req.md`.

## End Log

- 2026-05-06: Created session with initial component list approved in chat.
- 2026-05-06: Updated Agentos.Agent and Agent.Provider to in-progress; captured provider subsystem-adapter direction and linked provider infra impl-req.
