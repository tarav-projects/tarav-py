# Diagram Object Query

## Impl.Abstract

- **Status:** Implemented
- **Source session:** `01a05752-fa8d-7c62-abb2-5ff20c8260da`
- **Objective:** Add a general filtered Diagram object-list query so Agents can
  retrieve narrow Model surfaces without rendering and post-processing the
  whole Model.
- **Boundary:** Query by Model or Project, object kind, `Object.Type`, and
  label; return compact standing scoped to the matched objects.
- **Out of scope:** A special Impl.Req registry or command, and invention of a
  cross-surface identity between Diagram Blocks and live notes.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` /
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Model:** `Tarav` / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Impl.Req.Block:** `770.Impl.Req` /
  `215c9f66-edd5-4153-bf0a-4d8b36bdc98d`
- **Block edition:** `6e7b7c92-45d4-49ce-aa87-edcc32851f11`
- **Capture commit:** `5f95671b21cc400e492c0022c960f09152d74a08`
- **Capture standing:** one automatic Decision Line landed; expected
  unasserted and Archive-grounding POIs remain nonblocking.

## Execution.Plan

1. **Query contract** — add failing domain and CLI tests for narrow,
   composable object filtering. **Complete.**
2. **Implementation** — add the generic query and compact scoped output.
   **Complete.**
3. **Acceptance** — query the live Tarav Model for `Impl.Req.Block`, then run
   focused and maintained checks. **Complete.**

## Impl.Log

- The supported bootstrap Capture records the requirement before product
  mutation.
- The current workaround requires whole-Model JSON rendering plus `jq`, and
  returns unrelated whole-Model POIs.
- The live-note relationship remains a separate Product.Surface identity gap;
  this slice does not conceal it behind an Impl-specific lookup table.
- Required execution checkpoint: `tarav-py@3a5ef0d`.
- `tarav diagram object list` now selects a Model directly or through its
  Project and composes exact `--kind`, `--object-type`, and `--label` filters.
  Block labels are matched across retained editions, while results identify
  the current edition and current label.
- The compact result includes assertion counts, reviewed/unreviewed Line
  counts, and only POIs belonging to matched objects. Relational Annotations
  retain their separate `diagram annotation list` query surface.
- Testing exposed and repaired a projection defect: Ship editions without
  timestamps could be ordered by random UUID. The projector now honors the
  authoritative edition order stored by each Ship.
- Live acceptance returned the four current Tarav `Impl.Req.Block` objects;
  filtering by `770.Impl.Req` returned only this Block and its four scoped
  POIs.
- Focused and complete Diagram checks pass; Ruff passes and the full maintained
  suite passes (`1509 passed`). Slice-close review found no additional
  User-Touched requirement beyond the bootstrap Decision Line.
