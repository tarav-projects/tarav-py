# agentos

Core library for agentic workflow primitives, with a companion CLI.

Current baseline includes:
- project context commands: `init`, `rev-parse`, and scope-aware `doctor`
- `tape` and `git-refs` (from `obacli`)
- `mdblocks`, `prefix`, `skills`, `utils`, `doctor`, `test` (from `devcli`)

`agentos` is the core Python package/library.
`agentos` is the CLI entrypoint/layer.

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
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha --data-json '{"k":"v"}'
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha --override-created-at 2026-03-01T10:11:12Z
uv run agentos tape consolidate --tape bla
uv run agentos tape query --tape bla --mode best_effort --count
uv run agentos tape query --tape bla --mode committed --count --consolidate
uv run agentos tape config --tape bla
uv run agentos tape doctor --tape bla

# headless explicit root
uv run agentos tape append --root /tmp/my-tape --writer-id proc-a --class event.alpha --init
```
