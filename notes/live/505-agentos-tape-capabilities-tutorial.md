# AgentOS tape capabilities (live tutorial)

This tutorial describes the current unified `agentos tape` interface.

## 1) What `tape` supports today

`agentos tape` subcommands:

- `init`
- `append`
- `append-batch`
- `consolidate`
- `query`
- `verify`
- `config`
- `doctor`

## 2) Tape model

Each tape is a folder with:

- `tape.manifest.json` (config only)
- `segments/*.jsonl` (committed records)
- `staging/*.jsonl` (per-writer staged records)

The interface treats this as one logical tape.

## 3) Target resolution

You can target a tape in two ways:

- Project mode: `--tape <name>` resolves to `<project>/.agentos/tapes/<name>/`
- Headless mode: `--root <folder>` uses an explicit tape folder path

Project mode requires being inside an AgentOS project (`agentos init`).

## 4) Write semantics (`--init`)

Write commands are:

- `append`
- `append-batch`
- `consolidate`

Behavior:

- If tape is missing and `--init` is not passed: command fails.
- If tape is missing and `--init` is passed: tape is created with init/default config.
- If tape exists and explicit init options mismatch existing config: command continues with warnings.
- If tape exists with non-default config and no explicit init options: command continues with warnings.

## 5) End-to-end flow (project mode)

Initialize project and tape:

```sh
uv run agentos init --scope project --root .
uv run agentos tape init --tape bla --naming sequential --max-records-per-segment 1000
uv run agentos tape init --tape bla --tape-class events.demo --data-schema-json '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["k"],"properties":{"k":{"type":"string"}},"additionalProperties":false}'
```

Append one record:

```sh
uv run agentos tape append \
  --tape bla \
  --writer-id proc-a \
  --class event.alpha

uv run agentos tape append \
  --tape bla \
  --writer-id proc-a \
  --class event.alpha \
  --data-json '{"k":"v"}'

# optional timestamp override (otherwise created_at is auto-generated)
uv run agentos tape append \
  --tape bla \
  --writer-id proc-a \
  --class event.alpha \
  --override-created-at 2026-03-01T10:11:12Z
```

Append a batch:

```sh
uv run agentos tape append-batch \
  --tape bla \
  --writer-id proc-a \
  --entries-json '[
    {"class":"event.beta"},
    {"class":"event.gamma"}
  ]'
```

Consolidate staged records into committed segments:

```sh
uv run agentos tape consolidate --tape bla
```

Read committed or best-effort:

```sh
uv run agentos tape query --tape bla --mode committed --count
uv run agentos tape query --tape bla --mode best_effort --with-source --last 20
# one-call convenience: consolidate before querying committed view
uv run agentos tape query --tape bla --mode committed --count --consolidate
```

Verify segment header consistency:

```sh
uv run agentos tape verify --tape bla
```

Inspect effective config and health:

```sh
uv run agentos tape config --tape bla
uv run agentos tape doctor --tape bla
```

## 6) Headless mode example

If no project context is available, target a folder directly:

```sh
uv run agentos tape append \
  --root /tmp/demo-tape \
  --writer-id proc-headless \
  --class event.headless \
  --init
```

## 7) Naming and ordering notes

- Segment filenames are configured by naming strategy (`sequential`, `monthly`, `daily`):
  - `sequential`: `0001.jsonl`, `0002.jsonl`, ... and honors `max_records_per_segment`
  - `monthly`: `YYMM.jsonl` and rolls only when month changes
  - `daily`: `YYMMDD.jsonl` and rolls only when day changes
- Segment metadata stores `segment_filename`, and `verify` checks it matches the actual file.
- Read ordering is best-effort and primarily driven by `created_at`; strict global ordering is not guaranteed.
