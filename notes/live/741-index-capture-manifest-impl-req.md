# 741 — One manifest for complete Index capture

## Impl.Abstract

Replace the agent-operated chain of Anchory batch files, source patching, LineRecord
reconciliation, and Chat.Index plans with one typed `Capture.Manifest` and one coordinator.
The manifest states the authored intent once; `tarav index capture preview --manifest ...`
validates and reports the complete plan without writing, while `land` revalidates, applies the
same plan, and audits every resulting surface.

This first iteration implements the default path required by current work: ground exact
existing Markdown or SKW-hosted Index lines. It does not introduce a configurable capture
graph or a second surface parser. A disposable Markdown `Capture.Test` block exercises the
real production path and is removed after the test.

Per the session overwrite, product grounding is deliberately deferred until execution is
otherwise complete. The final pass will use this new workflow to scan and ground this
Impl.Req and the edited code surfaces.

## Impl.Index

- [DC] one `Capture.Manifest` is the authored authority for support, gate evidence, target
  placement, and line wording; downstream Anchory, source, LineRecord, and Chat.Index effects
  are derived from it
- [CT] `preview` performs the whole preflight and writes nothing; `land` repeats that preflight,
  refuses every invalid batch before mutation, applies the complete pipeline, and audits the
  final state
- [CT] message references are structured objects containing session identity, message address,
  message-content hash, and optional human hints such as timestamp and `expect.contains_all`
- [DC] message side is not authored in the manifest; relationship position determines the
  allowed side and the workflow verifies it against the immutable Chat.Surface
- [CT] content expectations are conjunctive, normalized substring checks against the resolved
  message text and fail closed before any anchor is minted
- [CT] source edits address one project surface, one parser-backed block/annotation scope, and
  one exact ungrounded typed line; ordinary live Markdown uses an explicit heading locator while
  default Index and SKW surfaces retain structural discovery
- [CT] all renderings consume one `Index.Capture.Run` runtime model; default text is compact and
  structured JSON exposes the same plan and audit rather than a separate execution path
- [CT] capture is retry-safe: a repeated manifest reuses exact dossiers, recognizes already
  grounded source lines and records, and does not duplicate Chat.Index lines
- [TS] a disposable `Capture.Test` Markdown block is created in an isolated project, captured
  through the production coordinator, audited end to end, and then deleted with its test state
- [PR] Stable.Surface means maintained valuable content, not undeletable content; immutability is a separate contract held by Chat.Surface and must not be inferred from stability ^c20260821-45u
- [CT] maintained project guidance names the installed `tarav` CLI, not the retired `agentos` command ^c20260821-46u

## Execution.Plan

### Slice 1 — manifest and preflight

- Add strict dataclasses/parser for the manifest and structured message references.
- Resolve all referenced messages once, verify relationship side, hashes, order, tokens, and
  `expect.contains_all`, then derive the existing Anchory batch model.
- Resolve target lines through the shared native Markdown, Index, and Skillware surface parsers
  and stage exact source patches without writing.
- Return one compact `Index.Capture.Run` document for text and JSON.

### Slice 2 — coordinated landing

- Revalidate before writing, register the idempotent Anchory batch, patch exact source lines,
  create/reconcile LineRecords, and derive/apply Chat.Index capture plans from the same resolved
  objects.
- Audit source attachments, dossiers, records, and Chat.Index results; report precise phase and
  effects if a later durable write fails.

### Slice 3 — disposable production-path test

- Build an isolated discovered Markdown surface containing a `Capture.Test` block.
- Preview and land its manifest through the production coordinator, assert every durable effect,
  repeat for idempotency, then remove the block and isolated state.
- Keep this a real production-path probe, not a parallel fake implementation.

### Slice 4 — close and capture

- Correct maintained `AGENTS.md` CLI guidance from `agentos` to `tarav` where it describes this
  distribution's installed command.
- Run focused capture/CLI tests, broader Index tests, ruff, and the proportionate full suite.
- Scan this Impl.Req and edited code surfaces for durable decisions, author one manifest, preview
  it, land it, and verify its final line/record/Chat.Index audit.

## Impl.Log

- [TS] Execution is authorized by `$tarav-hugentics --impl --dev --AUTO`; the user explicitly deferred all grounding to the final scan so the new workflow can ground its own implementation.
- [OBS] The pre-edit checkpoint is clean except for a concurrent edit to
  `src/tarav/index/record/blessing.py`; capture work will preserve and avoid that file.
- [DC] Existing Anchory registration validates immutable message hashes, relationship sides, proposal/approval order, exact attachment triplets, and idempotent reuse; existing Chat.Index application validates dossier support and applies an idempotent audited surface update, so the missing unit was composition and one authored model. ^c20260821-47u
