# Context package organization

## Scope and checklist

- [x] Move Context primitives from Kernel to `tarav.context`.
- [x] Split ContextWorkflow into `context.workflow` and Archive-backed services
  and Records into `context.storage`.
- [x] Remove Kernel re-exports and the conflicting callable library-root name.
- [x] Keep `context(subject)` runtime-aware; expose contributor-based `explore()`.
- [x] Move class-bases presentation to Context; Kernel hooks remain extensible.
- [x] Update maintained callers, architecture tests, and guidance.
- [x] Complete regression validation: 196 focused tests, fresh-process import
  order checks, and all 1,297 full-suite tests passed. Ruff and diff whitespace
  checks pass; no old Context import paths remain in maintained Python callers.

The user explicitly approved the public import change. External callers must
update imports; no compatibility aliases or stored-data rewrites are added.
Type/Workflow Ships and Record schemas remain unchanged. Storage is a higher
composition layer than Context primitives; dependency checks distinguish these
layers and omit annotation-only TYPE_CHECKING imports.

## Capture status

Coordination only. Diagram capture remains unreconciled; no Collection, Draft,
or Capture Receipt is claimed. Earlier worktree changes remain preserved.
