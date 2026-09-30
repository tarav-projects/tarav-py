# Reading containment and first-order link availability

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki.
Phase: Develop. Alignment.Mode: Interactive.
Status: implemented and focused-test verified; evidence recovered for closure.

Unify reading content claims around containment. Loading a block loads the
content of its contained SKW blocks recursively, including their annotations.
Links expose references, not the content or annotations of their targets.
Do not change the shared Check/CheckResult/POI infrastructure or infer claims
from prose. Rendering and explicit reading routes remain separate concerns.

## Design narrative

The user established these examples:

```text
A contains B contains C -> A supplies B and C.
A contains B links C    -> A supplies B and a reference to C.
A links B contains C   -> A supplies only a reference to B.
```

Containment claims equivalence to loading the contained block itself. A
separate inline declaration is unnecessary for this semantic relationship.
Targets may be TaravEntities from other workflows; recursive annotation
expansion initially applies to SKW blocks. The mechanics trust declarations;
checking that prose substantiates them is a separate responsibility.
<!-- tarav.breadcrumb 17bb4674fb1b45214a25be3538ba4523422d7b04cca6b5522c4a321bf314a530 -->
<!-- tarav.breadcrumb 778ae63ee3e6220f95e1eb849e443f350d6c0521d7e59dc3342d1e1c651ad35f -->

The link stopping rule belongs to reading-path availability analysis, not
to all graph traversal. Agents may choose to follow links, and other analyses
may explore linked targets. A link exposed through containment must not be
lost, but neither should its target automatically enter the loaded context.

Current reading.py defines ProvidesEntity, InlinesEntity and IncludesBlock.
IncludesBlock inherits ReadingLink and also drives rendering slots. loading.py
recursively supplies included blocks and their links, but adds ExpectedLink
destinations to automatic traversal. ProvidesEntity/InlinesEntity only add
target identities, without recursively expanding block targets. Base
ReadingLink is accepted by the registry but ignored by the analyzer.

Required changes: provide one containment declaration; recursively expand
block targets; treat all links as references for availability; retain
composition separately; migrate affected declarations explicitly; preserve
complete containment paths in dependency diagnostics. Existing Check and POI
integration remains the reporting surface.

The user clarified requirement timing: if A contains C and A precedes B on
the reading path, B's requirement for C is satisfied. A does not need to
contain B. Containment expands supplied context; the reading path accumulates
that context before checking later blocks. Preserve that distinction and do
not introduce a new sibling-order contract. Requirements remain checks on
incoming path context, not on a block's own newly supplied content.
<!-- tarav.breadcrumb 71b057d08790a528640bc4f92535b38f5112a384e776830c9fbed40966e6a55b -->

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki.
Context: reader-context-path.md, section “Containment supplies content; links
supply references — 2026-09-30”; daily/2026-09-30.md.

Supporting conversation: codex session
01a0d86c-9538-7be1-af96-014cd4203d61, from “maybe we do not need inlines”
through the confirmation that other analyses can follow links further, and
the subsequent Develop invocation. Chatlas refresh failed with PermissionError
writing its derivation cache under /Users/pereiro/Documents/tarav/chatlas.
Exact Turn Breadcrumb attachments remain pending; none are fabricated.

## Execution.Plan

- [x] Inspect current declarations, recursive supply, rendering and tests.
- [x] Establish scoped start checkpoint before product edits.
- [x] Resolve requirement timing, then cold-read this request.
- [x] Implement containment and reference-only availability, separately from rendering.
- [x] Inspect maintained records for required migration; none use removed declarations.
- [x] Test the three examples, nested containment, cycles, external targets,
  base links, dependency timing and containment-path diagnostics.
- [x] Run focused Checks/POI/SKW tests and relevant lint checks.
- [ ] Capture product evidence, update Wiki and close scoped commits.

## Impl.Log

Design inspection found no edits to the target reading.py/loading.py/tests
from other work. Existing uncommitted Lines/Context/Models work is out of
scope and must be preserved. The implementation requires neither a new
runner nor a new finding type.

The scoped start checkpoint was attempted using an empty-file manifest.
Tarav rejected the message: “Commit message requires an evidence group”.
No checkpoint was created and no product code was edited. The known-session
User evidence remains unresolved; unknown-session is not an appropriate
replacement. The Develop procedure requires stopping before product edits
when the checkpoint cannot be established. Resolve evidence/permissions and
the requirement-timing choice before execution resumes.

### Execution after clarification

The user clarified that A need not contain B: A contains C and precedes B on
the reading path; B requires C. This is the regression contract. Context is
accumulated before checking later blocks; no new sibling-order policy was
introduced.

The earlier checkpoint failure was corrected with an honest agent-initiated
evidence group describing only the empty operational checkpoint, not claiming
user support for product changes. Start commit:
`d1985641fccbd159518c19323ce0641a16d00eac`. No unrelated files were included.

Implementation:

- reading.py adds Contains and removes ProvidesEntity/InlinesEntity. Contains
  resolves a target identity and recursively expands bound SKW blocks only.
- IncludesBlock remains a composition specialization of Contains, no longer a
  ReadingLink. It preserves its identity and rendering fields; its entry must
  resolve to its claimed contained block. Plain Contains does not render.
- loading.py recognizes base ReadingLink and subtypes uniformly as references.
  ExpectedLink no longer adds automatic reading edges. Explicit parents and
  default within-document predecessors still determine reading routes.
- Requirements retain incoming-context semantics and occurrence diagnostics now
  include the full containment path. Shared Checks/POI mechanics are unchanged.
- Existing `inlined` analysis keys and InlineDependency remain the content
  vocabulary for consumers; their documentation now clarifies containment is
  not a rendering instruction. No unnecessary output-schema rename was made.

Record inspection searched maintained tarav-md/tarav-py JSON (including hidden
SKW sources) for both removed names and their TypeShips: no matches. Thus no
retained record rewrite was needed. Existing IncludesBlock records remain
valid composition claims; ExpectedLink declarations remain link expectations,
not automatic proof of loading. External depots were not mutated or migrated.

Verification: 62 tests passed across test_skw_loading, test_skw_skills,
test_skw_poi, test_checks_workflow, test_poi_primitives, test_poi_workflow and
kernel/test_object_record_contract. Ruff on both changed modules and the test
file passed; git diff --check passed. uv could not access its cache in the
sandbox, so these checks used the existing .venv executables.

Maintained-package read-only analysis: tarav-hugentics visits all 101 bound
blocks, reports complete=True, and retains three unannotated-output-link
diagnostics. tarav-pkg has no declared loading model; attempting loading()
reports that explicit boundary, so no path analysis was claimed for it.

Product evidence scope: reading.py, loading.py, test_skw_loading.py and this
request. Exact-session Chatlas ledger access failed on its Normal Model lock
with PermissionError. Breadcrumb insertion/submission/audit could not proceed
without exact Turn references; no fabricated markers were inserted. Wiki
capture is saved locally with the same gap. Completion commits remain pending
rather than mislabeling user-directed implementation as agent-initiated.

### Evidence recovery

Permissions were restored. Exact-session refresh and Turn ledger resolution
succeeded; the 62-test verification was rerun successfully. Earlier permission
gaps above describe historical attempts. Evidence submission and closure resumed.

Breadcrumb submission succeeded for all three changed Python surfaces, this
request, reader-context-path.md and the daily note. The post-submission
reading-path suite passed (24 tests), Ruff passed and diff whitespace checks
passed. Other uncommitted Lines/Context/Models work remains outside this closure.
