# 873 — Project skills bootstrap — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: complete. Phase: Execute.

Give every Tarav Project built-in checks that the skills an arriving agent needs are available. This is the second bootstrap level, after the agents file of [Impl.Req 872](872-project-agents-bootstrap-impl-req.md). Two skills are required: the **Tarav package skill**, whose name is fixed in Tarav code, and the **Project package skill**, which each Project names in its configuration. A skill is available when a skill with that declared name is found in the Project's `.agents/skills` folder or in the home folder's `.agents/skills`. Further checks confirm the minimal folder structure: `.agents/skills` exists, and `.claude/skills` leads to the same place, in both the Project and the home folder. Findings are typed check POIs and run inside `project.checks`, therefore inside `tarav check --project`.

Dependency: this request builds on 872. It adds to the `project.agents` namespace, the `agents` entry of the Project marker, and the `TaravProject.Checks.suite()` composition that 872 introduces. Execute it after 872 and follow whatever 872's open questions resolve to, in particular its carrier class.

Non-goals:

- Checking whether an installed skill is current with its source.
- Changing `tarav project skills` or its depot mechanics.
- Adopting or repairing any Project's skill folders.
- Configurable search places, and any opt-out, in this slice.

## Design narrative

### Why

The User wants a second minimal entry point for contextualization: skills. A Tarav Project is the Tarav version of the folder-rooted project that agent harnesses such as Codex and Claude Code already use, so the Project object should know about the skills an agent started in that folder would have, and should check that specific skills are available. The first such check is that the Tarav package skill is available, because that skill is meant to be the documentation system behind the short bootstrap text. The second level is that every Project demands a Project package skill: the entry point to the skill part of that Project. That skill need not be developed in the Project, and several Projects may point to the same one, as `tarav-py` and `tarav-md` both point to the Tarav package skill.
<!-- tarav.breadcrumb bd7228d460687290c8560ba24e1c00932cd05a0de1ac35faf3d44c2a3ea7b6d6 -->

### Mechanics decided by the User

The name of the Tarav package skill is hard-coded in Tarav, since the check itself ships with Tarav. The Project package skill is named in the Project's configuration. Nothing else is configured.
<!-- tarav.breadcrumb 7a0a5a4285db1a3761d82422cc455b7c4ca919085cc0b4fd1edde777161414d9 -->

The check is about presence only. The search places are fixed and not configurable for now: `.agents/skills` in the Project and `.agents/skills` in the home folder. Tarav may start rigid and add configuration later.
<!-- tarav.breadcrumb b4e4d460fa53e9098e5903ee6cea2615a8486bde587a597920d931e7991ee66e -->

A skill needs a model for this purpose: a minimal object that describes a skill from the outside, by looking at its folder, with just enough for identity. It does not need to be a Skillware skill, although a Skillware skill can be one. How that object is built is an implementation detail.
<!-- tarav.breadcrumb e133f527cfd3419b586d2c7df3622b2d56fc2901b5577854f38a233e461e3582 -->

Tarav also checks that the minimal structure it requires is in place, for example that `.claude/skills` is a sensible link to `.agents/skills`, both in the Project and in the home folder.
<!-- tarav.breadcrumb 86229f6d7c2163a4915f61af5a559f57f6b0f5bfa84b40c8fb51c574a3a9b2b2 -->

Every Project has its own skill folders, sub-projects included. How those folders are populated or linked to each other is outside these checks.
<!-- tarav.breadcrumb 4c1f6b13b57fa54445ca738b496ae86ff8df5ba2a61b292ea0eec2dcad6a48c2 -->

The checks state that the bootstrap infrastructure is in place in case an agent starts working in this folder. They do not claim what any harness will actually load, in the same way that the agents-file checks do not claim an agent will read the file.
<!-- tarav.breadcrumb 1813111542da74121fd2f98e9930615d1b77164cd531ff2ca5c514a1f4449832 -->

The User asked for this second level to be written as its own implementation request.
<!-- tarav.breadcrumb 80f98d65e665963b2e3484867e49258c0fead1db2c9470b8e72137954547364d -->

### Current behavior (inspected 2026-10-08)

- `TaravSkill` (`src/tarav/l1/skills/skill.py`) is an abstract skill read from its folder: `entrypoint` is `SKILL.md`, and `skill_name` is the frontmatter `name`, falling back to the folder name. A subtype supplies `root`. The only concrete subtype is `SkwSkill` (`l2/skw/skills.py`); there is no plain-folder skill.
- `parse_skill_frontmatter` (`l1/skills/catalog.py`) reads the frontmatter fields from a skill folder.
- `tarav project skills import` (`l2/project/skills/routing.py`, `DEFAULT_SKILLS_DEPOTS`) already links a Project's `.agents/skills` and `.claude/skills` to one shared depot under `~/.tarav/skills/depots/<hash>`.
- Observed layout on this machine: in the Taravangian root, `tarav-py` and `tarav-md`, `.agents/skills` and `.claude/skills` are sibling symlinks into one depot, not one linking to the other. `tarav-py` and `tarav-md` share a depot. In the home folder, `~/.claude/skills` is a symlink to `~/.agents/skills`.
- Installed folder names can carry a prefix. The Chatlas package skill is installed as `chatlas-tarav-chatlas-pkg` while its `SKILL.md` declares `tarav-chatlas-pkg`. The Tarav package skill is installed as `tarav-pkg`.

### Proposed design (agent proposal, not yet User-approved in detail)

**Module.** A new module in `tarav.l1.project`, next to 872's agents module. It imports `tarav.l1.skills` (same layer) and nothing higher.

**Skill object.** `FolderSkill(TaravSkill)`: a concrete skill whose `root` is a given folder. It adds nothing else; identity is the declared `SKILL.md` name that `TaravSkill.skill_name` already provides.

**Namespace member.** `project.agents.skills` returns an object with:

- `search_places`: the Project's `.agents/skills` and the home folder's `.agents/skills`, in that order;
- `available()`: the `FolderSkill`s found directly inside those places;
- `find(name)`: the available skills whose declared name equals `name`;
- `package_skill`: the name read from the marker, or `None`;
- `checks`: its own `CheckProvider` namespace.

The home folder is a constructor argument defaulting to the real one, so tests can supply a temporary folder.

**Configuration.** One value in the `agents` marker entry introduced by 872:

```json
"agents": {
  "package_skill": "tarav-pkg"
}
```

**Checks and POIs.**

| Check | POI type | Codes |
| --- | --- | --- |
| `TaravPackageSkillCheck` | `TaravPackageSkillPOI` | `missing` |
| `ProjectPackageSkillCheck` | `ProjectPackageSkillPOI` | `undeclared`, `missing` |
| `SkillFoldersCheck` | `SkillFoldersPOI` | `agents-skills-absent`, `claude-skills-absent`, `claude-skills-diverges` |

`SkillFoldersCheck` runs once for the Project and once for the home folder, and the POI situation records which. `claude-skills-diverges` means `.claude/skills` does not resolve to the same directory as `.agents/skills`. The rule is worded that way because a literal "is a symlink to `.agents/skills`" would flag the current depot layout, where both are sibling links to one depot.

Each POI's details list the search places that were examined and name `tarav project skills import` as the existing repair path.

**Composition.** `project.agents.skills.checks.suite()` is added to the suite that 872 gives `TaravProject.Checks.suite()`, beside the agents-file checks.

For the Tarav Projects themselves both layers name `tarav-pkg`, so one missing folder produces two POIs. They are two requirements that happen to coincide.

### Informative alternatives

- Identifying a skill by its folder name is simpler but fails for prefixed installs.
- A literal symlink rule for `.claude/skills` matches the home folder here but not the Project folders.
- Modelling the installed skill as a `SkwSkill` would give staleness checks, but a deployed copy carries no `.skw` data, and presence is all this level asks.

### Open questions

1. **Structure rule wording.** Confirm "`.claude/skills` resolves to the same directory as `.agents/skills`". The User answered "Very nice" to the message that proposed it but did not address it directly.
2. **Opt-out.** 872 lets a Project disable each prompt. Should these checks have an equivalent switch, or stay unconditional as the User's "start rigid" suggests?
3. **Machine dependence.** Because the home folder is a search place, the result depends on the machine and is not a property of the repository alone. This was accepted in discussion; it is recorded here so reviewers expect it.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `agents-bootstrap.md`, `projects.md`, `skillware.md`, `batchy-skills.md`, `checks-workflow.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. **Confirm the base.** Check that 872 is implemented and read its final carrier class, marker entry and suite composition. Stop if it is not.
2. **`FolderSkill`.** Add the concrete folder skill and register its Type where the runtime lists skill Types. Test name resolution with frontmatter, without frontmatter, and with a prefixed folder name.
3. **`project.agents.skills`.** Add the object, the two search places with an injectable home folder, `available()`, `find(name)` and `package_skill`. Test with a temporary Project and a fake home folder: skill only in the Project, only in the home folder, in both, in neither, and reached through a symlinked depot.
4. **Checks and POIs.** Add the three checks and POI types. Test every code and the clean case: Tarav skill missing; package skill undeclared; declared but missing; `.agents/skills` absent; `.claude/skills` absent; `.claude/skills` a separate directory; sibling links into one depot (clean); `.claude/skills` linked to `.agents/skills` (clean).
5. **Composition.** Add the skills suite to the Project suite from 872 and update the affected Project tests.
6. **Guidance and closure.** Update `AGENTS.md` through its Skillware source and `ARCHITECTURE.md`. Run the full test suite and Ruff, reinstall the CLI, run `tarav check --project` at the Taravangian root and record the resulting POIs, including the undeclared package skill expected for each Project until it is configured. Inlined Capture on each changed surface, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): `l1/skills/skill.py`, `l1/skills/catalog.py`, `l2/project/skills/routing.py`, `tarav project skills --help`, and the skill folder layout of the Taravangian root, `tarav-py`, `tarav-md` and the home folder.
- At design capture, request 872 was not yet implemented. It was complete before 873 execution began.
- Design note capture: eight User-Turn Breadcrumbs submitted, audit clean; design commit `859083b17779ce0a84d8692d4a95a2ba60f15d25`.
- Wiki capture in `tarav-md`: a Skill availability section appended to `notes/wiki/agents-bootstrap.md` (7 new Breadcrumbs, 25 in the note, audit clean) and a section appended to daily `2026-10-08.md` (2 new Breadcrumbs). Start checkpoint `467b4bb4bc78090f5a769601d61142742cb13f7c`, completion commit `589696b68216d3b2efc72fbe20a38ccf562daa40`.
- The daily note audit still reports the 13 `breadcrumb-position-missing` POIs recorded in request 872's log; this capture appended only and added none.
- Execute (2026-10-08): 872 is implemented. Chose resolved-directory equivalence for the two skill folders and unconditional checks, following the bounded proposal and the User's "start rigid" direction; these are implementation choices, not newly claimed User decisions. Scoped start checkpoint `00253b8ac7e2b006bdac5981fbdd7e80563f2459`.
<!-- tarav.breadcrumb 8080d7f2ab4d495081ad9148881e509377c01f23c2df8b038035234fdfbd325a -->
- Implemented folder-backed Skill identity, `project.agents.skills` discovery, three typed POI families and four checks (the folder check runs at Project and home), plus base Project check composition. Added focused tests, architecture guidance, and regenerated `AGENTS.md` from its Skillware source. Full suite: 183 passed; Ruff: clean; installed CLI refreshed. Root `tarav check --project .` ran 362 checks: all completed, 64 POIs across existing checks; the new skill checks produced three `package_skill` undeclared POIs and no missing Tarav skill or folder-structure POIs. Markers remain unmodified as this request excludes adoption/repair.
- Product Surface Inlined Capture submitted 11 new Breadcrumbs across nine supported Python/Markdown files; the authoritative Skillware JSON source has no native inline convention. The old `tests/test_project_agents.py` Breadcrumb position changed when its helper was narrowed and now audits with a position POI; new capture there resolves. Shared worktree contains a separate uncommitted Skills Workflow refactor supplying `TaravSkill`, so scoped product closure must preserve that prerequisite without absorbing unrelated edits.
- Product completion commit `2ea7d0bebf3ee3bb52787d09c9c32fb863c6209e` includes the bounded bootstrap and minimal `TaravSkill` prerequisite. Its commit Breadcrumb audit is clean. The committed tree passed 173 tests and Ruff in an isolated checkout; the full shared worktree passed 183 tests and Ruff. The installed CLI was reinstalled and the root Project check produced the expected new skill findings. Unrelated shared-worktree edits remain outside the commit.
- Wiki capture in `tarav-md`: start checkpoint `fd6efbe0a020ebffc268a6809d974a49c870bdd1`; daily and topical notes updated with User-Turn-linked Breadcrumbs. Topical audit is clean; daily retains its 13 pre-existing position POIs, with the new Breadcrumb valid. Scoped completion commit `7725b64165469bc4b6df5ced3c0cf3fe08d774ac`.
<!-- tarav.breadcrumb 4cf9620c3925df4f83a5e85d66153d00182624be783abf2219a4fc47042283aa -->
