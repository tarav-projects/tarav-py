# 849 — Blessing attention and reassessment

<!-- tarav.sessions
1ae20f8c = codex:01a0ff32-0ec2-7b72-8850-fa795135f3c9 @1ae20f8c8159f12d2402ea702cf49c876ec46a72f71ce12423ae1dbdf2a91871
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: design ready; Wiki capture pending. Phase: Design only.

Add Tarav's reusable attention policy for continuing, judgment-based POIs. Checks keep detecting the situation; blessings and their scored Assertions affect when that same situation is offered for another review. Weakly assessed or old blessings return sooner, repeated well-supported reassessments may defer review longer up to a cap, and a user or agent can request every POI regardless of standing.

Non-goals: changing detection, granting permanent certainty, rescheduling mechanically resolved conditions such as a now-existing file, imposing one scalar score over all workflows, prescribing fixed durations or five mandatory backers, and making validation block mutation.

## Design narrative

A blessing is an attributed, revisable statement that a still-detected POI needs no action for now. It does not remove the sensor signal. The user distinguished this from a mechanically resolved POI: if the check no longer detects “file missing” after the file is created, there is nothing to revisit. For a still-detected judgment call, present a compact standing with available score-vector entries, prior review count, last review time, and a next-attention signal. The presentation layer can select a bounded attention window for an agent; direct inspection can always reveal all detections and their blessing history.
<!-- tarav.breadcrumb 19031ee131f3658f4e3711951207c9f02dda88958614e97402b291eaad619195 -->
<!-- tarav.breadcrumb 5c64033a04859cdb946969626b7566e81402048213f9e024fe1cd1ac74eb2e65 -->

Use an intentionally simple first policy, with parameters chosen in implementation after inspecting consumers: a first blessing defers briefly; later distinct reassessments may extend deferral within a cap; elapsed time and weak/missing assessment make the POI due again. Do not treat five correlated agents or repeated votes on one faulty source as independent proof. Retain each decision. A changed POI situation follows existing Tarav identity rules and must not inherit old standing accidentally. Distinguish score of support from confidence/sampling of that score. Policy consumes the vector or selected named assessments; it must not convert the whole vector into a canonical Tarav-wide truth scalar. Existing consumers may retain their present binary standing as a compatibility view until deliberately adapted; the new attention view is separate.
<!-- tarav.breadcrumb dbb2c2d659866f8ad012ddfb0ee1cddb526fb70cd7eaa038ed0d836f2932d015 -->
<!-- tarav.breadcrumb 3f4a9dbdb726c09ebc3a41832afaff726b83402599d636bca0f5fd9c3fd2e203 -->

The user said blessings “do not make the POI disappear,” that trust can increase with work and time but “should never be a 100% trust,” and proposed aging and bounded resurfacing to balance agent resources. They explicitly disliked “priority” as the primitive: the point is whether prior judgment warrants deferring attention.

Current `BlessingStore.standing()` is binary and the POI collector can still carry blessed findings. Existing `BlessingAssessmentRecord` already retains scores, but no general time-aware attention scheduler is established. Read `poi-system.md`, the POI/Checks/Blessings code, and requests 833–835 before edits. Depend on 847 for Assertable blessings and 848 for an initial scored source; the policy should also behave sensibly with unscored blessings.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`, `checks-workflow.md`, candidate `tarav-semantic-calculus.md`. Supporting chat: Codex native session `01a0ff32-0ec2-7b72-8850-fa795135f3c9` through retained Breadcrumbs. Dependencies: requests 847 and 848.

## Execution.Plan

1. Cold-read current POI collection and consumer presentation paths, blessing standing, score retrieval, and clock/test conventions. Identify one bounded agent-facing entry point for the MVP.
2. Implement a derived attention view over current detections and retained blessings/assessments. Keep all POIs discoverable; make due, deferred, and unscored states inspectable without asserting absolute truth.
3. Add a simple configurable reassessment policy with bounded deferral and age-based return, plus explicit show-all/force-review behavior. Preserve the user/agent's choice to attend a deferred POI immediately.
4. Test first blessing, repeated independent review, repeated correlated review, aging, changed POI situation, mechanically disappeared POI, and direct all-POI inspection with a controlled clock. Capture Product.Surface Breadcrumbs and run focused/proportional validation during Execute.

Acceptance: a still-triggering blessed POI remains visible in the full result; agent-facing selection can defer it and later resurface it; stronger evidence permits longer but bounded deferral; unscored or stale claims remain actionable; mechanically absent POIs are not scheduled as though still detected.

## Impl.Log

- Design only; no scheduler, presentation path, or retained blessing data changed.
- Concrete durations and formula are implementation parameters to pilot, not user-approved constants.
- Recovery: moved from temporary staging into this product repository as request 849; Chatlas and Breadcrumb evidence now live in Tarav's durable data depot. Project.Wiki capture remains pending.
