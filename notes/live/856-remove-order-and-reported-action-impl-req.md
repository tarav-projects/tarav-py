# 856 — Remove Order and ReportedAction from the Decisions workflow

<!-- tarav.sessions
5a029cbf = claude-code:8c55cc60-f28a-439f-a6a0-0521567e600e @5a029cbf49a299c9709013b8ccb3fc517b2fb56fed373d3da819b6ea842afa2f
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: ready.

Delete the `Order` and `ReportedAction` Decision subtypes added by request 854.
`Decision` stays as the root type and `BlessingRecord` keeps subtyping it.

Non-goals: no change to `Decision`, `BlessingRecord`, `BlessingStore`, tracked
POIs or the board's behaviour; no decision about where Decisions are stored;
no replacement subtypes.

## Design narrative

### User direction

`Order` and `ReportedAction` were discussed as hypothetical kinds of decision
and were never explicitly designed. They do not belong yet in a workflow as
core as Decisions.
<!-- tarav.breadcrumb 2ca425b8e7646851ebc6c26f64011d90cdf0308a50db685c1c860dd018440302 -->

They are deleted. Nothing is over-implemented without a clear need or a clear
design; other Decision types can be defined later, and the system is not
biased now.
<!-- tarav.breadcrumb 82badfb9185421154ec1783fba03de18a23f6c9da6952009093f398f56879ca6 -->

A Decision is a point in the ontology that says the object exists; it is not
forced to have storage. Storage is still to be designed. It may depend on the
workflow or on the project. A single store for all the Decisions of one
project, linked to the Project workflow, is the arrangement that makes most
sense to establish first; other stores can come later.
<!-- tarav.breadcrumb 11337b483106eca7d7c11b2757d71d882814db7e395064038c4c874467cff4f4 -->
<!-- tarav.breadcrumb edfe792727643e1e68b099b10a419902b0359f23d3d6c2b15a90fe433eab0c44 -->

### Current behaviour (inspected)

`src/tarav/l1/decisions/records.py` defines `Order` and `ReportedAction` with
identical bodies (`subjects`, `poi_ids`). Their only references are the
package exports, `DECISION_RECORD_TYPES` (registered in `l3/runtime.py`),
`DecisionStore.__init__`, which registers both by default, and one test. No
workflow, and neither g70203 nor md-library, creates or reads them. Request 854
listed their record shape under "Agent proposals (not User-approved)".

### Decisions (agent proposals)

- `DecisionStore` stays in place but registers only the types its caller
  supplies. Whether it remains in the Decisions workflow or becomes the
  Project workflow's store is the open storage design above and is not settled
  here.
- No retained data is migrated: no Order or ReportedAction record is known to
  exist outside test temporaries.

## Impl.Req.Wiki

Product owner: `tarav-py`.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: `tarav-md/notes/wiki/decisions.md`; request 854.
Supporting chat: claude-code session `8c55cc60-f28a-439f-a6a0-0521567e600e`.
Capture status: pending.

## Execution.Plan

1. Remove both classes, their exports and their default registration.
   Check: no reference to either name remains in `src`.
2. Rework the test to exercise `Decision` through a test-local subtype.
   Check: `tests/decisions` and the architecture tests pass; ruff clean.
3. Update the `decisions` row and paragraph in `ARCHITECTURE.md`.

## Impl.Log

