# Agentos Agent Session Model - design-summary

## Summary

Agentos should model provider integration around two provider-native anchors: `<Provider>.Agent` and `<Provider>.Session`. The design keeps the core object model small while allowing provider-specific extensions and shared primitives where they genuinely fit.

## Accepted Decisions

1. Use `<Provider>.Agent` as the provider-native configured actor.
   This replaces the direction of many sibling top-level objects with one provider-specific anchor that can support running, Chatlas, accounts, home handling, and related subsystem behavior.

2. Use `<Provider>.Session` as the provider-native session artifact model.
   This is the missing middle layer between raw provider files/events and the provider-agnostic Agentos session model.

3. Keep `Agentos.Session` provider-agnostic.
   Agentos standard session data is normalized output, not the native session shape for Codex, Claude, Pi, or any other provider.

4. Use `Chatlas.Normalizer.<Provider>` for provider-specific conversion.
   Normalizers convert provider-native sessions into `Agentos.Session` / Chatlas standard model data without making `<Provider>.Session` own the normalized model.

5. Attach subsystem behavior as provider-agent extensions when useful.
   Examples include `<Provider>.Agent.Runner`, `<Provider>.Agent.Chatlas`, `<Provider>.Agent.Accounts`, and `<Provider>.Agent.Home`. These are focused extensions of the provider agent, not separate top-level model anchors.

6. Share primitives, not forced schemas.
   Agentos can reuse primitives such as `ProviderFamily`, `ConfigSource`, `HomeSlot`, terminal command data, run request/result data, and raw artifact policy, but provider-specific objects decide how those primitives apply.

7. Avoid overspecifying implementation mechanics in the model.
   The design should describe anchors, relationships, and conversion boundaries, not prescribe readiness methods or object construction mechanics.

## Execution Plan

1. Introduce explicit provider-native session objects.
   Add or design `Codex.Session`, `Claude.Session`, `Pi.Session`, and equivalent provider session shapes as the native input boundary for normalization.

2. Align Chatlas normalizers around provider sessions.
   Refactor or document existing provider-specific normalizers so their conceptual input is `<Provider>.Session`, even if implementation remains incremental.

3. Continue evolving `<Provider>.Agent` as the provider actor anchor.
   Move current overloaded provider-instance responsibilities behind provider-agent extensions where useful, starting with runner behavior because `agent run` already exists.

4. Reduce the role of the transitional `ProviderInstance` shape.
   Treat it as a config/input DTO or migration bridge rather than the long-term model for every provider capability.

5. Promote durable concepts into index notes after implementation proves the shape.
   The live design summary should guide near-term refactoring, while final durable design truth belongs in `notes/index/`.

## Deferred Items

- Full config schema redesign for provider agents.
- Complete account/home/runner/session implementation details for each provider.
- Naming final Python classes and modules for every provider-specific object.
- Removing all existing `agent.instances[]` support in one step.
- Defining non-Chatlas consumers of `<Provider>.Session`.

## Relevant Files Or Surfaces

- `notes/live/557-agentos-agent-model-design-session.md`
- `notes/live/558-agent-provider-infra-redesign-impl-req.md`
- `src/agentos/agent/providers.py`
- `src/agentos/agent/run_profiles.py`
- `src/agentos/chatlas/session_model/`
- `src/agentos/chat/providers.py`

## Open Questions

- Which provider should receive the first explicit `<Provider>.Session` implementation?
- Should `Chatlas.Normalizer.<Provider>` be the durable concept name, or should the index use a more general `Agentos.Session.Normalizer.<Provider>` concept?
- How narrow should `ProviderInstance` become before it is renamed or replaced?

## End Log

- 2026-05-08: Created after converging on provider-native `Agent` and `Session` anchors, provider-agnostic `Agentos.Session`, and `Chatlas.Normalizer.<Provider>` conversion.
