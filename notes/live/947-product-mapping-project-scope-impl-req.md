# Project-configured Product Mapping scope

## Impl.Abstract

Knowledge.Surface: wiki. Status: executing. Correct the overbroad tarav-py run:
only committed .py files under src/ and tests/ belong in its active map. The
User explicitly puts this scope in Project configuration, not engine defaults.
Keep the generic workflow product-agnostic.

## Design and Impl.Req.Wiki

Add include/exclude globs to the existing product_mapping config section.
The Project Mapping manager supplies those controls to ProductMapper; the
historical driver reads the same Project config. Scope changes must not silently
reinterpret a confirmed map: retain each map's actual include/exclude selection
and audit against it. Standalone callers retain the existing explicit controls.
An outdated scope triggers an update even at the same commit.

Preserve the rejected broad run through its existing committed Registry data
and a superseded track. Rebuild the active history at the same ten-commit
checkpoints from the configured scope, then map completed HEAD. Keep the report
outside the selected product paths. Migrate existing records explicitly to name
their original scope; do not add read-time repairs or hardcode Python in core.

Wiki owner: tarav-md/notes/wiki; product-mapping.md and daily/2026-10-22.md.
This corrects request 946's operational scope, not the underlying general design.

## Execution.Plan

- [ ] Feature: Project config → manager/driver → generic mapper; snapshot scope
  preserves old audits. Verify nested .py inclusion and exclusion of .md, notes,
  retired code and similarly named directories; config changes update selection.
- [ ] Data: preserve old run, rebuild scoped history, independently audit each
  snapshot and compare inventory with committed src/tests Python files.
- [ ] Capture, checks and commits; final HEAD catch-up without changing scope.

## Impl.Log

- Worktrees initially clean. Product head 1f714d75, original run 128 maps.
- Todo list above. Product Mapping's existing include/exclude mechanics are
  reused. No new file classification, parser or workflow type is needed.
