# 631 · agent profiles CLI surface · Impl.Req

## Impl.Abstract

**Scope:** Add a `profiles` subcommand group to `agentos agent` with two subcommands: `new` (scaffold a template profile file) and `show` (print raw profile JSON).

**Status:** Ready for execution.

**Source context:** Post-630 cleanup session. Profile files at `~/.agentos/profiles/<id>.json` are now the sole source of truth for named agents. The write side of this system has no CLI surface — profiles must be created by hand. The design session established that hand-editing small JSON is acceptable, but a template scaffold and a raw-print command are the right minimal additions.

**Out of scope:** `agent list` is unchanged — it already reads from profile files and is the canonical listing surface. No profile edit, delete, or validation commands.

---

## Impl.Index

### Block: `profiles` subcommand group

The `agentos agent` surface already has a `accounts` subgroup (nested subparsers). The `profiles` group follows the same pattern.

Registration point: `register_agent_commands()` in `agentos-py/src/agentos/agent/commands.py:779`.

Existing parallel: `accounts_parser` and `accounts_subparsers` (lines 811–815) are the direct structural model.

### Block: CLI argument convention

All `profiles` subcommands take options, not positional args. Match the rest of the `agent` surface (`--profile`, `--provider`, `--account`).

### Block: `profiles new --id <id>`

Stdout-only — writes no file. Prints the destination path on the first line, then the template JSON.

- **With `--id`:** path is `~/.agentos/profiles/<id>.json`, template `id` field is set to `<id>`.
- **Without `--id`:** path is `~/.agentos/profiles/<id>.json` (literal `<id>` in the filename), template `id` field is `"<id>"`.

The agent or user reads the path from line one and the JSON body from the rest, then writes the file themselves (likely after replacing `<provider>`). This avoids poisoning `agent list` with half-filled scaffolds: the loader strictly validates `provider`, so any written-but-unedited template would break list/run for the whole system.

Template content (all fields the profile system recognises):

```json
{
  "schema_version": 1,
  "id": "<id-or-actual>",
  "provider": "<provider>",
  "label": "",
  "home": "",
  "cli_command": [],
  "default_model": "",
  "model_flag": "",
  "run_args": [],
  "env": {}
}
```

`schema_version: 1` matches what `write_agent_profile()` emits (config.py:328). Only `provider` is strictly required at runtime; everything else is optional. The template includes all optional fields as empty placeholders so the user/agent knows what's available.

Profile location: `profiles_root() / f"{id}.json"` — `profiles_root()` is already in `config.py:273`.

Validation: run `validate_string_for_path` on the id when provided (same guard used in `profile_path()`).

### Block: `profiles show --id <id>`

`--id` is required. Reads `profile_path(id)` and prints the file content verbatim (`print(path.read_text())`) — no re-parsing, no re-formatting. Fails with a clear error if the profile does not exist.

---

## Execution.Plan

### Slice 1 · `profiles` subgroup skeleton + `show`

**What changes:**
- In `commands.py`, after the `accounts` block, register a `profiles` subparser group.
- Add `profiles show` subcommand with required `--id`: prints the verbatim file content at `profile_path(id)`, errors if missing.

**Observable result:** `agentos agent profiles show --id codex-main` prints the raw text of `~/.agentos/profiles/codex-main.json`.

**Check:** Run the command against an existing profile. Run against a nonexistent id and confirm clean error.

---

### Slice 2 · `profiles new`

**What changes:**
- Add `profiles new` subcommand with optional `--id`: validates id when present, prints the destination path on line one, then the template JSON. Writes no file.

**Observable result:**
- `agentos agent profiles new --id zz-test` prints `~/.agentos/profiles/zz-test.json` followed by the template with `"id": "zz-test"`.
- `agentos agent profiles new` (no id) prints `~/.agentos/profiles/<id>.json` followed by the template with `"id": "<id>"`.
- `agent list` is unaffected because no scaffold file is written.

**Check:** Verify both invocations print path + template. Verify no files are created. Verify `agent list` continues to work after running `profiles new`.

---

## Impl.Log

- 2026-06-05: Slice 1 implemented. Added `_cmd_agent_profiles_show` handler in `commands.py` after `_cmd_agent_list`. Registered `profiles` subparser group with `show` subcommand (required `--id`) between the accounts and run blocks. Imported `profile_path`, `profiles_root`, `validate_string_for_path`. Verified: `profiles show --id codex-main` prints raw file content, `profiles show --id no-such-profile` errors cleanly with exit 1.
- 2026-06-05: Slice 2 implemented. Added `_cmd_agent_profiles_new` and `_agent_profile_template` helper. Registered `new` subcommand with optional `--id`. **Design deviation during execution:** initial implementation wrote the scaffold file directly when `--id` was given, which poisoned `agent list` (the strict provider-family validator rejects the literal `"<provider>"` placeholder, breaking list/run for all profiles). Resolved by switching `new` to stdout-only for both branches — prints the destination path on line one, then the template JSON. Verified: both invocations work, no files written, `agent list` unaffected.
