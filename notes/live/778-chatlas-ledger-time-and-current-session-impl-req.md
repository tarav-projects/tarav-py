# 778 — Chatlas ledger time and current-session identity

Status: Completed

## Impl.Abstract

Add visible temporal context to `Chatlas.Turn.Ledger.Renderer` without moving resolution into presentation, and expose the existing verified harness-session resolver as a read-only Chatlas command for both Codex and Claude Code.

The Query engine will resolve each selected Turn's earliest valid referenced Event `started_at`. The ledger will format that value in UTC and render `-` when it is unavailable; it will not infer time from observation or file timestamps.

`tarav chatlas current-session --provider <provider> --json` will return the provider-native session ID obtained from the provider's verified harness context. It will not capture, update, or infer a neutral Chatlas identity. The session-ID skill will use this command before updating and resolving the exact Normal Model session.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Collection: `778.Impl.Req` — `be9da9d9-cd8f-4a06-a0d0-4287b4bf1805`
- Draft: `311520fb-8529-4e76-9f61-5f585b157bd0`
- Authorization Gate: `18bcc9c1-2361-4ec5-9949-79130538892a`

## Execution.Plan

1. Extend Chatlas Query findings with the earliest valid `started_at` from each Turn's mechanically resolved Event references. Check reference integrity, timezone-aware parsing, actual instant ordering, and explicit absence.
2. Format that Query-owned value in `Chatlas.Turn.Ledger.Renderer` as UTC minute precision, retaining `-` for unavailable time. Check that renderers perform no Event lookup.
3. Add `tarav chatlas current-session` over the existing provider resolver for `codex` and `claude-code`; update the session-ID skill to use it. Check provider-specific success, ambiguous/no-context failures, and read-only behavior.
4. Reinstall the editable CLI and run focused, Chatlas, Ruff, full-suite, skill validation, and live command checks.

Risks: duplicating session-resolution logic, accepting unverified ambient hints, turning rendering into selection, or substituting a weaker timestamp.

Deviation triggers: Normal Model Events do not expose a stable `started_at`, or the provider adapters require a different verified identity boundary.

Acceptance signals:

- Query findings expose `started_at` resolved from Turn Event references.
- Multi-Event Turns select the earliest valid absolute instant.
- The ledger shows timezone-explicit UTC time or `-`.
- `current-session` works for both registered harness providers and does not write.
- The session-ID skill uses the surfaced command instead of directly reading provider environment variables.

## Impl.Log

- Existing Query already owns Turn/Message assembly, while the ledger owns only string presentation; Event time follows the same boundary.
- Existing `--current-session` query/update mechanics already use one exact resolver for Codex and Claude Code. The new command surfaces that resolver rather than adding another identity mechanism.
- The preceding `777` product changes remain uncommitted and will enter this workflow's required pre-edit checkpoint.
- Workflow checkpoint: `131677a`.
- Query findings now resolve Turn Event references, validate their addresses and hashes, and retain the earliest valid timezone-aware `started_at` by absolute instant.
- `Chatlas.Turn.Ledger.Renderer` formats the resolved value at UTC minute precision and emits `-` for absence; it performs no Event lookup.
- Added the read-only `tarav chatlas current-session` command over the existing verified resolver. Live Codex and isolated Claude Code checks returned their provider-native session identities.
- Updated `tarav-chatlas-my-session-id` to use the surfaced command and documented it in the Chatlas package skill.
- Verification: `42` targeted tests passed; `78` Chatlas tests passed; Ruff clean; full suite `1553` passed; skill validation passed; editable CLI reinstalled and live ledger/current-session checks passed.
- Product surfaces: `src/tarav/chatlas/{commands,query,rendering}.py`, their focused tests, and the two Chatlas skill surfaces.
- Applied the closed `778.Impl.Req` Draft once. Diagram receipt commit: `fa8ca9a919c4356d7a82ed7c1cbcc4cb16bd79e6`.
- Expected capture POIs remain for unasserted records, unavailable Archive-grounding assessment, Model staleness, and older closed implementation collections. The new Collection is closed and introduced no closed-write finding of its own.
