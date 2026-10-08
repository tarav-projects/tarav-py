# 875 — Run script registry — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: complete. Phase: Execute.

Give `tarav run` a simple central registry of the Python code it runs, so that agents can study how Tarav has recently been used, in their own project and in others. Each run retains the code that ran (a copy of the script file, the inline `-c` source, or the source read from standard input) together with a small metadata record. Entries are partitioned by Project when `--project` is used and go to a global partition otherwise. Retention is bounded by size, not by time. The registry is best effort: it must never change the outcome of a run.

Non-goals:

- A query command, a lookup by name, quality marks, or operation labels. These were brainstormed and remain undecided; agents browse the registry folder with their own tools in this first version.
- Any connection to code help or Context. That is a possible later consumer.
- Recording which Tarav modules a script imported.
- Space efficiency beyond trivial deduplication.
- The import guard and `tarav_bypass` entry, which are request 874. This request does not depend on 874, but together they make `tarav run` the route most scripts take.

## Design narrative

### Why

The User's pandas analogy: operating a Tarav project should largely mean agents writing scripts against the Tarav library. The primary documentation is then the code base and recent uses of it, because skills go stale. Agents should be able to find examples of how Tarav has been used recently.
<!-- tarav.breadcrumb 19eddffe1131777cc09f16a246655f420ee9b15de78f2f60cb72596b0392e5d7 -->

Live help already implements this principle for the command line interface. The registry here is a separate, similar workflow for scripts: `tarav run` itself owns a store of the code it has been running. It is not the record of how the `run` command was called, which live help already keeps. It can be very simple: a place where the files are copied, kept bounded in size, with metadata such as the project and the commit so that contextualization can find things later.
<!-- tarav.breadcrumb 7423cecf783a58ee0b0a0e681016c781ad6bec51bcf3249acbad44a9f4bf5b4e -->

The store is central, so that an agent can see how other projects use the same things. Scripts from other projects may contain better patterns, and agents can be prompted to study them, which lets practice improve over time.
<!-- tarav.breadcrumb 6fc1d94b25c60fca50c065dbee32a92633f4587f1f0361b007822b47806d26f8 -->

### Decisions by the User

The registry is another registry like the help one, in its own folder. `tarav run` keeps the path, and copies the file into the registry when a script path is given; source given as text or on standard input is kept as well. It should be very simple; some deduplication is fine, and space efficiency does not matter at first. It is partitioned at least by Project: a run with the `--project` flag is stored under that Project's partition, and a plain run goes to a global partition. Metadata is left to common sense, for example the calling folder and the date; what is useful will be discovered later.
<!-- tarav.breadcrumb 6c5c9a86a99c0b8e7e5e442015b816a01d835a7584963557ece3604966a2a578 -->

Retention exists only to bound size, so size is the rule: an allocation per partition, for example 50 MB, and a limit per entry, for example 1 or 2 MB, beyond which the copy is simply cut. This is a best-effort system that only increases contextualization power; nothing in it is critical. The User accepted the agent's other proposed choices and asked for common sense on the rest.
<!-- tarav.breadcrumb 22398abdca267af863438dc73c6273f30034ff0b256325ab8ac22837f3c2cdaf -->

### Current behavior (inspected 2026-10-08)

- `tarav run` is `src/tarav/l3/run.py`. `_run()` picks a configurator (`CurrentRunnerConfigurator`, or `ProjectRunnerConfigurator.from_path()` with `--project`) and calls `run_python()`.
- `run_python()` in `src/tarav/l1/python_env/core.py` is a plain `subprocess.run([interpreter, *arguments], cwd=configuration.cwd)` that returns the exit code. Standard input passes straight through to the child, so `tarav run -- -` works with heredocs.
- `_describe_run()` already classifies a call as `code` (`-c`), `module` (`-m`), `stdin` (`-`) or `script`, for the live-help usage trace. That trace keeps a short descriptor, not the code.
- The Usage Registry (`src/tarav/l1/usage/__init__.py`) is the nearest precedent. It stores JSONL rows in an Archive partition owned by its workflow under the durable data root (`default_tarav_data_root() / "archive"`), writes under a file lock, trims by a day window after each write, and never lets a failure affect the caller.
- A Project's stable identity is the `project_id` in its marker; `ProjectLaunchConfiguration` resolves the Project root for `--project`.

### Proposed design (agent proposal under the User's "use common sense")

**Ownership and place.** A small `RunRegistry` in `tarav.l1.python_env`, next to `run_python()`, with its own partition following the Usage Registry pattern. `tarav run` (`l3/run.py`) is its only writer. See open question 1 for the exact root.

**Layout.** One folder per partition, one folder per entry:

```text
<registry>/
├── global/
└── <project_id>/
    └── <UTC timestamp>-<short content hash>/
        ├── entry.json
        └── source.py
```

The partition key is the Project's stable id, with the Project name and root kept in the metadata, because folder names can collide or move.

**What is kept per mode.**

| Mode | Retained source |
| --- | --- |
| script path | a copy of the file, plus its original absolute path |
| `-c` code | the code text |
| `-` (standard input) | the text; `tarav run` reads standard input fully, stores it, and feeds the same bytes to the child |
| `-m module` | no source; the module name only |

Only the entry script is copied, not modules it imports.

**Metadata (`entry.json`).** Start and end time, mode, original script path or module name, number of script arguments and the arguments themselves, calling folder, working directory used, interpreter, Project id, name and root when present, Git commit and dirty flag of the calling folder's repository when there is one, Tarav version, content hash, original size, whether the copy was truncated, and exit status.

**Write order.** The entry is written before the child starts, with no exit status, and completed afterwards. A run that crashes, hangs or is interrupted is therefore still recorded.

**Limits.** A per-entry limit (default 1 MB): a larger source is cut at the limit and marked `truncated` with its original size. A per-partition allocation (default 50 MB): when a write takes the partition over it, the oldest entries are removed until it fits. Pruning happens during the write, so no background job is needed. Both defaults are constants in code; configuration is not part of this slice.

**Deduplication.** Trivial only: when the newest entry in the partition has the same content hash, the new entry records the hash and metadata and omits the duplicate source file.

**Best effort.** Every registry step is wrapped as in the Usage Registry: a failure is logged and the run proceeds unchanged. The one exception to "unchanged" is standard-input mode, where reading and replaying the input is part of running; if capture fails there, the input already read is still passed to the child.

**Discovery.** `tarav run --help` prints the registry path, and the existing usage trace for `run` gains the entry id, linking live help to the stored code.

### Informative alternatives

- A time window, as the Usage Registry uses, was replaced by the User with a size rule: time alone would empty the registry after a quiet period.
- A store inside each Project folder was the first idea; the User agreed on a central store so that projects can learn from each other.

### Things to be aware of

- Scripts sometimes contain tokens or passwords, and this keeps copies of them. On a single machine with bounded retention this is accepted.
- Until 874 lands, scripts run without `tarav run` are simply not recorded.

### Open questions

1. **Root of the registry.** The discussion said "under `~/.tarav/`", and `tarav-pkg` places machine-local operational logs there. The existing help registry, which the User names as the model, lives instead in an Archive partition under the durable data root (`~/Documents/tarav/archive/`). The agent recommends `~/.tarav/` for this registry, because it is pruned by size and is not User.Touched.Data; confirm, or choose to follow the help registry's place.
2. **Standard input.** Confirm that `tarav run` may read standard input fully before starting the child. This changes nothing for heredocs and pipes, but an interactive session typed into `tarav run -- -` would only start after end of input.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `tarav-scripts-and-entry-points.md`, `live-help.md`, `tarav-harness.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. **Registry core.** Add `RunRegistry` with entry creation, completion, the per-entry cut, per-partition pruning and trivial deduplication, taking its root as a parameter. Test with a temporary root: each mode's retained content, truncation marking, pruning oldest-first at the allocation, deduplication, and that an unwritable root raises nothing.
2. **Wire `tarav run`.** Create the entry before `run_python()`, complete it with the exit status after, select the partition from `--project`, and handle standard-input capture and replay. Test through the command: script, `-c`, `-m`, standard input with a heredoc, a failing script, and a run with the registry disabled by an unwritable root still returning the script's own exit code.
3. **Metadata.** Add Project identity, Git commit and dirty flag, and Tarav version, each tolerant of absence (no Project, no repository).
4. **Discovery.** Print the registry path in `tarav run --help` and add the entry id to the `run` usage descriptor. Update `test_usage_live_help.py` expectations if the descriptor shape changes.
5. **Guidance and closure.** Document the registry in `ARCHITECTURE.md` and `AGENTS.md`. Run the full suite and Ruff, reinstall the CLI, run one real script through `tarav run --project` and inspect its entry. Inlined Capture on each changed surface, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): `l3/run.py`, `l1/python_env/core.py` and `runner.py`, `l2/project/runner.py`, `l1/usage/__init__.py`. The `tarav-py` worktree has unrelated uncommitted edits and other agents executing requests 872 and 873; Execute must checkpoint only its declared scope.
- The User did not answer the partition-key and reading-side questions directly, but accepted the agent's choices and asked for common sense. Project id as partition key and folder browsing as the first reading side are therefore recorded as agent choices, not explicit User decisions.
- Design note capture: five User-Turn Breadcrumbs submitted, audit clean; design commit `cf8adf1b99515ddda0985e53f7f832aceb689d9c`.
- Wiki capture in `tarav-md`: two sections appended to `notes/wiki/tarav-scripts-and-entry-points.md` (4 new Breadcrumbs, 23 total, audit clean) and one to daily `2026-10-08.md` (3 new, 27 total; only the 13 earlier `breadcrumb-position-missing` POIs). Start checkpoint `f32bd1a7e28099afaeca1271f7482d7716296118`, completion commit `edbe4ec63649ad95a3344f37f218d6850ff9d759`.
- Execute (2026-10-08): the User asked to start implementing while the two open questions were unanswered. Both were resolved with the agent's recorded recommendations, which remain agent choices: the registry lives under `~/.tarav/run-registry/`, and `tarav run -- -` reads standard input fully before starting the child. Scoped start checkpoint `475639557aa3884ffc3b88658faa0e336a8824b2`.
<!-- tarav.breadcrumb 32ca8c35fe3770635738d3b7910c68b19071361192dc321a56d472e0e41011ea -->
- Implemented `RunRegistry` in `src/tarav/l1/python_env/registry.py`, wired `tarav run` in `src/tarav/l3/run.py`, added optional standard-input replay to `run_python()`, and added `TARAV_RUN_REGISTRY` so the test suite and the commands it spawns stay out of the machine registry. Repeated code is shared by hard link, so pruning the older entry cannot orphan the newer one. The `run` usage trace carries `registry_entry`, and `tarav run --help` prints the registry path.
- Two deviations from the design, both forced by an uncommitted refactor in the shared worktree that moves `tarav.l0._core.project` to `tarav.l0.project` and `tarav.l0._core.home`: the registry resolves the Tarav home itself, and `tarav run` reads the Project marker file directly to get the Project id. Each imports cleanly in both the committed tree and the worktree.
- Verification: ten new tests in `tests/cli/test_run_registry.py`. The exact committed tree passed 188 tests in an isolated checkout; the shared worktree passed 198; Ruff clean. CLI reinstalled. A real `tarav run --project -- <script>` produced an entry under the `tarav-py` Project id with source, Git commit, dirty flag and exit status, and a heredoc through `tarav run -- -` ran and was retained under `global`.
- Product completion commit `c67033b` contains only this request's changes; the unrelated edits in `ARCHITECTURE.md` and `pyproject.toml` and the three staged renames were left as they were. It was built from a temporary index, so no commit-message Breadcrumb evidence was registered. Inlined Capture: seven Breadcrumbs across `registry.py`, `run.py`, `test_run_registry.py` and `ARCHITECTURE.md`. `run.py` now reports three `breadcrumb-position-missing` POIs for its older labels, because new imports shifted them; there is no re-observe command.
- Found while checking earlier requests: `tests/cli/test_check.py` has two tests asserting that the base Project declares no checks. They are outside pytest `testpaths`, were made obsolete by request 872, and fail when run directly. Not changed here.
