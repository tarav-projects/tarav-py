# Workflow singleton identities

## Impl.Abstract

Implement the revised class/object distinction: `entity(WorkflowClass)` represents
only the Python class; `WorkflowClass()` represents the workflow, with a separate
fixed identity and one instance per concrete class in the process.

## Execution.Plan

- [x] Restore TaravWorkflow as a TaravEntity with singleton construction.
- [x] Declare fixed workflow IDs independently from class ownership.
- [x] Update registry and Archive identity consumers; remove ContextService.id.
- [x] Test separate identities, ownership independence, repeated and concurrent
  construction, and record identity rejection.
- [x] Complete full-suite validation: 1,293 passed. An additional identity-
  declaration test added during that run also passed in the focused suite
  (4 tests). Ruff and diff whitespace checks pass.

## Scope

Both existing UUIDs survive unchanged. No retained data is moved or rewritten.
Registry APIs continue registering and returning implementation classes.
Workflow objects support direct Record round trips; automatic dynamic Record
registration is not added. Runtime-specific services remain separate from the
process-wide singleton. Follow-up establishes the umbrella root and explicit
parent links; package moves and DiagramView type discriminators remain outside
this change.

## Impl.Req.Diagram

Incomplete: this implementation has no reconciled Collection, Draft, or Capture
Receipt. This note is coordination only, not captured design authority. The
in-chat decision is implemented directly; Diagram and Product Breadcrumb capture
remain outstanding and must not be reported as completed.

## Impl.Log

- Follow-up: instantiate TaravWorkflow as umbrella root; `.workflow` returns
  the containing workflow object (None only at the root). Record Archive's
  parent is Archive. Class and partition Records retain Ship strings; their
  Python `workflow_ship` surfaces support storage and lookup consumers.
- Library composition injects lazy workflow resolution into Kernel. Ownership
  inheritance uses Ships without attempting runtime bootstrap.
- Follow-up validation: full suite 1,295 passed; 27 focused ownership and
  architecture tests passed; Ruff and diff whitespace checks passed.

- Existing tests exposed class-level identity uses in the test-workflow fixture
  and architecture assertions; changed them to use workflow instances.
- Existing Archive partition addresses and class Context addresses are preserved.
- No retained-data migration or Git commit performed.
