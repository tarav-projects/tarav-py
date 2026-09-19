# SKW typed depot implementation

The user approved unifying SKW objects with ordinary registered Tarav directory
records. `.skw/main.json` selects a class; `SkwSkill` specializes `SkwDepot`.
Classes own interpretation and due diligence. There is no legacy manifest
fallback and no new universal schema gate.

Plan:
- Replace passive skill record and separate operational wrapper with SkwSkill.
- Reuse directory discovery and the type registry for library and CLI loading.
- Migrate the maintained manifest and examples to main.json.
- Verify an alternate depot subtype, current skill operations and error paths.

Design grounding is captured in the Project.Wiki commit c4907f3. This note is
implementation coordination, not a new Diagram capture.

Implemented: SkwDepot and SkwSkill use the existing directory-record loader.
Runtime injects its registry into CLI consumers. Skill operations perform
class-owned validation without a second type-label gate or cached validity.
Document dispatch honors entry-file priority and accepts non-skill depots.
The Hugentics manifest moved to main.json; no legacy loader is retained.

Verification: 58 focused tests passed before additional regression coverage.
The full run passed 1,139 tests and exposed one incorrect new test expectation
(check reports a finding rather than raising). The corrected 12-test skill
suite passed; scoped Ruff and diff checks passed. Real Hugentics loading and
CLI checking retain the three pre-existing link POIs. CLI reinstalled.
Product changes remain uncommitted.
