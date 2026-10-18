# 890 — Neutral POIs: guidance out of the POI — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design.
Status: superseded by request 893. The destination was decided: the POI's
context, and the action's skill when the POI is followed by an action.

A POI states what its producer knows: the check that raised it, the
situation, the evidence and a descriptive message. What a reader should do is
not the POI's to say. Move the "what to do" guidance (`may_do`, and the part
of `read_first` that is not producer knowledge) out of POI Types and into the
context a reader opens.

Non-goals: typed subjects and precedent; Directives and conditioned context;
repairing existing POIs in Projects.

## Design narrative

A POI connects above all to the code and the situation that produced it. Its
job is to narrow the gap between producer and reader so the reader can judge
with all the available information. The producer cannot know the reader's
goal, and the design does not pretend otherwise.
<!-- tarav.breadcrumb c3a3d1556fd7 -->

Perhaps the mistake is that "what to do" is on the POI at all: that belongs to
the skill contextualizing the agent. The POI gives evidence and clear producer
intention, plus tooling for getting more context. Its wording is descriptive,
not imperative (`Workflow.Neutral`).
<!-- tarav.breadcrumb 523e4e6a5115 -->
<!-- tarav.breadcrumb 233a28074d10 -->

`may_do` must move out of the POI and can be part of the context. The POI is
concerned with the immediate producer description: the triggered check and the
situation. The agent goes to the context and decides. A skill can prime the
agent on what to look for and can provide a typed Context view.
<!-- tarav.breadcrumb 00726a1656bb -->

The User also raised a typed Message: the POI has a message, and guidance
could be modelled on the Message Type, freeing the POI from it. The User said
this is the point of least clarity: the structure must be simple and primitive
enough to fit every scenario and must not mislead agents.
<!-- tarav.breadcrumb aa8834332d60 -->

`Workflow.Neutral` is the good practice when the reader's context is unknown.
<!-- tarav.breadcrumb 374bf0223d35 -->

### Current behavior (observed 2026-10-09)

- A POI Type may set class attributes `read_first` and `may_do`;
  `guidance_of()` in `src/tarav/l1/poi/reporting.py` reads them, the reported
  POI record stores them as `guidance`, and `ReportedPOIContext` shows them.
- About forty Types set them, mostly in `src/tarav/l1/project/agents.py` and
  `src/tarav/l1/project/skills.py`, also in `l1/checks/poi_contract.py`,
  `l1/poi_tracking/__init__.py` and `l2/unsorted/pois.py`. Many `may_do`
  entries are imperative ("Raise it first.", "Replace the alias by a
  symlink").
- `POIGuidanceCheck` (`l1/checks/poi_contract.py`) raises a POI for every
  local POI Type that declares neither. It demands what this request removes.
- Named Context views are registered per workflow
  (`ContextQueryService.register_view`); a view declares which subjects it
  supports.

### Options for where guidance goes (not decided)

1. **Context entries owned by the producing workflow.** The workflow that
   defines the POI Type registers a contributor that adds a guidance entry to
   the POI's context. The text leaves the class; the POI record no longer
   stores it.
2. **A typed Message.** The POI holds a Message object; a Message Type may
   carry descriptive guidance. The POI Type supplies a default.
3. **Reader-side only.** Guidance lives in the skills of the workflows that
   read POIs; Tarav code carries none.

Agent lean, not decided: option 1 for what the producer knows (what the POI
means, where its code is), rewritten descriptively; option 3 for what to do.
`read_first` entries that point to producer documentation stay as producer
knowledge. `POIGuidanceCheck` then checks that a Type's context is not empty
for an unprimed reader, or is retired.

### Open questions

- Which option, or which mix?
- Does `read_first` stay, renamed, as producer knowledge?
- What replaces `POIGuidanceCheck`?
- Is the forty-Type rewrite one request or done per workflow?
- Retained reported-POI records already store `guidance`; are they left as
  they are?

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`poi-system.md` (section of 2026-10-09), `operator-context.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done (Wiki notes written 2026-10-09).

## Execution.Plan

Not planned until the destination is chosen. Expected shape: start
checkpoint; the chosen mechanism with tests; move the Types one workflow at a
time; adjust the reported view, the tracking view and `POIGuidanceCheck`;
update the POI README and the Tarav System Prompt text if it names the
fields; full suite and a Project check on this workspace.

## Impl.Log

- Designed 2026-10-09. Not executed.
