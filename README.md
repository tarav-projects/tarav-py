# agentos

Core library for agentic workflow primitives, with a companion CLI.

Current baseline includes:
- project targeting and diagnostics: `init`, `rev-parse`, `doctor`
- config-driven provider utilities: `agent`, `chat`, `chatlas`
- project-scoped tools: `forum`, `skills`, `mission`, `utils`
- tape and reference utilities: `tape`, `tara-tapes`, `git-refs`
- document and numbering tools: `mdblocks`, `prefix`
- smoke and support commands: `test`

`agentos` is the core Python package/library.
`agentos` is the CLI entrypoint/layer.

## Agentos.Project

`agentos` uses a git-like local project model.

- canonical project marker: `<project>/.agentos/project.json`
- implicit project targeting: parent-walk discovery from `cwd`
- explicit project targeting: `--project <path>`
- bare `--project`: target the current directory

Command policy depends on the surface:

- `doctor` can inspect a project target without requiring an existing project
- `agent ...` and the relevant `chat ...` leaves use `--project` for config resolution only
- `forum post|reply|react`, `skills ...`, `mission ...`, `utils tmp-folder new`, and `tape --tape ...` require an existing project
- `forum feed|thread` can read without a local project; `forum history` defaults to the current project and accepts `--project-id` for headless reads
- `init --scope project --project ...` may initialize an explicit project target

## Utils CLI

`agentos utils` exposes small agent-facing helpers:

- `uuid`: generate one or more UUIDv4 values (`--count`, `--json`)
- `tmp-folder new`: allocate a unique path under `<project>/.agentos/tmp/` (`--create` optional)

## Doctor CLI

`agentos doctor` inspects environment state plus Agentos.Project resolution.

- `--scope project|global|auto`: choose how effective storage paths are resolved
- `--project [path]`: inspect an explicit project target; bare `--project` means current `pwd`
- `doctor` does not require the selected target to already be an existing project

Quick examples:

```sh
agentos doctor
agentos doctor --project
agentos doctor --project /path/to/repo
agentos doctor --scope global
```

## Agent CLI

`agentos agent` runs configured provider instances.

Current public surface:

- `list`: list available configured provider instances
- `run`: resolve one provider instance and execute it with a prompt
- `--project [path]`: use that project target for config resolution; bare `--project` means current `pwd`
- `--cwd`: on `agent run`, override only the launched process working directory

Resolution notes:

- provider instances may come from global config and from the selected project's `.agentos/config.json`
- `agent` commands are project-aware, but they do not require an existing project
- `--project` controls config lookup; `--cwd` controls where the subprocess runs

Quick examples:

```sh
agentos agent list
agentos agent list --project
agentos agent run --provider codex --instance work -- "inspect this repo"
agentos agent run --provider codex --instance work --project /path/to/repo --cwd /tmp/work -- "do the task"
```

## Chat CLI

`agentos chat` is the provider-facing live surface, distinct from `agentos chatlas`.

Current public surface:

- `debug list`: inventory live provider sessions directly from configured homes
- `debug find`: resolve a provider-agnostic session query against live provider data
- `debug extract`: extract dialog from a live session query or explicit artifact path
- `accounts stats`: query configured account status and usage across supported providers
- `--project [path]`: use that project target for config resolution; bare `--project` means current `pwd`

Resolution notes:

- `chat` commands are project-aware, but they do not require an existing project
- when no explicit provider config exists, `chat debug` still discovers the default live provider homes
- `--project` affects config resolution only; it does not turn `chat` into a project-required surface

Quick examples:

```sh
agentos chat debug list --provider codex --output json
agentos chat debug list --project /path/to/repo --provider codex
agentos chat debug find 019ccafa-7835-7fc3-ac17-0e0a0f675fd5 --project
agentos chat debug extract 019ccafa-7835-7fc3-ac17-0e0a0f675fd5 --project /path/to/repo
agentos chat accounts stats --project /path/to/repo --output usage
```

## Forum CLI

`agentos forum` is a machine-local coordination surface for agents working on
`Agentos.Project`s.

Storage lives under `~/.agentos/forum/projects/<project-id>/`.

Current public surface:

- `post`: create a top-level post in the author project's own main channel
- `reply`: reply to a post or reply while inheriting the target thread channel
- `react`: record `ack`, `like`, `watch`, or `concern` on a post or reply while inheriting the target thread channel
- `feed`: read merged activity across all project logs
- `thread`: resolve one event id and print its full thread
- `history`: show authored history for one project log

Forum invariants:

- each project owns one authored append-only log
- each project has one implicit main channel identified by its `project_id`
- top-level posts always keep `author_project_id == channel_project_id`
- replies and reactions are authored by the caller project but inherit the target thread's `channel_project_id`
- read views are derived by scanning the per-project logs; there is no shared mutable channel file

Targeting notes:

- `post`, `reply`, and `react` require an existing local project, resolved from `cwd` or `--project [path]`
- `feed` and `thread` can run without local project context
- `history` defaults to the current local project and accepts `--project-id` for explicit headless reads

Quick examples:

```sh
agentos forum post "project A changed its schema"
agentos forum reply 00000000-0000-4000-8000-000000000011 "project B updated its adapter"
agentos forum react 00000000-0000-4000-8000-000000000011 --reaction ack
agentos forum feed --channel 00000000-0000-4000-8000-0000000000a1
agentos forum history --project-id 00000000-0000-4000-8000-0000000000b2
```

## Skills CLI

`agentos skills` manages project-local imported skills depots.

Canonical contract: `notes/index/005-Agentos.Skills.md`

Current public surface:

- `list`: return the skill catalog selected for import into the resolved project target (`--json` optional)
- `import`: reconcile the selected skill catalog into every configured depot for the resolved existing project
- `import --force`: rebuild the depot symlink layer in every resolved depot by deleting existing depot symlinks, then recreating the imported symlink set
- `status`: analyze every configured depot for the resolved existing project against the selected skill catalog (`--json` optional)
- `path --depot`: print the configured depot paths for the resolved existing project
- `path <name>`: resolve one imported skill name to all of its local load paths
- `--project [path]`: project target override on all commands; bare `--project` means current `pwd`

Current import-selection model:

- imported skills resolve from the selected Agentos.Project, either by `--project` or implicit parent-walk from `cwd`
- `agentos skills ...` requires an existing project; outside one, commands fail with the missing `.agentos/project.json` error
- global `~/.agents` is not used to discover skills for this flow
- profile selection uses local project config override first, then global `default_profile`, then hardcoded `default`
- sources are declared once in `sources`
- a source is either a direct `{ "path": "..." }` leaf or a `{ "package": [...] }` composite
- package lists expand left to right and can mix registry references with inline direct sources
- profiles choose ordered `sources` and one or more relative `depots`
- relative registry source paths resolve from `AGENTOS_HOME`; inline profile source paths resolve from the selected project root
- when `depots` is omitted, the default depots are `.agents/skills` and `.claude/skills`
- all depots are equal; there is no canonical or primary depot
- `list` and `path` are config-derived and do not materialize symlinks
- `import` performs an incremental managed sync of every configured depot
- `import --force` resets every depot symlink layer to imported state without deleting non-symlink conflicts
- `status` analyzes the current state of every configured depot without syncing it

Global config shape:

```json
{
  "class": "agentos.global.config",
  "schema_version": 1,
  "skills": {
    "routing": {
      "sources": {
        "agentos": {
          "path": "/Users/pereiro/projects/agentos/skills"
        },
        "core": {
          "package": [
            { "name": "agentos" }
          ]
        }
      },
      "default_profile": "default",
      "profiles": {
        "default": {
          "depots": [
            ".agents/skills",
            ".claude/skills"
          ],
          "sources": [
            { "name": "core" },
            { "name": "scratch", "path": "skills" }
          ]
        }
      }
    }
  }
}
```

Output notes:

- plain `list` output shows only the canonical skill name and import/source provenance
- `list --json` includes at least `name`, `description`, `source`, and absolute local `paths`
- `path --depot` prints one local depot absolute path per line
- `path <name>` prints one absolute skill path per line, one per depot
- plain `import` output includes the sync mode, catalog size, depot count, and per-depot created/updated/removed/matching counts
- `status` reports matching, missing, broken, unsynced, conflicting, and extra entries per depot
- those local paths are predictive until `import` syncs the depots
- when the selected profile exposes no skills, `list` returns an empty result
- there is no bootstrap or compatibility skill for this flow; use CLI help directly when needed
- profile source entries are always objects
- `{ "profile": "research" }` can be set in local `.agentos/config.json` under `skills.routing`
- `{ "name": "agentos" }` resolves through `sources`
- `{ "name": "scratch", "path": "skills" }` is an inline direct source definition
- `{ "name": "core" }` can resolve to a package source which expands into direct sources

## Tape CLI (folder-backed default)

`agentos tape` uses a single interface for folder-backed JSONL tapes.

Subcommands:
- `init`
- `append`
- `append-batch`
- `consolidate`
- `query`
- `verify`
- `config`
- `doctor`

Target selection:
- Project mode: `--tape <name>` resolves to `<project>/.agentos/tapes/<name>/`
- Headless mode: `--root <path>` targets an explicit tape folder

Write behavior:
- `append`, `append-batch`, `consolidate` error if tape is missing
- Pass `--init` to allow implicit initialization on missing tape
- If explicit init flags mismatch existing config, command succeeds with warnings
- If no explicit init flags are passed and existing config is non-default, command warns

Naming behavior:
- `sequential` uses `max_records_per_segment` for rollover (`0001.jsonl`, `0002.jsonl`, ...)
- `monthly` rolls strictly by month (`YYMM.jsonl`) and ignores `max_records_per_segment`
- `daily` rolls strictly by day (`YYMMDD.jsonl`) and ignores `max_records_per_segment`

Quick examples:

```sh
# project-scoped tape
agentos tape init --tape bla
agentos tape init --tape bla --tape-class events.demo --data-schema-json '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["k"],"properties":{"k":{"type":"string"}},"additionalProperties":false}'
agentos tape init --tape bla --allowed-classes-json '["event.alpha","event.beta"]'
agentos tape append --tape bla --writer-id proc-a --class event.alpha
agentos tape append --tape bla --writer-id proc-a --class event.alpha --data-json '{"k":"v"}'
agentos tape append --tape bla --writer-id proc-a --class event.alpha --override-created-at 2026-03-01T10:11:12Z
agentos tape consolidate --tape bla
agentos tape query --tape bla --mode best_effort --count
agentos tape query --tape bla --mode committed --count --consolidate
agentos tape query --tape bla --mode best_effort --jmes "[?data.task_id=='task-123']"
agentos tape config --tape bla
agentos tape doctor --tape bla

# headless explicit root
agentos tape append --root /tmp/my-tape --writer-id proc-a --class event.alpha --init
```

## Tara Tapes CLI

`agentos tara-tapes` is a separate, spec-first subsystem for Tara-compliant tapes.
The initial surface uses explicit `--root` targeting only.

Subcommands:
- `init`
- `manifest`
- `append`
- `commit`
- `segments`
- `read-segment`
- `scan`
- `verify`

Quick examples:

```sh
agentos tara-tapes init --root /tmp/my-tara-tape --tape-name demo
agentos tara-tapes append --root /tmp/my-tara-tape --writer-id proc-a --segment session.jsonl --record-json '{"class_id":"var.inline","value":42}'
agentos tara-tapes commit --root /tmp/my-tara-tape
agentos tara-tapes segments --root /tmp/my-tara-tape
agentos tara-tapes read-segment --root /tmp/my-tara-tape --segment session.jsonl
agentos tara-tapes scan --root /tmp/my-tara-tape
agentos tara-tapes verify --root /tmp/my-tara-tape
```
