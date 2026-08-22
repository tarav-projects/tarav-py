# 752 — Unified POI.Linter design session

## Note.Abstract

- **Purpose:** capture the design conversation that recovers a single `POI.Linter` model from the
  three forking layers now in `tarav-py`, and record the first-principles derivation that settles
  the status vocabulary and the severity question.
- **Session:** `9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5`
- **Status:** discussion only. Nothing edited, nothing committed. The conclusions below are
  aligned in chat but not yet landed in any design surface.
- **Method:** every claim below was read from the tree during the session, not recalled. Where a
  claim was found wrong mid-session it is marked as corrected rather than removed.

---

## 1. The scanned state

### Three shared layers, not one

| Layer | Provides | Consumers |
|---|---|---|
| `tarav.poi` | `POIInstance`, `POILocation`, `POISeverity`, `POICatalog`, `POIDiagnostic`, `POILinterReport`, `SelectableCheck`, renderer, discovery, adapters | index (partially), skillware, anchory, canvas, chatlas, tournament |
| `tarav.poi.runtime` | `Status`, `Evaluator`, `Tier`, `GateResult`, `Finding`, `Check`, `LintReport`, `run_checks` | IndexLab |
| `tarav.index.verdict` | its own `Status`, `Evaluator`, `GateResult` | index |

`poi/__init__.py` re-exports the first and second side by side, so the public `tarav.poi` API now
carries **two complete, unrelated linter vocabularies**. `tarav.index.linter` — the reference
implementation `poi.runtime` was extracted from — consumes neither.

### The class corpus

164 classes declared in `tarav-py/src`: `Index.Linter` 93, `Skillware.Linter` 23, `IndexLab.Linter`
13, `Anchory.Linter` 9, `Markdown.Block.Linter` 7, `Index.Evaluator` 5, `Canvas.Linter` 5,
`Tournament.Linter` 3, `Index.Capture` 3, `Wayfinder.Registry.Linter` 2, `Bloberia.Linter` 1.

Plus 10 more outside the codebase: `tarav-chatlas-md/skills/tarav-chatlas-pkg/poi/101-poi.md`
declares ten classes in the **retired markdown-catalog pattern**, all in the `Index.Linter/`
namespace it does not own.

### The general model has drifted behind its realization

Keyword counts across `tarav-pkg`:

| term | `107` (general) | `104` (Index) | `references/poi-linter.md` |
|---|---|---|---|
| `blocked` | 0 | 1 | 9 |
| `verified` | 0 | 0 | 3 |
| `severity` | 0 | 0 | 3 |
| `Evaluator` | 0 | 0 | 0 |
| `GateResult` | 0 | 0 | 0 |
| `narrow` | 1 | 0 | 11 |

`107` describes a binary emit-or-don't linter. `Evaluator` and `GateResult` appear in no markdown
surface at all — they exist only in Python. `104` is 11 lines and names `POI.Linter` once without
defining tier, verdict, narrowing, or gating. `107` never names `Index.Linter`: the general model
does not know what realizes it, which is why the other eight linters drifted unchecked.

### The severity contradiction, made executable

`poi/model.py:48` requires `severity: POISeverity` and validates `error | warning | advisory`.
`index/verdict.py:31` and `references/poi-linter.md:68` both say there is deliberately no severity,
because it is the route by which semantics gets smuggled back into the signal. The collision is at
`index/report.py:270`, which hardcodes `severity="error"` to satisfy a type it rejects in doctrine.

`POIDiagnostic` carries the same field with the same defect (`severity: str = "error"`).

---

## 2. The derivation

The linter's value is not detection — grep detects. Its value is that output is **addressed**: a
name that resolves to documented prior alignment. Signal → class → documentation → what was already
decided. That escalation path is the product.

Which gives one test for every field in a report:

> does this help the agent reach the right documentation, or does it substitute for reading it?

- class reference — *is* the path
- subject / surface — where to look
- evidence / operands — what the agent reasons with after arriving
- **severity — a summary of what the documentation says, computed by something that never read it.**
  A shortcut around the path, offered to an agent that would otherwise have walked it.

Stated as **is vs ought**: the linter reports what *is* — mechanically observed, verifiable, no
opinion. The documentation says what *ought* to be. The linter notices a mismatch and addresses it;
it never states the ought, because the ought lives at the other end of the pointer.

The payoff is that **the ought can be revised without touching code**. Edit the documented block and
every finding immediately means something new.

---

## 3. The status vocabulary

Four values, aligned in session. They are not degrees of badness — they name **which door the agent
walks through**:

| status | ran? | knowledge | escalate to |
|---|---|---|---|
| `passed` | to completion | positive | nowhere |
| `failed` | to completion | positive | the POI documentation — the *subject* is wrong |
| `blocked` | never started | none — expected | the run configuration — something wasn't supplied |
| `error` | started, died | none — unexpected | the linter's source — the *tool* is wrong |

- `blocked` is expected; `error` is a bug. Collapsing them hides linter defects inside normal
  operation permanently, because a blocked run looks routine.
- `verified` must require zero of **both** bottom rows. Both mean "we did not actually look."
- Status lives on the **check**. A POI instance has no status and no severity — only class →
  documentation. Instance-level status is severity under another name.

### Error attribution

Attribution to a class is legitimate **only where it is true**, because a false class reference
sends the agent down a documentation path unrelated to the failure — strictly worse than no path.

- error raised while constructing a finding for class C → the class is already determined; surface
  it. The agent needs both doors.
- error before any finding, outside a check, or on an unmet Floor → **no class is true**. Fall back
  to an unattributed runtime error carrying its message.

This dissolves the multi-class ambiguity: do not pick one, do not list all. Attribute only where
attribution is a fact.

Open defect: `Check.poi_classes` (`poi/runtime.py:104`) returns a `frozenset[str]` computed by
scraping the check function's source (`_referenced_poi_classes`). The class↔check binding is
inferred rather than declared, so it changes silently when a body is edited. If blocked/errored
checks report through their class, this binding must become explicit and probably singular.

---

## 4. Two channels, already present

The old model already draws the right cut. `poi/linter.py:1` says so verbatim: *"common report keeps
POIs diagnostics summaries and domain data distinct"* — `POIReport.instances` (class-addressed) vs
`POIDiagnostic` (message-carrying).

The discriminator, restated:

- something wrong with the **subject** → POI. Classed, located, documented.
- something wrong with the **observation** → message. The linter couldn't look. No class, because
  there is nothing to document.

Worked example: a record that will not deserialize is a defect *in the data* → POI. "Chatlas will
not resolve" is a defect *in the run* → message.

**So the recovery is a narrowing of the existing two-channel model, not a rewrite:** drop severity
from both channels, re-scope diagnostics to run-addressed entries only, put the four-value status on
checks.

On the exception analogy — it holds, with three limits:

1. **Blocks must not unwind.** One unreadable surface must not convert a full run into a short clean
   report. Collect-and-continue, as `projection.py:fold_records` already does.
2. **The message must not be the only payload.** Attributing a failure by parsing message text is
   not an identity relation — carry the structured cause alongside, as `ProjectionError.record_id`
   now does.
3. **Do not mint an error taxonomy.** For `error`, the underlying exception type plus the cause is
   enough. Named, documented error types rebuild POI classes one level down, for the linter's own
   bugs.

---

## 5. Consequences worth acting on later

- **Class names must name the observed condition, not the verdict.** `Anchor.Unresolvable` passes —
  checkable. A name like `Bad.Indexing` fails: "bad" is the ought, welded into an identifier where
  no documentation can revise it. This is auditable across all 174 classes.
- **"Every class reference resolves to a documented block" becomes a conformance check the linter
  can run on itself.** The Chatlas ten fail it today.
- **The linter is semantics-free per finding, not semantics-free.** Deciding that unresolvable
  anchors are worth checking is a value judgment — concentrated in the **catalog** rather than
  smeared across reports. That is why the catalog earns review discipline and the runtime does not.
- **Before scoping severity removal**, separate sites that bind `POISeverity` from sites that merely
  have a variable named `severity`. 20 files match; `mdblocks/core.py` (13 hits) and `anchory/core.py`
  are likely carrying an unrelated notion.
- `Check.resolutions` is **not** a violation and should be the template for anything else wanting to
  live on a check. `index/linter.py:284` already draws the line: resolutions survive precisely
  because they are not derivable from the body — alternatives to choose between, never a
  recommendation. The linter enumerates the moves and refuses to choose.

---

## 6. Corrected in session

- **"Old reports lying around" was wrong.** Linter reports are not persisted — `lint()` builds a
  document and `render_linter_text` prints it. Findings are recomputed every run.
  The durable state is the **blessing** (`index/linter.py:1425`, `BlessingStore.put`), described in
  its own docstring as *"the one piece of state whose purpose is to stop the checker, so it is the
  last place an unevidenced agent value could survive."* A blessing stores the class name, the line's
  type and body, and its support refs — so it is keyed to a class whose documentation can be revised
  underneath it. That is where the is/ought split actually bites, and the design already treats it as
  the dangerous place: `blessing_standing` re-derives `GROUNDED | UNRESOLVED | UNTOUCHED`, and
  `Index.Linter/Blessing.Ungrounded` makes an unevidenced blessing a finding. The loop closes.
- **`Check.resolutions` was nearly flagged as prescriptive creep.** It is not; see §5.

---

## 7. In flight by other agents

Recorded so this note is not read as the only current position:

- `src/tarav/poi/runtime.py` and `tests/test_poi_runtime.py` were **untracked** at scan time.
- `notes/live/749-indexlab-poi-linter-impl-req.md` declares itself completed, uncommitted.
- `notes/live/751-poi-check-classes-impl-req.md` is ready for execution and moves `POI.Check` to
  instantiated classes with `run()`, using **the check class as the POI documentation attachment
  point**. That is consistent with §2 and would give §3's error attribution a declared binding
  instead of the scraped one.
- HEAD moved three times during the session.

## 8. Not settled

- whether `tarav.index.linter` migrates onto the shared runtime, or the shared runtime is redefined
  around it
- what happens to the five realizations genuinely using `POISeverity`
- where the recovered design lands: `107` is the general model but is behind; `104` is explicitly
  off-limits by user instruction; `references/poi-linter.md` currently holds the real design
- the Chatlas namespace squat, and its retired declaration pattern
