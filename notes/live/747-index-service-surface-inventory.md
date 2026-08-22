# 747 — Index service-surface inventory

## Note.Abstract

- **Purpose:** enumerate every capability the current Index system provides to its consumers, so the
  IndexLab recording kernel (`745`, `746`) can be measured against a real requirement list rather
  than a remembered one.
- **Scope:** `tarav-py` and the `tarav-md` skills. Chatlas and Anchory appear only where the Index
  depends on them.
- **Method:** read from the live CLI surface, the `src/tarav/index/` package, and every
  `tarav-hugentics` / `tarav-skillware` module. Not from recollection.
- **Status:** inventory only. No judgment here about which capabilities the new model should keep,
  drop, or reshape — several are artifacts of the superseded multi-surface model and are marked as
  such where the design session already says so.

## How To Read This

Each capability below is stated as *what a consumer can currently do*. The **Consumers** line names
the surfaces that would break without it. The **New-model note** line flags where `642`'s recording
kernel already has a position — including "explicitly dropped".

---

## 1. Record Lifecycle

### 1.1 Write a line record

- `tarav index write --scope --body [--type] [--anchor] [--session] [--support ...] [--trace-id]`
- creates a `LineRecord` for a line authored on a surface: identity, scope, typed body, label,
  support refs, optional trace membership.
- **Consumers:** `hugentics/capture.md` (landing step 8), `hugentics/edit.md`, `hugentics/link.md`.
- **New-model note:** becomes `line.capture`. Note the current call takes `--scope` (a *surface*
  coordinate) where the new model takes `block_id` (a semantic coordinate).

### 1.2 Revise a line into a new edition

- `tarav index revise --record-id --body [--type] [--kind rename|rephrase]`
- writes a new version and links it to its predecessor through `Equivalence`.
- **Consumers:** `hugentics/edit.md`, `hugentics/capture.md`.
- **New-model note:** `Equivalence`/predecessor chaining is replaced by `Isoline` membership. The
  `rename` vs `rephrase` distinction has no direct successor verb.

### 1.3 Remove a record

- `tarav index remove --record-id`
- **Consumers:** `hugentics/edit.md`, curation passes.
- **New-model note:** `purge`, bounded by `Index.Record.Mutation.Boundary`.

### 1.4 Inspect records

- `tarav index record [--record-id] [--side agent|user]`
- **Consumers:** every diagnostic path; `hugentics/search.md`.

### 1.5 Trace membership

- `tarav index trace --trace-id` — show one trace and its members.
- **Consumers:** `hugentics/edit.md`, `hugentics/decision-cycle.md`.
- **New-model note:** superseded by `Isoline`; `isoline.group` covers the grouping act but there is
  no read-side equivalent of `trace` yet.

### 1.6 Storage

- one Bloberia depot, shards, keyed by `id`, Git-backed (`record/store.py:75`).
- **New-model note:** IndexLab already matches this shape, but per-workspace rather than
  per-project-geography.

---

## 2. Identity, Addressing, Citation

### 2.1 Resolve a public label

- `tarav index resolve --label <^label>` → entry plus derived standing.
- labels are mutable selectors, never storage identity (`record/store.py:15`).
- **Consumers:** every citation in every index surface; `hugentics/search.md`, `link.md`,
  `anchory-pkg`.
- **New-model note:** IndexLab has `line_by_label` in the projection but no CLI and no standing.

### 2.2 Line identity triplet

- `Line.Type + body + Anchor.Id`, trailing anchors excluded from the body
  (`index/model/identity.py`).
- backs `anchor-collision`: one anchor may repeat only on an identical triplet.
- **New-model note:** IndexLab uses `Line.Id` for exact wording and `label` for citation. The
  triplet has no successor — worth deciding whether it needs one.

### 2.3 Anchory registration

- trailing `^anchor` tokens resolving through the Anchory depot registry to Chatlas dossiers.
- **Consumers:** every grounded line on every surface; `tarav-anchory-pkg` in full.
- **New-model note:** `642` keeps addressed support but drops the surface-side anchor token; the
  Anchory subsystem's role in the new model is unsettled.

---

## 3. Support And Grounding

### 3.1 Attach support to a line

- `--support ...` on `write`; the Chatlas dossier's `relationships.support` namespace.
- exact `{session, message_address, message_hash}` per reference.
- **Consumers:** `hugentics/link.md` (the whole grounding pipeline), `capture.md`, `agendix.md`.
- **New-model note:** `Support.Set` of `Evidence.Neighborhood`s. The new model adds the
  grounding/context split (user turns vs the agent turns needed to read them) that the flat
  current tuple does not carry.

### 3.2 Grow support without a new edition

- currently done by rewriting the record's support tuple.
- **New-model note:** `support.add` targeting an exact `Line.Id`. This is a genuine improvement,
  already implemented.

### 3.3 Derive line standing

- `Live` / `Grounded` / `Ungrounded` / `Demoted`; `Touched.Authority` vs `Index.Presumption`.
- **Consumers:** `hugentics/touched-data.md`, `search.md`, `decision-cycle.md`,
  `index-context-assembly.md`. This is the single most widely depended-on Index concept.
- **New-model note:** **no successor in IndexLab.** The kernel stores support but computes no
  standing. Every hugentics reasoning module depends on this classification.

### 3.4 Message touch standing

- `tarav index messages --session [--touched] [--contains] [--limit]`
- which messages in a session already carry touch into the index.
- **Consumers:** `hugentics/capture.md` (Map step), `chat-status.md`.
- **New-model note:** no successor. This is the *reverse* index — from chat message back to
  records — and IndexLab has no query in that direction.

### 3.5 Session summary

- `tarav index session --session <id|uri|hash>`
- **Consumers:** `hugentics/chat-status.md`, `capture.md`.

---

## 4. Surfaces And Discovery

### 4.1 Depot geography

- `tarav index config` / `tarav index init [--depot]`
- `000-INDEX.md` router, `<chapter>/NNN-<chapter>.md`, `appendix/`, `agendix/`, `issues/`.
- **Consumers:** `hugentics/edit.md`, `search.md`, `agendix.md`, `issues.md`; the `--depot` and
  `--chapter` skill args on the whole Hugentics router.
- **New-model note:** `642` rejects a required Markdown surface entirely
  (`Index.Primary.Surface` is the record depot). Chapters/appendix/agendix become *consumers*, and
  depot/chapter scoping has no kernel-level successor.

### 4.2 List lines as they appear on surfaces

- `tarav index lines --project [--surface]`
- **Consumers:** `hugentics/edit.md`, retrofit campaigns, `index-retrofit.md`.
- **New-model note:** this is the `Index.Secondary.Surface` read direction. Still required by
  `642` (`^c20260821-154u`), implemented nowhere in IndexLab.

### 4.3 Block grounding density

- `tarav index blocks [--limit]` — `Grounding.Density` = unique inline anchors / kernel lines,
  ascending as the enrichment worklist.
- **Consumers:** `hugentics/capture.md` (Map), enrichment passes.
- **New-model note:** derivable from `Block.Support` but no command exists.

### 4.4 Code surfaces

- project `.skw/skw.json` `code_surfaces` — typed Python/Markdown surfaces whose `$kw` annotations
  host `Index.Line`s (`index/surfaces.py:271`).
- **Consumers:** `tarav-skillware` (`Skw.Touched.Index`), `index/capture.py`
  (`Index.Capture/Surface.Lines`), every annotated file in `tarav-py`.
- **New-model note:** `642` reframes these as *dependencies from product surfaces into the Index*,
  not as distributed Index materializations. Nothing in IndexLab reads them.

---

## 5. Capture Pipeline

### 5.1 Manifest preview / land

- `tarav index capture preview|land --project --manifest <capture.json> [--limit N]`
- one `tarav.index.capture-manifest.v1` document drives: target resolution through surface parsers,
  exact message validation, side checks, hash checks, `expect.contains_all` content checks, gate
  checks, existing-anchor checks, then Anchory registration + source attachment + `LineRecord`
  creation + Chat.Index projection + final audit as one mechanical workflow.
- **Consumers:** `hugentics/capture.md` steps 6–9, `link.md` steps 4–7, `agendix.md`,
  `design-session.md`, `impl/product-capture.md`. **This is the single highest-traffic Index
  service.** 16 of the 20 `tarav index` invocations across the hugentics modules are `capture`.
- **New-model note:** IndexLab has a manifest with atomic records and rollback, but no preview,
  no content checks, no gate validation, no surface attachment, and no audit.

### 5.2 Preview must be non-mutating

- preview writes no stable surface; landing revalidates from scratch.
- **New-model note:** no successor. `indexlab capture` writes immediately.

### 5.3 Backpropagation to Chat.Index

- land also projects each exact grounded edition to the current `Chat.Index.HEAD` and, best-effort,
  to a support-derived Delta horizon; absent local support produces a *reported* head-only
  reconciliation gap rather than invented chronology.
- **Consumers:** `hugentics/capture.md`, `link.md`.
- **New-model note:** `642` supersedes the `Other.HEADs -> Chat.Index.HEAD` direction. The
  reported-gap discipline is worth keeping even so.

---

## 6. Gates And Review

### 6.1 Record a user gate

- `tarav index gate --record-id [--kind review|landing] --session --token --user-turn --agent-turn`
- **Consumers:** `hugentics/edit.md` (`::approve <token>` / `::land`), `capture.md`,
  the whole `User.Command.Section` in the Hugentics `SKILL.md`.

### 6.2 Edition approval tokens

- `Edition.Approval.Token`, minted with a proposal, upgrading materially equivalent landed lines to
  CPU-checkable `Reviewed.Content`.
- **Consumers:** `hugentics/edit.md`, `capture.md`, `issues.md` (Resolution.Line),
  `design-session.md`.
- **New-model note:** `642` demotes gates to *known mechanical assertions* under the common
  assertion carrier (`^c20260821-111u`). IndexLab retains `assertions` losslessly but lints none of
  them, so no gate is currently checkable.

### 6.3 Review closure

- `Reviewed.Cite.Closure`: reviewed content may only cite reviewed content.
- **Consumers:** `hugentics/edit.md`, the `review-closure` check.
- **New-model note:** no successor.

### 6.4 Verbatim gate

- `Line.Verbatim.Gate` — wording-sensitive index work requires the exact approved wording.
- **Consumers:** every index write path in Hugentics.

---

## 7. Conformance (Linter)

34 checks, 2 structural (`surfaces-readable`, `records-loadable`), 1 dev-lane
(`gate-verifies-dev`). Grouped by what they defend:

| Group | Checks |
|---|---|
| surface integrity | `surfaces-readable`, `records-loadable`, `alias-has-no-block` |
| line form | `line-typed`, `line-type-known`, `line-anchored`, `line-drift` |
| anchor integrity | `anchor-has-record`, `anchor-collision` |
| record form | `record-typed`, `record-label-unique`, `record-scoped`, `record-placed` |
| grounding | `record-grounded`, `support-resolves` |
| scope | `scope-resolves`, `scope-kind` |
| trace / equivalence | `trace-wellformed`, `equivalence-predecessor`, `equivalence-support`, `equivalence-rename` |
| review | `review-closure`, `review-covers-support`, `review-via-rephrase`, `review-evidence` |
| gates | `gate-verifies`, `gate-verifies-dev`, `landing-evidenced`, `landing-honored` |
| materialization | `materialization-standing`, `coverage-converges` |
| blessing | `blessing-grounded`, `blessing-orphaned` |
| self-test | `poi-test` |

**Consumers:** `hugentics/check.md`, `capture.md` (step 9 audit), `skillware/check.md`,
`tarav-py/AGENTS.md`, CI.

**New-model note:** IndexLab has 12 checks covering surface integrity, grounding, and projection.
Everything in the trace/equivalence, review, gate, and materialization rows has **no successor** —
though `642` explicitly retires the `record-placed` / materialization rows with the multi-surface
model, so those are dropped by design, not by omission.

### 7.1 Linter selection surface

- `--lane dev`, `--label`, `--record-id`, `--check`, `--skip`, `--limit`, `--poi-class`, `--poi-id`,
  `--status`, `--list-checks`, `--scope`, `--anchor`, `--coverage line|block|all`, `--show-passed`
- **New-model note:** IndexLab has none of this. `746` already records the shared selectable-check
  catalog as deliberately deferred.

### 7.2 POI explanation

- `tarav index explain --poi-class <address>` — resolves the class to its managed `$kw` block
  beside the emitting code.
- **Consumers:** `hugentics/check.md`, `skillware/check.md`.
- **New-model note:** IndexLab classes carry managed identities beside their checks, so this is
  wiring, not new design.

### 7.3 Blessing

- `tarav index bless --poi-id --body [--type] [--session] [--support ...]`
- `tarav index blessings [--poi-id]` — with derived standing
  (`grounded | ungrounded | unresolved | untouched`); only `grounded` silences.
- **Consumers:** `hugentics/check.md`, `skillware/check.md`, `references/poi-linter.md`.
- **New-model note:** no successor. A blessing is itself a grounded claim, so in the new model it
  is presumably just another record — which would be a good early test of the general envelope.

### 7.4 External check socket

- `run_linter(..., extra_checks=...)` / `register_index_commands(..., extra_linter_checks=...)`;
  bridges register at `tarav.cli` while Index modules never import them
  (`Dependency.Profile.Split`).
- **Consumers:** the Chatlas grounding-provenance check.
- **New-model note:** no successor; worth preserving as the extension point for
  `Chat.POI.Linter`.

---

## 8. Issues

- `tarav index issues --depot <depot> --json`
- `issues/NNN-issues.md`, `Issue.I####[.Dotted.Name]` blocks, every line typed and supported.
- open/resolved are **computed** from reviewed `[DC]` Resolution.Lines with exact tokenized
  approval — never folders, never cached status fields.
- **Consumers:** `hugentics/issues.md`, `session-router.md`, `workflow-status.md`.
- **New-model note:** `642` puts issue lifecycle outside the recording kernel
  (`^c20260821-78u`) — a consumer, not a kernel service. But the *computed-standing* discipline is
  a kernel-level pattern worth keeping.

---

## 9. Migration

- `tarav index import --depot-root [--depot] [--home] [--chapter]` — bring a legacy depot into the
  current layout.
- **New-model note:** `642`'s open question names conservation-first reconciliation of the existing
  Chat.Index HEAD/Delta data and the 3,974-record Bloberia corpus. This command is the precedent.

---

## Capability Gaps, Consolidated

Ordered by how many consumers break without them.

1. **Derived line standing** (§3.3) — grounded/ungrounded/live/demoted. Depended on by every
   Hugentics reasoning module. IndexLab stores support and derives nothing.
2. **Capture preview** (§5.2) — non-mutating preflight over the whole manifest. The current loop's
   safety property; IndexLab writes immediately.
3. **Reverse lookup: message → records** (§3.4) — what has already been captured from this chat.
   Required by the capture Map step; no query in that direction exists.
4. **Label resolution as a service** (§2.1) — projection-internal only, no CLI, no standing.
5. **Gate assertions being checkable** (§6.1–6.4) — `642` reclassifies gates as mechanical
   assertions, and IndexLab lints no assertions at all, so the entire approval protocol is
   currently unverifiable in the new model.
6. **Secondary-surface reconciliation** (§4.2) — `642` still requires it; nothing implements it,
   and it is the same discovery problem that produced `Record.Unplaced` 168 times.
7. **Linter selection surface** (§7.1) — already recorded as deferred.
8. **Blessing** (§7.3) — probably falls out of the general record envelope; untested.

## Explicitly Dropped By `642`

Listed so they are not mistaken for gaps:

- `record-placed` / materialization standing — the multi-surface model that produced them is
  superseded.
- Index-owned HEAD/Tail, agent/user standing flags, Chat.Index backpropagation direction.
- Trace/`Equivalence` predecessor chaining as privileged schema fields — replaced by Isoline.
- Required Markdown primary surface; chapter/appendix/agendix as kernel concerns.
- Issue lifecycle, Design.Project organization, capture profiles beyond the extension point.

## Sources

- CLI: `tarav index --help` and every subcommand's `--help`; `tarav skw --help`.
- Package: `src/tarav/index/` — `cli.py`, `linter.py`, `record/model.py`, `record/store.py`,
  `surfaces.py`, `model/identity.py`.
- Skills: all 38 modules under `tarav-md/skills/tarav-hugentics/references/` and
  `tarav-md/skills/tarav-skillware/references/`.
- Design authority for the new-model notes: `tarav-md/notes/live/642-touched-index-recording-kernel-design-session.md`.
