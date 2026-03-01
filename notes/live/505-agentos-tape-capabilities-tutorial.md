# AgentOS tape capabilities (live tutorial)

This tutorial shows the **current** `agentcli tape` interface in this repo and a practical end-to-end flow.

## 1) What `tape` supports today

`agentcli tape` has these subcommands:

- `init`
- `append`
- `append-batch`
- `path`
- `list`
- `summary`

## 2) Data model and invariants

Tapes are append-only JSONL files.

- Line 1 must be metadata with `entry_type: "tape.meta"`.
- Metadata `cargo` must include:
  - `tape_id` (UUID)
  - `tape_name` (string)
- Appended entries use:
  - `ts`
  - `writer` (`agent`, `skill`, `version`)
  - `workflow`
  - `entry_type` (must **not** be `tape.meta`)
  - `refs` (JSON array)
  - `cargo` (JSON object)

## 3) End-to-end walkthrough

### Step A: choose a path

```sh
uv run agentcli tape path \
  --dir notes/tapes \
  --tag todo-miner \
  --rotation monthly
```

You can also select an existing file instead of generating one:

```sh
uv run agentcli tape path \
  --dir notes/tapes \
  --tag todo-miner \
  --select latest \
  --filter-tag
```

### Step B: initialize the tape

```sh
uv run agentcli tape init \
  --tape notes/tapes/202602-todo-miner.jsonl \
  --workflow todo.scan \
  --tape-name "TODO miner findings" \
  --writer-agent codex \
  --writer-skill todo-miner \
  --writer-version 0.1.0 \
  --cargo-json '{"repo":"agentos"}'
```

Notes:
- `--ensure` makes init idempotent (returns existing metadata instead of erroring).
- `--tape-id` can be supplied explicitly; otherwise a UUID is generated.

### Step C: append one entry

```sh
uv run agentcli tape append \
  --tape notes/tapes/202602-todo-miner.jsonl \
  --workflow todo.scan \
  --entry-type todo.miner.finding \
  --writer-agent codex \
  --writer-skill todo-miner \
  --writer-version 0.1.0 \
  --cargo-json '{"file":"src/agentos/tape/commands.py","line":239,"text":"entry type validation"}' \
  --refs-json '[{"kind":"span","path":"src/agentos/tape/commands.py","line":239}]'
```

### Step D: append a batch atomically

```sh
uv run agentcli tape append-batch \
  --tape notes/tapes/202602-todo-miner.jsonl \
  --workflow todo.scan \
  --writer-agent codex \
  --writer-skill todo-miner \
  --writer-version 0.1.0 \
  --entries-json '[
    {"entry_type":"todo.miner.finding","cargo":{"file":"a.py","line":10},"refs":[]},
    {"entry_type":"todo.miner.finding","cargo":{"file":"b.py","line":25},"refs":[]}
  ]'
```

If any entry is invalid, the command returns an error and appends **none** of them.

### Step E: query and summarize

List by type:

```sh
uv run agentcli tape list \
  --tape notes/tapes/202602-todo-miner.jsonl \
  --entry-type todo.miner.finding \
  --last 20
```

Count only:

```sh
uv run agentcli tape list \
  --tape notes/tapes/202602-todo-miner.jsonl \
  --entry-type todo.miner.finding \
  --count
```

Summary:

```sh
uv run agentcli tape summary --tape notes/tapes/202602-todo-miner.jsonl
```

## 4) Practical capability map

- `path`: deterministic naming/selection for tape files.
- `init`: creates a valid metadata-first tape.
- `append`: writes one structured event.
- `append-batch`: validates all entries first, then writes all-or-none.
- `list`: filters/slices/counts entries (`--entry-type`, `--cargo-contains`, `--first/--last`, `--count`).
- `summary`: reports totals, per-type counts, first/last timestamps.
