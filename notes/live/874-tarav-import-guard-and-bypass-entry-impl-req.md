# 874 — Tarav import guard and bypass entry — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: complete. Phase: Execute.

Split the way into the Tarav library into two entry points over one code base. `import tarav` becomes a guarded entry: in a process that was not started through Tarav it fails with an error that tells the reader to run the script with `tarav run`. A second top-level package, `tarav_bypass`, is the explicit way through for deliberate users. This request adopts `tarav_bypass` in Tarav's own console commands, test suite, and direct-import maintenance scripts. Other repositories remain outside its scope by the User's later decision.

Non-goals, all of them brainstormed in the same session and not decided:

- A registry of the scripts that `tarav run` executes, and any lookup of source or recent uses by name.
- Quality marks on retained scripts, and labels that tie a run to an operation or skill module.
- Other ways through the guard: a Python `-X` option, a script argument flag, a marker file.
- Any change to what `tarav run` records today.

## Design narrative

### Why

The User describes a pandas analogy. Asked for a plot, an agent writes a script that imports pandas and lets the library manipulate the data; it does not read the files with its own tools, and a wrong use produces an error that points to the right one. Operating a Tarav project should largely work the same way: agents write scripts against the Tarav library. The primary documentation is then the code base itself and recent uses of it, with skills in a secondary place because they go stale.
<!-- tarav.breadcrumb 6d25eeb178b5 -->

`tarav run` is the intended way to run such scripts. Tarav should complain when it is imported in a process that `tarav run` did not start, using a flag in the environment that `tarav run` populates, and the testing infrastructure should be able to override it. The purpose is only to push agents toward `tarav run`.
<!-- tarav.breadcrumb 6636ce230788 -->

### Decisions by the User

The complaint is an error, not a warning, but one that can be controlled: whatever needs to import Tarav outside this route must be able to do so. The Constitution's preference for informing over forbidding is a general principle and not an invariant; a strong rule is acceptable here. If the hard version proves too complicated it can be downgraded to a warning later.
<!-- tarav.breadcrumb bf03f3fc608b -->

The mechanics use an environment variable, but the error message does not mention it. The message only says that the process was started the wrong way.
<!-- tarav.breadcrumb 53b4c0ea2122 -->

The guard is a speed bump for agents that casually import Tarav. A developer who uses Tarav directly must be able to pass it as easily and ergonomically as possible.
<!-- tarav.breadcrumb 98cb4207ac05 -->

There should be different ways to pass, and one of them is a second entry point to the same library: an import layer with the rest of the system below it.
<!-- tarav.breadcrumb 67caf3a3530e -->

Only the different entry points are to be done now. Plain `tarav` is what regular agents use and is where the speed bump sits.
<!-- tarav.breadcrumb 235551827d7a -->

The name of the second entry should read like a warning, in the spirit of flags that say the user is leaving the sandbox.
<!-- tarav.breadcrumb b920aae58128 -->

The name is `tarav_bypass`, settled "for a while". This request covers the split of the entry point and its adoption in every application that requires it, such as the command line interface itself and the test engines.
<!-- tarav.breadcrumb 1be44394d281 -->

### Current behavior (inspected 2026-10-08)

- `src/tarav/__init__.py` holds only `__version__`. The version in `pyproject.toml` is a static string, so building the wheel does not import the package.
- After the Iterante removal (`a7e5f16`) there are two console scripts: `tarav = "tarav.l3.cli:main"` and `tarav-daemon = "tarav.l3.daemon.entrypoint:main"`. Both start inside the `tarav` package, so `tarav/__init__.py` runs before any of their code. The wheel is built from `packages = ["src/tarav"]`.
- `tarav run` ends in `run_python()` (`src/tarav/l1/python_env/core.py`), a `subprocess.run` without an `env` argument. The child inherits the parent's environment.
- Other places that start a Python process which imports Tarav:
  - `ChildProjectCheck` (`src/tarav/l2/project/root.py`) passes a copy of `os.environ` with `VIRTUAL_ENV` removed;
  - `TestSuiteCheck` (`src/tarav/l2/project/dev.py`) runs `sys.executable -m pytest` with the inherited environment;
  - the Project harness launch, `python -m tarav.l3.project.launch` (`src/tarav/l3/project/launch.py`), which imports the `tarav` root first because of `-m tarav...`;
  - `tarav daemon`, which starts the `tarav-daemon` executable with `subprocess.Popen` (`src/tarav/l3/daemon/commands.py`), and launchd, whose job has `ProgramArguments` of that executable only (`src/tarav/l3/daemon/launchd.py`). A launchd job does not inherit a shell environment.
- There is no `tests/conftest.py`. Pytest `testpaths` are listed in `pyproject.toml`. Tests run with `uv run pytest` and through `TestSuiteCheck`.
- Importers of `tarav` outside `tarav-py/src` found on this machine:
  - `tarav-py/tests` (most test files), `tarav-py/tooling` (5 migration scripts), `tarav-py/scripts` (3 migration scripts), and historical files under `tarav-py/dev/live`;
  - `/Users/pereiro/projects/taravangian-project/tarav-extension-py/src/tarav_extension` (3 files);
  - `/Users/pereiro/projects/md-library-project/md-library-py/src/md_library` (14 files);
  - `/Users/pereiro/projects/pereiros-projects/g70203-project/g70203-py` (13 source files, 3 tests);
  - `/Users/pereiro/projects/telegram-archive-project/telegram-archive-py/src/telegram_archive` (7 files).
- The harness hooks in `~/.claude-jp/settings.json` call the `tarav` command, so they enter through the command line.

### Proposed design (agent proposal, not yet User-approved in detail)

**The mark.** A process is "started through Tarav" when one internal environment variable is present. Its name is an implementation detail kept out of every user-facing message. Its value names the door that set it (`cli`, `daemon`, `pytest`, `bypass`); the guard only tests presence.

**`tarav_bypass`.** A new top-level package `src/tarav_bypass/`, added to the wheel's `packages`. Importing it sets the mark if absent and imports nothing from `tarav`. A deliberate user writes `import tarav_bypass` before the first Tarav import. It also holds the two console entry functions: each sets the mark and then imports and calls the real `main`. The console scripts in `pyproject.toml` point at these functions.

**The guard.** In `src/tarav/__init__.py`: if the mark is absent, raise a subclass of `ImportError`. The message says that Tarav was imported from a process that was not started through Tarav, tells the reader to run the script with `tarav run -- <script>` or `tarav run --project -- <script>`, and gives the reason: the script then runs in the Project's environment, which is the intended path. It does not name the variable or `tarav_bypass`. The way through is documented in a comment beside the guard, in `ARCHITECTURE.md` and `AGENTS.md`, and in the Tarav package skill.

**Inheritance.** `tarav run` needs no code of its own: the `tarav` command sets the mark, the Python child inherits it, and so does anything the script starts. The same holds for `ChildProjectCheck`, `TestSuiteCheck` and the harness launch when their parent is marked. The daemon is the exception, because launchd does not pass a shell environment; its own console door covers it.

**Tests.** A new `tests/conftest.py` imports `tarav_bypass`. Guard behavior is tested in subprocesses whose environment has the mark removed:

- plain `import tarav` fails, and the message contains `tarav run` and neither the variable name nor `tarav_bypass`;
- `import tarav_bypass` followed by `import tarav` succeeds;
- a script run through `tarav run` imports Tarav successfully;
- `python -m tarav.l3.project.launch` works when started by a marked parent.

An architecture test asserts that nothing in `tarav` imports `tarav_bypass`, and that `tarav_bypass` imports nothing from `tarav` at module import.

**Landing order.** The guard is switched on last so nothing breaks midway: first add `tarav_bypass`, the console doors and `conftest.py`; then adopt `import tarav_bypass` in every importer that needs it; then enable the guard, reinstall the command, and confirm that the daemon still starts, including one started by launchd.

**Other repositories.** Out of scope by User decision (2026-10-08): the four importing repositories listed above are not adopted by this request. Once the guard is on they will meet the error, and their maintainers resolve it there. This request changes `tarav-py` only.

**Known limitation.** The mark travels through the environment, so any process started from a marked process passes, and an agent that reads the source can set the mark itself. This is accepted: the guard is a speed bump, not a security boundary.

### Informative alternatives

- A warning instead of an error was proposed by the agent and rejected by the User.
- Letting the guard accept processes whose command name is `tarav` or `tarav-daemon` avoids the console doors but is a looser rule.
- `tarav_direct`, `tarav_raw`, `tarav_dev` and other names were considered before `tarav_bypass`.
- A submodule such as `tarav.bypass` cannot work, because importing it runs `tarav/__init__.py` first.

### Open questions

1. **Other repositories.** Resolved: not this request's concern; see the design section above.
2. **The mark's value.** Resolved for this implementation: the value names the door (`cli`, `daemon`, or `bypass`); the guard tests presence only.
3. **Maintenance scripts.** Resolved for this implementation: direct-import migration scripts in `tooling/` and `scripts/` import `tarav_bypass`; historical `dev/live` files are left alone.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `tarav-scripts-and-entry-points.md`, `live-help.md`, `projects.md`, `tarav-harness.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. **Bypass package and doors.** Add `src/tarav_bypass/` with the mark and the two console entry functions; add it to the wheel; point the console scripts at it. The guard is not yet active. Verify that the built wheel contains both packages and that `tarav --version` and `tarav-daemon` start after a reinstall.
2. **Test configuration.** Add `tests/conftest.py` importing `tarav_bypass`. Run the full suite.
3. **Adoption inside `tarav-py`.** Resolve open question 3, then update `tooling/` and `scripts/` accordingly. Leave `dev/live` historical files alone.
4. **Adoption inside `tarav-py` only.** Add the import where `tarav-py` itself needs it (tests, and the maintenance scripts according to open question 3). No other repository is edited.
5. **Enable the guard.** Add the check and its error to `src/tarav/__init__.py`, the subprocess tests and the architecture test. Run the full suite and Ruff.
6. **End-to-end verification.** Reinstall the command; run a script with `tarav run` and with `tarav run --project`; run `tarav check --project` at the Taravangian root, which exercises `ChildProjectCheck`, `TestSuiteCheck` and the harness launch; restart the daemon through `tarav daemon` and through launchd; confirm the harness hooks still work.
7. **Guidance and closure.** Document the two entry points in `ARCHITECTURE.md` and `AGENTS.md`; note the companion change needed in the Tarav package skill in `tarav-md`. Inlined Capture on each changed surface, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): `src/tarav/__init__.py`, `pyproject.toml`, `l3/run.py`, `l1/python_env/core.py`, `l2/project/root.py`, `l2/project/dev.py`, `l3/project/launch.py`, `l3/daemon/commands.py`, `l3/daemon/launchd.py`, and a search for `import tarav` / `from tarav` across `/Users/pereiro/projects`. The `tarav-py` worktree has unrelated uncommitted edits, including `pyproject.toml`, and other agents are working there; Execute must preserve them and checkpoint only its declared scope.
- Not verified in Design: whether any process outside `/Users/pereiro/projects` imports Tarav, and how the launchd job behaves once the daemon door exists. Both are covered by step 6.
- Design note capture: nine User-Turn Breadcrumbs submitted, audit clean; design commit `99693f65c311f5d24bea7b65041832e47f0978ae`.
- Wiki capture in `tarav-md`: new topical note `notes/wiki/tarav-scripts-and-entry-points.md` (19 Breadcrumbs, audit clean) and two sections appended to daily `2026-10-08.md` (4 Breadcrumbs, no new POIs; the note keeps its 13 earlier `breadcrumb-position-missing` POIs). Start checkpoint `bcb0436cd7d6fe67f61bcb8bd9ab9df9fae528ca`, completion commit `7abcfd990e8dbcd25223475debdee5bdb6ebfdff`.
- Alignment (2026-10-08): the User decided that other repositories are not this request's concern. They will see the error and their maintainers will resolve it. The design section, open question 1 and plan step 4 were updated in place; the request now changes `tarav-py` only.
<!-- tarav.breadcrumb 80e625feceb2 -->
- Execute (2026-10-08): reviewed the topical Wiki, daily entry, and ten relevant User turns before editing. Started with scoped checkpoint `b90e097190c84b54121514f7480bf336c10e7470`. Implemented `tarav_bypass`, guarded root import, console doors, test collection setup, direct-import maintenance script adoption, and guidance. The internal mark's door value and maintenance-script adoption are bounded implementation choices, not additional User decisions.
<!-- tarav.breadcrumb 747964ca6058 -->
- Product verification: isolated committed tree passed 178 tests and Ruff; shared worktree passed 188 tests and Ruff. Built wheel includes `tarav_bypass`. Reinstalled the CLI; plain and Project `tarav run` imports passed. Root `tarav check --project .` completed 362 checks with 65 POIs from existing Project state. Restarted the installed daemon through the CLI and launchd; it returned running with a new PID. Product completion commit `4629dd90ad45e1ac35e9b2b915dae6a9304c9a05`, commit evidence audit clean.
- Product Inlined Capture linked the changed Python and Markdown surfaces to the design turns. TOML and generated JSON have no registered native inline convention; their changes are covered by the scoped commit evidence. Pre-existing Breadcrumb position POIs remain in some older edited surfaces; new labels audit in place. Other repositories and historical `dev/live` scripts were not edited.

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

- Wiki capture appended implementation and verification to the topical note and daily log. Topical audit is clean; daily retains its 13 pre-existing position POIs without new findings. Scoped Wiki start checkpoint `bb26076828a678b0b90c962538806a28d64b0842` and completion commit `60deb3892d1e34885f864f9a8e3f0da3c772a3fd`.
<!-- tarav.breadcrumb ff6558343c58 -->
