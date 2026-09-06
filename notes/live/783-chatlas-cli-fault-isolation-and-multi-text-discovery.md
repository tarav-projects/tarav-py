# Chatlas CLI fault isolation and multi-text discovery

Status: observed design gaps; no implementation started.

## Context

During a Reading Club capture, the Agent needed to discover several User Turn hashes from the current Codex session. The intended public command was:

```bash
tarav chatlas render \
  --provider codex \
  --current-session \
  --update \
  --side user \
  --text-contains "search text" \
  --order newest \
  --limit 20 \
  --renderer Chatlas.Turn.Ledger.Renderer
```

At that moment, this command failed before Chatlas executed:

```text
ImportError: cannot import name 'ASSERTION_TYPE_SELECTOR'
from 'tarav.scoring.model'
```

The Agent temporarily bypassed the public CLI by invoking `build_normal_model_from_row()` directly, normalizing the current native transcript in memory, joining Turns to Messages, and searching several literal fragments for their Turn hash prefixes.

The scoring import has since been repaired and the ordinary Chatlas path is healthy. Focused Chatlas tests pass. The investigation nevertheless exposed two still-reproducible design gaps.

## 1. Command-family fault isolation

Running any Tarav command first constructs the complete root parser. During this process, `TaravRuntime.register_commands()` imports every command family, including Chatlas, scoring, Diagram, and others.

Consequently, an import failure in one unrelated subsystem prevents every command from starting. Although the failed operation was `tarav chatlas render`, execution stopped while registering scoring commands.

A read-only fault-injection check against the current code confirms the vulnerability remains:

1. intercept the import of `tarav.scoring.commands` and raise a simulated `ImportError`;
2. call `tarav.cli.cli.build_parser()`;
3. parser construction fails with that unrelated scoring error.

Current location: `src/tarav/runtime.py`, inside `TaravRuntime.register_commands()`.

Desired property:

> A broken optional or unrelated command family should not prevent healthy command families from operating.

The implementation remains open. Dispatch may load only the selected command family, or registration failures may be isolated while preserving clear diagnostics for the broken family.

### Acceptance checks

1. Simulate a failure while importing scoring commands.
2. Invoke `tarav chatlas render --help`.
3. Confirm Chatlas remains usable.
4. Confirm invoking the broken scoring family reports its own failure clearly.

## 2. Repeated `--text-contains` silently discards values

The CLI currently defines one scalar `--text-contains` value. Argparse nevertheless accepts the option multiple times:

```bash
tarav chatlas render \
  ... \
  --text-contains "first phrase" \
  --text-contains "second phrase"
```

Observed behavior: only `"second phrase"` is applied; the earlier value is silently overwritten. A live check with two fragments that match different Turns returned only the Turn matching the second fragment.

Current surfaces:

- `src/tarav/chatlas/commands.py`: scalar argument definition;
- `src/tarav/chatlas/query.py`: `text_contains: str | None`.

Choose and document one explicit behavior:

- preferably support repeated values with OR semantics, so a Turn matches when it contains any supplied literal fragment; or
- reject repeated arguments with a clear error.

### Acceptance checks

1. Query with two text fragments matching different Turns.
2. Under OR semantics, confirm both Turns are returned once in the requested order.
3. Confirm case-insensitive literal matching remains unchanged.
4. Confirm one `--text-contains` remains backward compatible.
5. If repetition remains unsupported, confirm duplicate options fail instead of silently discarding input.

## Verification record

Current healthy-path checks:

- `tarav chatlas render --help`: pass;
- current-session `--update` plus literal Turn discovery: pass;
- ordered lookup of two Turn hash prefixes: pass;
- `tarav scoring --help`: pass;
- focused Chatlas suite (`test_core_cli.py`, `test_query.py`, `test_rendering.py`): 42 passed.

Current gap checks:

- simulated unrelated scoring import failure: root parser construction fails;
- repeated `--text-contains`: only the final value is honored.

