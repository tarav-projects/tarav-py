# 777 — Chatlas Query update preflight

Status: Designed

## Impl.Abstract

Connect Chatlas `query` and `render` to the existing capture/update system through an explicit `--update` flag. The flag performs one exact-session update before querying and then reads a fresh Normal Model.

The distinction is intentional:

- `--update` captures provider data and updates the session index; it writes.
- `--refresh` rebuilds the Normal Model from retained data.
- neither flag keeps Query read-only.

Initial update targets are deliberately exact: `--provider` plus either `--current-session` or `--session-id`. Identity-hash update resolution and implicit provider selection are out of scope.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Collection: `777.Impl.Req` — `e76116a6-e2a8-417f-ad0c-bbf9f93aca04`
- Draft: `823f0202-a20d-410b-83a0-6535938495fe`
- Authorization Gate: `6304b010-e1ba-490b-9ca0-4306dc1216d2`

## Execution.Plan

1. Add `--update` to the shared Query/Render options and validate the mechanically exact target before any write. Check CLI failure behavior for missing provider and unsupported identity-hash targeting.
2. Reuse `chatlas_update` for the selected provider/session, preserve update progress on stderr, then force the query reader to refresh. Check that Query and Render both see newly captured data through the same path.
3. Reinstall the editable CLI, exercise the current-session command live, and run focused, Chatlas, and proportional repository tests.

Risks: accidentally broad provider scanning; querying a stale Normal Model after capture; polluting renderer stdout with update output; or duplicating update mechanics.

Deviation triggers: exact update cannot be expressed through the existing update function, or refreshing after update requires a new cache/index architecture.

Acceptance signals:

- `query` and `render` both expose `--update`.
- `--provider codex --current-session --update` captures only that session before querying.
- `--provider codex --session-id <id> --update` follows the same path.
- `--update` without an explicit provider or with `--identity-hash` fails before mutation.
- `--refresh` remains independent and read-only.
- update progress stays on stderr and rendered/JSON results stay on stdout.

## Impl.Log

- Current product already centralizes Query/Render execution in `src/tarav/chatlas/commands.py::_run_query_renderer` and capture in `chatlas_update`; no new update subsystem is needed.
- The preceding `776` implementation remains uncommitted and will be included in this workflow's required pre-edit checkpoint.
- Product capture will remain in the durable Draft and land once after verification.
