# 776 — Chatlas Turn discovery and current-session scope

Status: Designed

## Impl.Abstract

Implement the smallest general Chatlas extension that lets an Agent discover Turns within one resolved session and address its own running session without manually supplying the provider-native session ID.

The recommended current-session invocation remains provider-explicit:

```sh
tarav chatlas query --provider codex --current-session ...
```

Provider inference is a convenience only when one verified harness context exists. Query remains read-only; capture/update remains an explicit write.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Collection: `776.Impl.Req` — `86fc658c-e9ab-4c55-84e9-c8219d3e45e5`
- Draft: `e746c9da-0b51-4f05-b75e-4b52e2ade3ba`
- Authorization Gate: `14f6dbcb-428e-46eb-bb33-beb9e8f4549c`

The Draft hosts two implementation-specific Lines attached semantically to `Context.Provider` and `Availability.And.Resolution`.

## Execution.Plan

1. Extend `ChatlasQuery` with bounded Turn discovery inside one exact session: side, literal text, order, and limit. Preserve exact prefix lookup.
2. Add `--current-session` to exact-session Chatlas commands. Resolve only verified harness variables; recommend explicit `--provider`; never guess from recency, cwd, or process activity.
3. Add a compact Turn-ledger renderer, CLI and unit tests, editable reinstall, and live command checks.

## Boundaries

Excluded: a query DSL, semantic search, corpus-wide indexing, project inference, newest-session guessing, automatic Reference repair, and automatic query-time capture/update.

Deviation triggers: discovery requires an index outside one Normal Model; harness identity cannot be resolved without provider-specific logic escaping Chatlas; or exact-prefix behavior would become ambiguous.

## Acceptance.Signals

- Exact prefix queries retain their ordered one-to-one behavior and errors.
- A query without prefixes can find bounded User or Agent Turns by literal text.
- `--provider codex --current-session` resolves `CODEX_THREAD_ID`; the equivalent Claude Code path resolves `CLAUDE_CODE_SESSION_ID`.
- Missing or ambiguous harness context fails explicitly.
- Query and render share selection; renderer code does not perform finding.
- Focused and proportional tests pass.

## Impl.Log

- Grounded the Tarav Model at Diagram commit `3d6db4d717eb1699f0fed0ba63b9c5de12107b99`.
- The existing session View targets `Pdf.Readings`, so direct Block rendering supplied the Tarav context. This is a contextualization POI, not product scope for this slice.
- Product capture will be reconciled in the durable Draft and applied once when the implementation converges.
