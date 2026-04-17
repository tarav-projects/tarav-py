# agentos

Core library for agentic workflow primitives, with a companion CLI.

Current baseline includes:
- project context commands: `init`, `rev-parse`, and scope-aware `doctor`
- `tara-tapes` for Tara spec-first tape operations
- `tape` and `git-refs` (from `obacli`)
- `mdblocks`, `prefix`, `skills`, `utils`, `doctor`, `test`

`agentos` is the core Python package/library.
`agentos` is the CLI entrypoint/layer.

## Utils CLI

`agentos utils` exposes small agent-facing helpers:

- `uuid`: generate one or more UUIDv4 values (`--count`, `--json`)
- `tmp-folder new`: allocate a unique path under `<project>/.agentos/tmp/` (`--create` optional)

## Skills CLI

`agentos skills` exposes the public routed skills surface.

Current public surface:

- `list`: return the routed skill catalog visible to the caller context (`--json` optional)
- `import`: materialize the routed skill catalog into the resolved local skill depot
- `path --depot`: print the routed local skills depot path for the current caller context
- `path <name>`: resolve one routed skill name to its loadable path
- `--project [path]`: optional caller project root override for routing on all commands; when passed without a value, use current `pwd`

Current routing model:

- local context resolves from `--project`, then nearest local `.agents/` directory, then agentos project root
- `~/.agents` is not used as the public routed skills surface for this flow
- profile selection uses local project config override first, then global `default_profile`, then hardcoded `default`
- imports are declared once in `imports_registry`
- packages group reusable ordered import sets
- profiles choose packages, optional inline imports, and a local `skill_depot`
- when no local context exists, public commands return an empty routed catalog or a local-context error
- `list` and `path` are config-derived and do not materialize symlinks
- `import` is the only public command that syncs the local routed depot

Global config shape:

```json
{
  "class": "agentos.global.config",
  "schema_version": 1,
  "skills": {
    "routing": {
      "imports_registry": {
        "agentos": {
          "path": "/Users/pereiro/projects/agentos/skills"
        }
      },
      "packages": {
        "core": {
          "imports": [
            { "name": "agentos" }
          ]
        }
      },
      "default_profile": "default",
      "profiles": {
        "default": {
          "skill_depot": ".agents/skills",
          "packages": [
            { "name": "core" }
          ],
          "imports": [
            { "name": "scratch", "path": "skills" }
          ]
        }
      }
    }
  }
}
```

Output notes:

- `list` includes at least `name`, `description`, `source`, and routed absolute `path`
- `path --depot` prints the routed local depot absolute path
- `path <name>` prints the routed absolute path only
- those routed paths are predictive until `import` syncs the depot
- when the selected profile exposes no skills, `list` returns an authoritative empty result
- package references are objects
- profile import entries are always objects
- `{ "profile": "research" }` can be set in local `.agentos/config.json` under `skills.routing`
- `{ "name": "agentos" }` resolves through `imports_registry`
- `{ "name": "scratch", "path": "skills" }` is an inline import definition

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
uv run agentos tape init --tape bla
uv run agentos tape init --tape bla --tape-class events.demo --data-schema-json '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["k"],"properties":{"k":{"type":"string"}},"additionalProperties":false}'
uv run agentos tape init --tape bla --allowed-classes-json '["event.alpha","event.beta"]'
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha --data-json '{"k":"v"}'
uv run agentos tape append --tape bla --writer-id proc-a --class event.alpha --override-created-at 2026-03-01T10:11:12Z
uv run agentos tape consolidate --tape bla
uv run agentos tape query --tape bla --mode best_effort --count
uv run agentos tape query --tape bla --mode committed --count --consolidate
uv run agentos tape query --tape bla --mode best_effort --jmes "[?data.task_id=='task-123']"
uv run agentos tape config --tape bla
uv run agentos tape doctor --tape bla

# headless explicit root
uv run agentos tape append --root /tmp/my-tape --writer-id proc-a --class event.alpha --init
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
