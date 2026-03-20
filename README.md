# agentos

Core library for agentic workflow primitives, with a companion CLI.

Current baseline includes:
- project context commands: `init`, `rev-parse`, and scope-aware `doctor`
- `tara-tapes` for Tara spec-first tape operations
- `tape` and `git-refs` (from `obacli`)
- `mdblocks`, `prefix`, `skills`, `utils`, `doctor`, `test`

`agentos` is the core Python package/library.
`agentos` is the CLI entrypoint/layer.

## Utils CLI

`agentos utils` exposes small agent-facing helpers:

- `uuid`: generate one or more UUIDv4 values (`--count`, `--json`)
- `tmp-folder new`: allocate a unique path under `<project>/.agentos/tmp/` (`--create` optional)

## Skills CLI

`agentos skills` exposes local skills-directory helpers:

- `list`: print discovered top-level skill directory names (`--json` optional)
- `path`: print the skills root path or a specific skill path
- `flatten [root]`: walk nested skill folders in any nested layout, including hidden directories and symlinked bundles, and create top-level symlinks for nested `SKILL.md` directories (defaults to current working directory)
- `flatten --dry-run`: print planned symlink creations or replacements without writing filesystem changes
- `flatten --overwrite`: replace conflicting destination symlinks instead of skipping them; non-symlink conflicts still warn and are left untouched
- `prune [root]`: recursively remove broken symlinks under a skills root without following working symlink targets (defaults to current working directory)
- `prune --dry-run`: print broken symlinks that would be removed without writing filesystem changes
- Existing root-path collisions are skipped: matching destination symlinks are reported as `info`, everything else as `warn`, with both source and destination paths reported.

## Tape CLI (folder-backed default)

`agentos tape` uses a single interface for folder-backed JSONL tapes.

Subcommands:
- `init`
- `append`
- `append-batch`
- `consolidate`
- `query`
- `verify`
- `config`
- `doctor`

Target selection:
- Project mode: `--tape <name>` resolves to `<project>/.agentos/tapes/<name>/`
- Headless mode: `--root <path>` targets an explicit tape folder

Write behavior:
- `append`, `append-batch`, `consolidate` error if tape is missing
- Pass `--init` to allow implicit initialization on missing tape
- If explicit init flags mismatch existing config, command succeeds with warnings
- If no explicit init flags are passed and existing config is non-default, command warns

Naming behavior:
- `sequential` uses `max_records_per_segment` for rollover (`0001.jsonl`, `0002.jsonl`, ...)
- `monthly` rolls strictly by month (`YYMM.jsonl`) and ignores `max_records_per_segment`
- `daily` rolls strictly by day (`YYMMDD.jsonl`) and ignores `max_records_per_segment`

Quick examples:

```sh
# project-scoped tape
uv run agentos tape init --tape bla
uv run agentos tape init --tape bla --tape-class events.demo --data-schema-json '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["k"],"properties":{"k":{"type":"string"}},"additionalProperties":false}'
uv run agentos tape init --tape bla --allowed-classes-json '["event.alpha","event.beta"]'
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha --data-json '{"k":"v"}'
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha --override-created-at 2026-03-01T10:11:12Z
uv run agentos tape consolidate --tape bla
uv run agentos tape query --tape bla --mode best_effort --count
uv run agentos tape query --tape bla --mode committed --count --consolidate
uv run agentos tape query --tape bla --mode best_effort --jmes "[?data.task_id=='task-123']"
uv run agentos tape config --tape bla
uv run agentos tape doctor --tape bla

# headless explicit root
uv run agentos tape append --root /tmp/my-tape --writer-id proc-a --class event.alpha --init
```

## Tara Tapes CLI

`agentos tara-tapes` is a separate, spec-first subsystem for Tara-compliant tapes.
The initial surface uses explicit `--root` targeting only.

Subcommands:
- `init`
- `manifest`
- `append`
- `commit`
- `segments`
- `read-segment`
- `scan`
- `verify`

Quick examples:

```sh
agentos tara-tapes init --root /tmp/my-tara-tape --tape-name demo
agentos tara-tapes append --root /tmp/my-tara-tape --writer-id proc-a --segment session.jsonl --record-json '{"class_id":"var.inline","value":42}'
agentos tara-tapes commit --root /tmp/my-tara-tape
agentos tara-tapes segments --root /tmp/my-tara-tape
agentos tara-tapes read-segment --root /tmp/my-tara-tape --segment session.jsonl
agentos tara-tapes scan --root /tmp/my-tara-tape
agentos tara-tapes verify --root /tmp/my-tara-tape
```
