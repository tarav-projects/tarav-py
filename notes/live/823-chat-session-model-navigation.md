# ChatSession and Model navigation

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Design. Alignment.Mode: Interactive.
Status: ready for bounded execution with the proposals below; no product code
implemented in this pass.

Introduce ChatSession as a navigable Tarav object representing a conversation,
distinct from its retained Normal Model. Deliver session selection and
session.model(); preserve existing retained formats. Turn/Message/Event
Explorer collections are follow-up work, not part of this first slice.

Non-goals: capture provider data automatically, redesign normalization or hash
schemes, create a session state machine, add Program/Project attachments,
replace Query, or require every Session to have an available Model.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki.
Relevant note: chatlas-normal-model.md.
Evidence: codex:01a0d86c-9538-7be1-af96-014cd4203d61,
identity 6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.
User turns: 8fb511e28962dea0 (ChatSession versus representation),
11718ab85fa5d275 (navigation tree), 44d2a3d2feca6b77 (accepted interface and
bounded first slice, Design request).
Capture destinations: chatlas-normal-model.md and daily/2026-09-28.md.

## Current implementation evidence

All paths below are under src/tarav/l1/chatlas/.

- session_identity.py hashes provider, instance and native session ID under
  the existing versioned identity schema. A native ID alone is not globally
  unambiguous; do not drop the instance dimension.
- session_resolver.py resolves exactly one indexed row, raising for missing or
  ambiguous selectors. Reuse this behavior rather than choose the newest match.
- normal_model/model.py: NormalModelSession is embedded Pydantic metadata;
  ChatlasNormalModel is an existing registered DirectoryRecord with source,
  counts, canonical main.json and JSONL collections.
- normal_model/normal_model.py exposes provide_normal_model_reader(), resolving
  the index and delegating materialization/freshness to normal_model_cache.py.
- workflow.py owns registration under the existing ChatlasWorkflow. A new
  Session Type needs its own class entity, not another Workflow.

## Proposed first-slice interface

```python
from tarav.l1.chatlas.sessions import ChatSessions

sessions = ChatSessions(chatlas_root=root, provider="codex")
session = sessions.get(session_id).open()
model = session.model()
```

ChatSessions is an ExplorerFolder view over retained Session Index rows.
Its provider and instance filters narrow lookup; get(key) accepts an exact
native session ID within that scope and rejects ambiguity. Entries have cheap
metadata and open ChatSession without normalizing or capturing anything.
Expose exact identity-hash selection as a named alternative (for example
get_by_identity(identity_hash=...)); never guess whether an arbitrary string
is a native ID or a hash. Listing entry keys must round-trip through selection:
if the unscoped view contains duplicate native IDs, require scope for native-ID
listing or use identity keys with an explicit documented selector. Resolve this
small API detail in implementation before claiming Explorer conformance.

ChatSession initially subclasses TaravObject, preserving identity_hash as the
existing Chatlas identity alongside provider, instance and session_id. This is
an implementation proposal: do not invent a new UUID merely to force this hash
into TaravEntity's Ship contract. Its class has a normal TypeShip and Chatlas
ownership. A future Ship mapping, if needed, is a separate identity decision.

The Record contains the portable session selector, not an index snapshot or
machine-local cache path. chatlas_root is runtime configuration. A deserialized
object uses the normal default root unless explicitly rebound; test that custom
roots remain isolated. Construction validates selector shape and hash agreement
using the existing identity function, without requiring a Model to exist.

session.model() returns the existing ChatlasNormalModel reader, resolving the
same exact session through retained data. It can create/reuse derived cache
files under the existing reader contract; it never captures provider data.
An explicit refresh keyword may delegate existing cache rebuilding semantics;
it is not a provider update. Missing, unsupported or unavailable sources surface
existing errors, not an invented empty conversation or a mandatory Model field.

Keep sessions.py as a consumer above capture/index and normalization modules,
with no reverse imports from those modules. Do not make the chatlas package
initializer eagerly import all consumers. Domain objects need not themselves
be ExplorerFolders; their collection views provide navigation mechanics.

## Execution.Plan

- [ ] Cold-read current instructions and source; checkpoint existing product
  work according to Execute policy before edits. Preserve concurrent changes.
- [ ] Inspect ExplorerFolder/Entry contracts and index row schema; settle an
  unambiguous, round-trippable collection key convention as described above.
- [ ] Implement ChatSession's class entity, portable Record and runtime root
  binding. Register it in the existing runtime's trusted Record Types.
- [ ] Implement the thin indexed session view and entry opener, delegating
  exact lookup rather than adding a second index or resolution algorithm.
- [ ] Delegate model() to the existing reader; preserve all existing Model,
  Turn, Message, Event and evidence-reference representations.
- [ ] Add fixtures and tests below; update architecture and capture the result.

## Acceptance and verification

- Selecting/opening a session neither captures data nor builds a Model; test
  with spies and temporary depots, not the user's live session store.
- Provider/instance collisions raise explicitly; exact identities select the
  intended session. Listing and entry selection agree, including empty views.
- Record round trips preserve identity and source selectors, and dynamic loading
  returns ChatSession. Invalid hash/selector combinations do not silently repair.
- model() returns ChatlasNormalModel for the same session; repeated access uses
  the existing cache policy. Absent source and unsupported normalization errors
  remain inspectable; Session construction itself is independent of availability.
- Custom roots do not fall through to the default depot. No provider-home writes.
- Existing CLI, Query, reference and normalization tests retain their semantics.
- Run focused new Session and Explorer tests plus tests/chatlas_normal_model,
  tests/kernel and tests/test_architecture.py. Run full pytest and Ruff before
  handoff. No new global dependency-enforcement machinery.

## Impl.Log

- Inspected existing identity, resolver, reader, Normal Model and registration
  boundaries. No product edits or tests executed in Design.
- The object-versus-Entity and collection-key details above are implementation
  proposals, not additional user decisions. No new session identity is assigned.
- Captured the supported discussion in Wiki chatlas-normal-model.md and
  daily/2026-09-28.md. Both Breadcrumb audits passed with no findings.
  Wiki-only closure commit: cef2a5f9aee6819e553702b5f721975de7fc0fa2.
