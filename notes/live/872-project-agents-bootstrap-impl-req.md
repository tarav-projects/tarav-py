# 872 — Project agents bootstrap — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: needs-alignment (three open questions below). Phase: Design.

Give every Tarav Project a checked bootstrap entry point for arriving agents. A Project's main agents file (`AGENTS.md` by default) becomes a Skillware-compiled product that must contain two sections: the **Tarav System Prompt**, shipped with the Tarav code base and identical in every Project, and a **Project System Prompt** authored by the Project. Built-in Project checks surface typed check POIs when either section is missing or stale, when the file drifts from its source, or when a declared alias file is not a symlink to the main file. The file is reachable as an object at `project.agents.agents_md`, and its checks run inside `project.checks` and therefore inside `tarav check --project`.

Non-goals:

- The wording of the Tarav System Prompt beyond a first reviewed version. It is ordinary maintained text that will evolve.
- Authoring the shipped Tarav System Prompt itself as Skillware inside `tarav-py`. It ships as plain Markdown first.
- Adopting the mechanism in the Taravangian root and in `tarav-md`. After this request those Projects are expected to report bootstrap POIs; adopting them is follow-up work in their own repositories.
- Any other member of the `project.agents` namespace.
- A scaffold or repair command. Repair is ordinary Skillware work by an agent that already has Tarav context.

## Design narrative

### Why

The User wants the minimal, "operating-system loading" level of contextualization: the thing that must be in place in a Project so that an arriving agent can hook into the harness even with no other context. The chosen first stop is the agents file, because existing agent harnesses already load it unconditionally. Every Project should carry built-in checks, inherited from the base class, that the file holds the minimal Tarav instructions; the User calls this section a Tarav system prompt and wants the root agents file to be configurable.
<!-- tarav.breadcrumb 7570c0677be3e8402bc36abac3a65310966f3c5002c823de4354e4754d79db69 -->

The section is not a short pointer. The User wants roughly one to two pages that explain core Tarav and how to get more context ("if you need this, do that"), identical across all Projects so there is homogeneity. Projects may add their own material, but Tarav does not prescribe it inside the bootstrap part.
<!-- tarav.breadcrumb 92085fbda37159cc071417b26176ad3229966260c7e3bf6da1cfc962543ea971 -->

### Mechanics decided by the User

The object is named the Tarav System Prompt. Its text is maintained in the Tarav code base like any other code. The minimal machinery is a document plus a check: when the section is not found identical in a Project, a POI is raised that points to the source file or command where the current text can be found. The same mechanics are duplicated one level down as a Project System Prompt, and a Project that defines none has a POI. The whole agents file is under Tarav control and is developed with Skillware, with its source in a skillware folder inside `.tarav/`.
<!-- tarav.breadcrumb bfed4104931c823692641ed07568808cb5b5259b41089124c03bf334fa6b6760 -->

Several agents files are supported in one way only: one main file under Skillware control, and every other declared file a symlink to it.
<!-- tarav.breadcrumb 915cd29cbe0f4fcdfd603cc9e8218f81420cd1eb7b96f70b60e27019c532495a -->

Skillware is the only path; there is no plain-text fallback tier. Bootstrap here means bootstrapping the arriving agent, not the Tarav engine. Maintaining the file is work for an agent that already has Tarav context, with the User in the loop, and a POI may say that it should be raised to the User.
<!-- tarav.breadcrumb 3d9262d078aff6f05aefcc00fe5930ae3bed24959439257ab4020e25616fcb21 -->

Findings are typed check POIs through the existing Check machinery. The agents file is a property of the Project: the Project can be asked for its path and its Skillware source, the file has its own checks, and those checks are hooked into the general Project checks run from the CLI.
<!-- tarav.breadcrumb 5a32244560f8fe7814519699963751849d33a2c186b198be84dbb769b4f948a4 -->

Every Project carries the bootstrap prompt, children included; nothing is inherited from a root. A Project may explicitly disable it in its configuration. By default a missing or stale prompt is reported.
<!-- tarav.breadcrumb bf94edede315b9931510d39b68d9c588bd588572347069d8ae7ad3db430a5227 -->

The access path is a `project.agents` namespace containing an explicitly named agents-file member, with a configuration that lists the files, one of them main. More checks, such as alias equivalence, can be added there over time.
<!-- tarav.breadcrumb 2d04a531072144d36c34530dbb489ce79c36a13434bed80eeacd2be6ac39f2e6 -->
<!-- tarav.breadcrumb 1bf101129849b033865ec45821225588235d61a6a9bbc8cd4915c75ab21cc8f4 -->

The agents file is a class object built on Skillware primitives. Its interior modeling is left to implementation judgement, and prompt wording is out of scope for this request.
<!-- tarav.breadcrumb 33fad22efcf1faf974223caf9ab7dc15b121175dcd21c073cccedc3056923339 -->

### Current behavior (inspected 2026-10-08)

- `TaravProject` (`src/tarav/l1/project/base.py`) is a `CheckProvider`, but its base `Checks.suite()` raises `NotImplementedError`. `PythonPackageProject`, `DocsProject` (`l2/project/dev.py`) and `RootProject` (`l2/project/root.py`) each override `Checks.suite()` completely. Request 866 established that suites are composed explicitly; there is no automatic merger.
- Harness-scaffolded Project types subclass `TaravProject` directly (`l2/project/harness.py`, `_project_source`), so anything meant for every Project must live at `l1`.
- Marker extras are read from the retained Record, as `RootProject.child_paths()` does with `children`.
- `tarav.l1.skw.document.Document` is the generic Skillware document. Its `lint()` already reports `source-uncompiled`, `product-drift` and `product-unavailable`. It requires the output inside `root` and outside `root/.skw`, and hard-codes the depot as `root/.skw` for discovery, `lock.json` and `generations/`.
- `SkillLink` (`l1/skw/skills.py`) is the existing pattern for a typed block with a code producer: `produce()` computes the content, and `output_findings()` reports `stale-produced-output` when retained content differs.
- Check and POI types are declared as in `l2/project/dev.py` (`ProvisionalMarkersCheck`, `ProvisionalMarkerPOI`). `l2/skw/pois.py` maps Skillware findings to POI classes but is above `l1`.
- No Project in the workspace has a `CLAUDE.md` or other alias today.

### Proposed design (agent proposal, not yet User-approved in detail)

**Module.** A new `tarav.l1.project.agents` holds everything below. It imports `tarav.l1.skw` (same layer) and nothing higher.

**Namespace and object.** `TaravProject.agents` returns a bound `Agents` namespace (`NamespaceBase`). `agents.agents_md` returns an `AgentsMd` object with:

- `path`: the main file, `<root>/<main>`;
- `source`: its Skillware source document path;
- `aliases`: the declared alias paths;
- `document()`: the loaded Skillware `Document`;
- `checks`: its own `CheckProvider` namespace.

**Configuration.** An optional `agents` object in the Project marker:

```json
"agents": {
  "main": "AGENTS.md",
  "aliases": ["CLAUDE.md"],
  "tarav_system_prompt": true,
  "project_system_prompt": true
}
```

Defaults: `main` is `AGENTS.md`, no aliases, both prompts enabled. Setting a prompt to `false` is the explicit opt-out; its check is then not produced.

**Source location.** The source is `<root>/.tarav/skillware/src/AGENTS.skw.json` and compiles to `<root>/AGENTS.md`. This needs `Document` to accept an explicit depot directory instead of assuming `root/.skw` (see open question 1).

**Two typed blocks.**

- `Tarav.Project.Agents.TaravSystemPrompt`: its `produce()` returns the lines of the shipped prompt, and `output_findings()` reports `stale-produced-output` when retained content differs, following `SkillLink`. Refreshing it is the existing `document produce` followed by `compile`.
- `Tarav.Project.Agents.ProjectSystemPrompt`: an authored block. Tarav checks only that it exists and has content.

Both are registered with the runtime Record registries next to the existing Skillware block types.

**Shipped text.** `src/tarav/l1/project/tarav-system-prompt.md`, read relative to the module. A first version follows the outline discussed in the design session: what Tarav is, how to operate it, how to get more context, and the behavioural contract. It lists only mechanisms that work today.

**Checks and POIs.** `AgentsMd.Checks.suite()` yields:

| Check | POI type | Codes |
| --- | --- | --- |
| `TaravSystemPromptCheck` | `TaravSystemPromptPOI` | `no-source`, `missing`, `stale` |
| `ProjectSystemPromptCheck` | `ProjectSystemPromptPOI` | `no-source`, `missing`, `empty` |
| `AgentsMdProductCheck` | `AgentsMdProductPOI` | the `Document.lint()` kind, for example `product-drift` |
| `AgentsAliasCheck` | `AgentsAliasPOI` | `missing`, `not-symlink`, `wrong-target` |

Each POI's details carry the path of the shipped prompt or of the Project's source, so the reader knows where to look. Skillware lint findings get one local POI type because `l2/skw/pois.py` cannot be imported from `l1`.

**Composition.** `TaravProject.Checks.suite()` stops raising and returns a suite containing `agents.agents_md.checks.suite()`. The three existing overrides include `super().suite()` first. This is explicit composition through ordinary inheritance, consistent with 866. A Project type that overrides `suite()` without calling `super()` loses the bootstrap checks; that is visible in its code and accepted.

### Informative alternatives

- A depot at `<root>/.skw/` needs no engine change, but departs from the User's stated `.tarav/` location and adds a second dot-folder to every Project.
- Carrying the feature on `Project` (`l2`) would allow reuse of `l2/skw/pois.py`, but harness-scaffolded Projects would not get it.
- Byte-equality checks for alias files were discussed and replaced by the symlink-only rule.

### Open questions

1. **Depot location.** Confirm `.tarav/skillware/` with a small `Document` change to accept an explicit depot, rather than `<root>/.skw/` with no engine change.
2. **Carrier class.** Confirm `TaravProject` rather than `Project`. The agent recommended it after the "every Project" decision; the User has not answered directly.
3. **Opt-out granularity.** Confirm one switch per prompt rather than a single switch.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `projects.md`, `skillware.md`, `checks-workflow.md`, `poi-system.md`, `tarav-harness.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. **Skillware depot parameter.** Let `Document` take an explicit depot directory, used for source discovery, the output exclusion rule, `lock.json` and `generations/`. Default behavior is unchanged. Verify with the existing Skillware tests plus one test of a non-default depot.
2. **Shipped prompt and typed blocks.** Add `tarav-system-prompt.md`, the two block types, their registry entries, and confirm the Markdown file is included in the built wheel. Test `produce()` and the stale finding. Present the first prompt text to the User before landing it.
3. **`project.agents`.** Add the namespace, `AgentsMd`, and marker configuration with defaults. Test path resolution, defaults, aliases, and both opt-outs.
4. **Checks and POIs.** Add the four checks and POI types. Test each code against temporary Projects: no source, missing block, stale block, empty Project prompt, product drift, alias missing, alias a regular file, alias pointing elsewhere, and the clean case.
5. **Composition.** Give `TaravProject.Checks.suite()` the agents suite and add `super().suite()` to `PythonPackageProject`, `DocsProject` and `RootProject`. Update `test_project_dev.py` and `test_project_tree.py` expectations; confirm a bare scaffolded Project now reports bootstrap POIs through `tarav check --project` instead of "declares no checks".
6. **Adopt in `tarav-py`.** Import the current `AGENTS.md` into `.tarav/skillware/src/AGENTS.skw.json` byte-for-byte as blocks, add the two prompt blocks, compile, and confirm the bootstrap checks are clean for this Project. The existing Read-first and Project-model sections are the natural Project System Prompt.
7. **Guidance and closure.** Update `AGENTS.md` (through its new source) and `ARCHITECTURE.md` for the new module and contract. Run the full test suite and Ruff, reinstall the CLI, run `tarav check --project` at the root and record the expected POIs for the root and `tarav-md`. Inlined Capture on each changed surface, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): `l1/project/base.py`, `l2/project/__init__.py`, `dev.py`, `root.py`, `harness.py`, `l1/checks`, `l1/skw/document.py`, `l1/skw/skills.py`, `l1/skw/depot.py`, `l3/check.py`, child markers, request 866. The `tarav-py` worktree has many unrelated uncommitted edits, including `src/tarav/l1/project/base.py` and `ARCHITECTURE.md`; Execute must preserve them and checkpoint only its declared scope.
- Observation: the Taravangian root folder is not a Git repository, so its future `.tarav/skillware/` source would be unversioned. This matters for the follow-up adoption, not for this request.
- Related change in the same session, outside this request: the `--ground` module was removed from the `tarav-hugentics` skill in `tarav-md`; those edits are uncommitted there.
- Design note capture: ten User-Turn Breadcrumbs submitted, audit clean; design commit `d20852a2ff2d14cd89434111762b44da23aebe0c`.
- Wiki capture in `tarav-md`: new topical note `notes/wiki/agents-bootstrap.md` (18 Breadcrumbs, audit clean) and a section in daily `2026-10-08.md` (4 Breadcrumbs). Start checkpoint `2475a09ffa2be619defc55a3118850b37627e2ca`, completion commit `2b017f3321a5be69b41ab9852d2a2b098c9d3adb`.
- Capture POI: declaring this session at the top of the existing daily note shifted its 13 earlier Breadcrumbs down one line, and their audit now reports `breadcrumb-position-missing`. Positions are observed only at submission and there is no re-observe command, so this was left unrepaired.
