# 834 — Situation-based POI identity and LiteRecord

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Impl.Abstract

Knowledge.Surface: wiki

Status: implemented and verified.
Alignment.Mode: Interactive.

Replace the identified POI's separate occurrence/state fingerprints with one
identity derived from its concrete Type Ship and explicit caller-supplied
`situation`. Introduce a reusable LiteRecord supporting controlled serialization
of accepted native values. Update Checks, Blessings, collectors, and active
producers together. Preserve neutral POIs and optional blessing capabilities.
<!-- tarav.breadcrumb 622bc08f3ef71f3f8ba5348456d915149f5542df6b24ab8045ca96adf78f5342 -->

Non-goals: legacy blessing-data migration or compatibility readers; changing
Archive placement; a general object persistence engine; automatic inference of
equivalent situations; making every notification blessable or identified.

## Design narrative

### Identity describes the situation, not an execution counter

A POI Type already has its class Ship. A detection instance may intentionally
identify the same situation across runs, or represent a fresh occurrence.
The producer decides what equivalence means. Discovery does not itself imply
random identity. An occurrence-specific token can distinguish intentionally
fresh situations without a separate identity policy engine.
<!-- tarav.breadcrumb 4afe64ff98376eb982f502913e864de5a0332c4123f8dd62c52d18287a034efe -->

The selected model is conceptually:

```python
situation = LiteRecord({"block": block_id, "input_revision": revision})
identity = hash_of(concrete_class_ship, situation)
```

The caller supplies the situation. Blessings are one consumer of identity, not
its definition. There is no second POI `state` used to distinguish situations
under the same identity. If a changed input should require another blessing,
the producer must include that distinguishing input in its situation. Prefer
resurfacing and reblessing to accidentally grouping a new concern with an old
blessed situation. Do not silently include evidence or message text in identity.
<!-- tarav.breadcrumb dd5b2bbea5e857be4fd2d58bd63f41a9131de99d2693188e6bf2352813a8e928 -->
<!-- tarav.breadcrumb 9f0c9403496aee195ae091ca789090f4643af5f063b5776c34cd4b2169af4688 -->
<!-- tarav.breadcrumb f2c6a130dfbc85474b1b65823bd8f2641daeaabe1a51ea4102c06452132a155a -->

### LiteRecord is controlled serializability, not primitives-only input

LiteRecord is a dictionary-shaped value with string keys and recursively
supported values. Its serialized representation is JSON-compatible, but callers
may pass supported native values directly, including dates and Tarav Types.
Established serializers define the accepted nonprimitive types. Unsupported
objects must fail explicitly, rather than falling back to `str()` or arbitrary
object introspection. This is a general foundation, not a POI-specific payload.
<!-- tarav.breadcrumb 73435f0849aee190784624c597929303af2613f9017e5dbe9980f337e495ee30 -->

Agent implementation proposal: put the foundational value/codec mechanics at
`tarav.l0.kernel.lite_records`, exported from the Kernel as appropriate. Keep
domain serializers outside that foundation when imports require it. Start with
JSON primitives/containers, dates, Ships, and declared Tarav Types; use trusted
code to extend accepted values. Do not introduce data-directed imports.
Do not change existing Record loading semantics as a side effect.

Canonical encoding must be deterministic: dictionary insertion order must not
alter identity; list order must remain significant. Type references use stable
class Ships, not Python names or repr. Preserve distinctions between a native
typed value and a lookalike string/dictionary through an unambiguous encoding.
Reject cycles and nonfinite numbers. Specify and test the exact encoding in
code; do not introduce timezone or other semantic equivalences implicitly.
Round-trip reconstruction of every native object is not a prerequisite.

Snapshot the canonical situation at POI construction (agent proposal). Later
mutation of caller-owned dictionaries must not change an existing identity.
Retain an inspectable situation representation; hashing must not hide what the
caller declared. No separate mutable-state fingerprint is introduced.

Collector addressing has two levels. The stable POI identity selects a
situation; a zero-based emission index selects one observation of that situation
inside the current collector evaluation. The index is assigned in emission
order, is not part of POI identity or blessing matching, and is exposed when
several observations share an identity. Identity-prefix resolution happens
before index selection. A lookup without an index succeeds only for one
observation and otherwise requires the caller to select the index explicitly.
<!-- tarav.breadcrumb f15d65be0d76e00ce37feef816d9f13e5b3f44059b725f8fbca5a2497dd79d8a -->

### Minimal integration, not another identity framework

Agent proposal: retain the existing `IdentifiedPOI` capability boundary and
change its constructor to require an explicit keyword `situation`. Keep the
almost-empty POI base and simple NotificationPOIs unchanged. Existing subject,
coordinate, evidence, details, and Check context may remain descriptive data;
none is an implicit second matching axis. Keep `identity` as the existing
public spelling; no extra `hash`/`id` aliases are needed for this slice.

BlessablePOI continues to compose with CheckPOI. Its snapshot carries concrete
class identity, situation, computed identity, and useful explanatory data.
BlessingStore validates the identity against the canonical situation and matches
only that identity. Remove stale-state comparison and corresponding status/filter
branches. Preserve attributed assessments and blessing history, not a second
POI identity dimension. A changed situation is a different, initially unblessed
POI. Blessing remains optional and does not suppress notification delivery.

### Current implementation and affected surfaces

Inspected implementation observations, not claims from the User:

- `src/tarav/l1/poi/primitives.py`: IdentifiedPOI currently computes identity
  from class_id/subject and state from identity/evidence. Collector lookup can
  reject a repeated identity when states differ; reports serialize state.
- `src/tarav/l1/checks/`: CheckPOI supplies subject/evidence defaults. Producers
  must now explicitly supply situation rather than inherit those defaults.
- `src/tarav/l1/blessings/capability.py` and `store.py`: blessing snapshots and
  schema-2 validation require state; standing distinguishes blessed/stale.
- `src/tarav/l1/skw/generation.py`: GenerationPOI currently identifies by
  invocation while kind/detail can differ. The producer must explicitly decide
  how kind and relevant inputs distinguish situations, avoiding conflation.
- SKW reading/generation checks, Breadcrumb audits, and other IdentifiedPOI
  constructors and CLI renderers must be inventoried before edits. Do not change
  unrelated neutral POIs just to make them identified.
- `src/tarav/l0/kernel/records.py` already owns Record JSON boundaries; LiteRecord
  must remain distinct from a typed object's full RecordInterface.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md`.
Wiki root: `../tarav-md/notes/wiki`.
Topical context: `poi-system.md`; daily: `daily/2026-10-01.md`.
This request supersedes the identity/state portion of 833, not its workflow
ownership, optional capability, or neutral notification decisions.
Original supporting User Turns are embedded beside the design above; another
session must preserve them rather than replace them with its execution trigger.

## Execution.Plan

Agent plan implementing the requested design:

1. Inventory all identity/state constructors, snapshot consumers, status filters,
   tests, and serializers. Respect concurrent changes. Confirm dependency placement
   and keep imported foundations independent from workflow/runtime composition.
2. Implement LiteRecord validation and canonical encoding with a small explicit
   serializer extension interface. Document supported native types and failure
   paths. Reuse existing Ship/Type identity semantics.
3. Change IdentifiedPOI and CheckPOI to explicit situation identity. Snapshot
   input; preserve inspectable context. Remove state from lookup and reports.
4. Update every active identified producer with a deliberate situation. Record
   those choices near code, including kind/location/revision when relevant;
   do not mechanically rename subject or evidence and assume equivalence.
5. Update BlessablePOI snapshots, BlessingStore validation/matching, CLI output
   and filters coherently. Version the new retained schema explicitly; no legacy
   reader or data rewrite. Keep physical storage placement unchanged.
6. Update relevant docs and inherited/runtime contracts. Capture product
   Breadcrumbs, test bounded slices, update this log, and close scoped commits.

### Verification

- LiteRecord: nested JSON input; dates, Ships and Tarav Types accepted without
  caller conversion; unsupported values/cycles/nonfinite numbers rejected;
  equivalent dict orders hash equally; list reorder and type distinctions differ.
- Identity: same concrete class/situation reproduces identity across processes;
  different class or situation differs; explicit occurrence token distinguishes
  runs; input mutation cannot change an already constructed POI.
- Descriptive evidence/message changes alone do not affect identity; producer
  tests show identity-relevant revisions are explicitly included in situation.
- Blessings: same identity matches; changed situation does not; no state field,
  stale-state resolution, or accidental subject-only fallback survives.
- Collector: repeated equivalent POIs remain inspectable without state conflicts;
  genuine identity-prefix ambiguity remains explicit.
- SKW: different generation concerns from one invocation are distinguishable;
  CheckPOI/BlessablePOI composition and notification delivery remain intact.
- Run focused POI/Checks/Blessings/SKW/Breadcrumb/CLI tests, architecture tests,
  lint and broader suite when feasible. Separate unrelated failures in the log.

## Impl.Log

2026-10-01 — Design inspected the current POI and blessing identity mechanics.
No product code or retained blessing data changed. Foundational encoding and
capability placement above are bounded agent proposals, not additional User
decisions. Start checkpoints: Python `c8d1acd`, Wiki `9c4c497`.
Capture completion is recorded by the submitted Breadcrumbs and closing commits.

Capture verification: 16 new Breadcrumbs submitted across this request and the
two Wiki surfaces. All three surface audits returned `status: ok` and no POIs
(6, 29, and 8 total existing/new Breadcrumbs respectively). Scoped whitespace
checks passed. No product tests were run because this pass changes design
documentation only. Unrelated worktree changes remain outside this request.

2026-10-01 — Execute added the approved two-level collector address: stable
situation identity plus a zero-based, evaluation-local emission index. Product
execution was explicitly requested after the design inspection.
<!-- tarav.breadcrumb b20357468251338bd191f5344c21a12cbd573578742fc3340acc7fdb6b73e9fc -->

Implemented `LiteRecord` in Kernel with deterministic JSON-compatible encoding,
native dates, Ships and Tarav Type references, reserved-tag escaping, cycle and
nonfinite-number rejection, detached snapshots, retained-value validation, and
trusted exact-type serializer extensions. This remains a value contract rather
than a TaravObject persistence system.

`IdentifiedPOI` now requires an explicit situation and hashes only its concrete
Type Ship plus that situation. The state fingerprint was removed. Collectors
retain every emission, require an index for repeated identities, and expose
those indexes in reports. Checks and all active producers now declare their
situations, including concern kind for generation and source revisions for SKW.

Blessing schema 3 retains and validates situations. Blessings match POI identity
directly; stale standing and filters were removed. The SKW CLI accepts only
`unblessed` and `blessed`, supports `--index` for repeated POIs, and keeps
non-blessable POIs inspectable without invoking Blessings.

Focused integration validation passed 162 tests. The complete suite passed
1,342 tests; its 88 failures stop at the concurrently disconnected Models
surface and do not reach 834 behavior. Ruff, `git diff --check`, CLI help, and
Product.Surface Breadcrumb audits passed. Start checkpoint:
`b9b61be0c559170e2814c6a796a528e866166176`.

Product completion commit:
`f93e785bc92f687d9876446c36d960dd033dae67`; its five commit-evidence
Breadcrumbs resolved with no POIs. Wiki implementation capture landed in
`tarav-md` as `bd5cc7af428e929682549e7b0d98b490555d7fca`; both Wiki surfaces and
all three commit-evidence Breadcrumbs resolved with no POIs. Unrelated dirty
work in both repositories remained outside the scoped commits.
<!-- tarav.breadcrumb eb9e8eb9360e2151b525b00449a147addc580e3d7b37b1d843b2687c86c2a795 -->
