# Skills Import Depot-Linking - impl-req

## Impl-Req State

Ready for implementation; the design is converged and should be implemented as the new default behavior for `agentos skills import`.

## User Intent

Change `agentos skills import` so the default import mode links project depot directories to a shared generated depot under Agentos home, instead of materializing per-skill symlinks separately in every project depot.

The new default mode is `depot-linking`. The current behavior remains available explicitly as `flat-linking`.

## Why This Exists

The current import behavior creates per-skill symlinks in every configured project depot, such as `.agents/skills` and `.claude/skills`. That is laborious to refresh across many projects and makes global updates harder.

With `depot-linking`, projects with the same import configuration point their depot paths at the same global generated depot. Updating that global depot updates all projects that use the same config-derived depot.

## Current Situation

`agentos skills import` currently resolves the selected skills catalog and then syncs each configured depot root directly. The core mechanics are in `src/agentos/skills/routing.py`:

- `import_selected_skills(...)`
- `_plan_profile_depot_sync(...)`
- `_apply_profile_depot_sync(...)`

The CLI command is wired in `src/agentos/skills/commands.py` through `_cmd_skills_import(...)` and the `skills import` parser.

Current tests for import behavior live primarily in `tests/test_skills_commands.py`.

## Requested Change

Add a command-only import mode option to `agentos skills import`:

- `--mode depot-linking`
- `--mode flat-linking`

`depot-linking` must be the default when `--mode` is omitted.

In `flat-linking`, preserve the current behavior: each configured project depot is a real directory containing per-skill symlinks to selected source skills.

In `depot-linking`, implement this sequence:

1. Resolve the same selected skills catalog and configured project depot roots as today.
2. Derive a stable hash from the import configuration identity that determines the selected skill symlink set.
3. Build or refresh a global depot at `~/.agentos/skills/depots/<hash>`.
4. Build that global depot using the same internal mechanics currently used by `flat-linking`.
5. Replace or update each configured project depot path so it is a symlink to the global depot.

The global depot is not a different kind of depot. It is the same flat symlink depot produced at a different root, then project depot paths point to it.

## Constraints And Invariants

- The global depot must be created by the existing flat symlink generation mechanics. Do not fork separate depot-content logic.
- `agentos skills import` in `depot-linking` must refresh the global depot every time it runs to reduce stale shared state.
- The import config should not gain a mode field. Mode is command-only.
- `depot-linking` is intentionally floating. If the shared global depot changes, every project linked to it changes. This is desired behavior.
- Projects that need frozen behavior should use a more specific or pinned import config, which should naturally produce a distinct config hash and global depot.
- The hash should not include project depot target paths or the command mode. Different projects with the same selected-skill import configuration should share a depot.
- `flat-linking` should remain available for one-off compatibility through `agentos skills import --mode flat-linking`.
- Existing conflict handling should remain crisp. Replacing an existing non-generated or non-symlink project depot path must not silently destroy user data.
- Follow the repository compatibility policy: do not add legacy aliases or compatibility layers unless explicitly requested.

## Out Of Scope

- Adding mode selection to the import config.
- Lockfile or frozen-depot semantics.
- Warnings when global depot membership changes.
- Separate commands for refreshing global depots.
- Backward-compatibility command aliases beyond the explicit `--mode flat-linking`.

## Acceptance Signals

- `agentos skills import` defaults to `depot-linking`.
- `agentos skills import --mode depot-linking` behaves the same as the default.
- `agentos skills import --mode flat-linking` preserves the previous per-project symlink depot behavior.
- In `depot-linking`, configured project depot paths such as `.agents/skills` and `.claude/skills` become symlinks to `~/.agentos/skills/depots/<hash>`.
- The global depot contains the per-skill symlinks that project depots used to contain directly.
- Re-running `agentos skills import` refreshes the global depot before wiring project depot paths.
- Two projects with the same relevant import configuration share the same global depot hash.
- Tests cover default `depot-linking`, explicit `flat-linking`, repeated refresh behavior, conflict behavior, and CLI help/argument validation.
- After CLI changes, refresh the installed executable with `uv tool install --reinstall --editable .`.

## Relevant Files Or Surfaces

- `src/agentos/skills/commands.py`
- `src/agentos/skills/routing.py`
- `src/agentos/skills/catalog.py`
- `tests/test_skills_commands.py`
- `agentos skills import`
- `agentos skills status`
- `agentos skills path --depot`
- `~/.agentos/skills/depots/<hash>`

Related design context:

- `notes/live/archived/523-skills-depot-design.md`
- `notes/live/archived/522-global-skills-imports-fallback-design.md`
- `notes/live/archived/521-skills-path-resolution-design.md`

## Open Questions

None blocking.

## Related Impl-Reqs

None known.

## End Log

- 2026-04-30: Created from design discussion. Accepted contract: command-only `--mode`, default `depot-linking`, explicit `flat-linking`, and global depot creation must reuse the current flat symlink depot mechanics.
