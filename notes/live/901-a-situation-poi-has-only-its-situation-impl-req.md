# 901 — A SituationPOI has only its situation — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: ready.

The base class of POIs that have an identity carried three things beside the
situation: `subject`, `evidence` and a second name for the subject,
`coordinate`. None was defined, and a check POI filled the first two with a
copy of its `details`. This request reduces the base to what it means.

1. `POI` has a Type and a message.
2. `IdentifiedPOI` is renamed `SituationPOI`. It adds a situation, an object
   describing it; the identity is the Type plus the situation. Nothing else
   is required or offered there.
3. A specialization adds its own fields as attributes of its Type, named
   for what they hold.
4. Each POI line that passed `subject` or `evidence` is sorted: a repeat of
   the situation goes away, real data becomes a field of that line.
5. Readers stop reading `subject` and `evidence` generically.
6. The action records are deleted and reopened, since the POI they keep
   changes shape.

Non-goals: what a line puts inside its situation, which includes the state
the Skillware line keeps there; the capability markers; blessing.

Follow-up in another repository:
`vscode-tarav-center/notes/live/010-read-the-situation-of-a-poi-impl-req.md`.

## Design narrative

### User decisions

Fixing a drift made 28 actions close and 28 open although two things had
changed. The agent proposed a three-part POI: subject, state, evidence.
<!-- tarav.breadcrumb dd4a33b00b80b1ee70266e34b1cd8d3207edc1d245b9c574107e8bfb783ba8fe -->

The user did not recognise that as the POI model and asked for the current
one from first principles.
<!-- tarav.breadcrumb 24911fafb82564e442560c8a2455db7591ec7789326c1874a8738d58ccee5719 -->

A particular implementation line of POIs must be told apart from a general
principle. The user asked for a tree of the lines.
<!-- tarav.breadcrumb 7aaa662011c7be1712cddff859384f75f0af3f54f7aa1b6237741e02bdd654a1 -->

`IdentifiedPOI` is renamed `SituationPOI`. It only prescribes that the
situation is a `LiteRecord`. More can be modeled inside a situation, but the
fundamental philosophy does not care: an object describing the situation is
put there. The situation needs no structure that is common across POIs.
A blessing does more than close an action: it can also suppress a POI from
showing.
<!-- tarav.breadcrumb 8df20c46efd8d7019b2f8130272d8194a8ad626f4419715511131657cc02e639 -->

`subject` and `evidence` should not be part of the base model, at least not
without clear fundamentals.
<!-- tarav.breadcrumb c2b89e0a68a23bb75e54e343e89943a650ac7d41ee0cf1480688227fcc96e39d -->

At the level of a `SituationPOI` only a situation field is required, plus
what comes from the other base, like the message. Other Types or
specializations can add other fields: POIs are subtypes, and the whole
expressivity of the Python type system is there. The base is Type, message
and situation. What is wanted is a clear and simple model without
ambiguities.
<!-- tarav.breadcrumb 510ea9812b87e15684ad22fdd8d399f630042955348a520a33887c689f195750 -->

The user asked whether `subject`, `evidence` and `coordinate` were well
defined.
<!-- tarav.breadcrumb a07cc6e1a3ea23befe2ee4883b766fdff8d4fd6b8915428d6d5dbf08746ec16d -->

Write the request and build it.
<!-- tarav.breadcrumb 63e37beec4d78000d4333b72b99c578f9fa1a36db2a935dd41342e8735bb6e2b -->

### Current behavior (inspected)

- `IdentifiedPOI(message, situation, subject=None, evidence=None)`
  (`l1/poi/primitives.py`). The identity is the Type plus the situation.
  `coordinate` returns the subject.
- The only written definition is negative: evidence and presentation "do not
  create a second identity axis". `subject` and `coordinate` have none.
- `CheckPOI` adds `check`, `details` and `failure`, and fills `subject` and
  `evidence` with a copy of `details` when they are not given.
- What the lines pass:
  - Skillware: `subject` repeats what is inside the situation; `evidence`
    is the same object as `details`.
  - Tribunal scores, Workspaces: `subject` repeats part of the situation.
  - Records provider error: `subject` equals the situation; `evidence` is
    the error.
  - Skillware generation: both repeat attributes the POI already has.
  - Skills status: `subject` is the situation itself; `evidence` is what was
    seen of the depot entry.
  - Reference resolution: `evidence` is the hints.
  - Breadcrumb resolution: `evidence` is a count of positions.
  - Diagram: `evidence` is a free mapping given by each caller.
  - Action closed: `subject` is the Project; `evidence` names the action.

### Proposals of the agent

**Base.** `POI(message)`. `SituationPOI(message, *, situation)` with
`identity`, `situation`, and `as_dict()` giving type, id, message and
situation. `describe()` gives that plus what the Types say.

**Check POIs.** `CheckPOI(check, message, *, situation, details, failure)`
keeps its three fields. `SituationCheck.poi()` loses `subject` and
`evidence`.

**Lines.** Skillware, tribunal scores, Workspaces and Skillware generation
drop the repeats. A line that held real data declares it: `error` on the
records provider error, `entry` on a skills status POI, `hints` on a
reference resolution POI, `positions` on an ambiguous Breadcrumb position,
`project` and `closed` on an action closed. The Diagram line keeps a field
of its own named `evidence`: its callers are in files other agents are
changing, and the line's base class now says what the field is.

**Readers.** The action record keeps `as_dict(detail=True)` of its POI as
before; that no longer has `subject` or `evidence`.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-12.md`. Supporting chat: session `abd0372d` above.
Capture status: pending.

## Execution.Plan

1. Base: `POI.message`, rename, reduce.
2. Check POIs and `SituationCheck.poi()`.
3. Lines, one by one, as sorted above.
4. Readers and tests; full suite and Ruff.
5. Delete the action records; real run.
6. README, architecture text, extension request 010, Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-12.
