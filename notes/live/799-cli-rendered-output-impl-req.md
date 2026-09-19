# 799 — CLI rendered output — implementation request

<!-- tarav.sessions
5626cd5f = codex:01a0af61-72e2-7bd2-94a3-26529d6914ec @5626cd5f7db74c4f2e3838250516b5e300cc9387ac254eb65a0816a5f30555a1
-->

## Impl.Abstract

Make rendered views the default CLI output. Offer explicit `--rendered` and
`--json` modes. The underlying operation and structured result remain the
same; mode selection changes presentation at the final printing boundary.
<!-- tarav.context 5626cd5f:e14da29c0a482853 -->

## Requirements

- Omitting a presentation flag selects the rendered view.
- `--rendered` explicitly selects that same view.
- `--json` prints the structured result as JSON.
- Rendering does not change the operation, its data, or its semantics; the
  presentation choice is applied when printing.
<!-- tarav.context 5626cd5f:e14da29c0a482853 -->

## Execution.Plan

Proposed implementation steps, not additional User requirements:

1. Inspect existing CLI printing and renderer conventions, starting with the
   SKW navigation commands that prompted this discussion.
2. Keep structured results in the library; select rendered or JSON output in
   the CLI presentation layer. Use mutually exclusive mode flags.
3. Add concise renderers appropriate to each selected command. Preserve
   existing bounded navigation and explicit expansion behavior.
4. Verify that default output matches `--rendered`, that `--json` preserves
   the structured result, and that output mode does not change execution.
5. Update CLI help and examples. Record which command surfaces are migrated;
   do not claim CLI-wide coverage from a SKW-only implementation.

## Impl.Log

Status: all maintained `tarav skw` commands implemented.

Migrated command surfaces:

- `tarav skw document context`
- `tarav skw skills ls`
- `tarav skw skills read`
- `tarav skw skills context`
- `tarav skw document lint`
- `tarav skw document compile`
- `tarav skw document prepare`
- `tarav skw document record`
- `tarav skw document observe-context`
- `tarav skw skills check`
- `tarav skw skills build`
- `tarav skw skills deploy`
- `tarav skw skills poi`
- `tarav skw skills bless`
- `tarav skw skills assess-blessing`

These commands default to concise rendered output, accept explicit `--rendered`,
and retain their complete structured results under `--json`. Presentation is
selected only after the existing library operation returns.

Grounding uses inline wiki-style references only, as requested. No Diagram
Collection, Draft, or other Diagram record is created for this request.
<!-- tarav.context 5626cd5f:e14da29c0a482853 -->
