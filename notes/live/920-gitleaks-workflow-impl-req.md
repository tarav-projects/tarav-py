# Gitleaks workflow — implementation request

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Status: complete, 2026-10-18.
Knowledge.Surface: wiki.

Integrate gitleaks, the secret scanner, into Tarav as a workflow under Git (`tarav.l1.git.gitleaks`). Gitleaks detects; Tarav keeps its reports in a depot, verifies their findings in Project checks, and turns them into actions of the owning Project, falling back to the System Project for repositories no Project owns. Gitleaks also runs as a default Git hook handler that stops commits with staged secrets.

Non-goals: cleaning existing repositories (that scan runs from Tarav afterwards), scanning working trees, writing a detector of our own, rotating keys.

## Design

The User chose the gitleaks binary over Python alternatives (no official library exists; detect-secrets scans files, not history; ggshield sends content to a cloud service), called transparently from a gitleaks workflow, with no adapter abstraction and nothing renamed.
<!-- tarav.breadcrumb 6e17f8936a1d -->

The workflow sits under Git. Gitleaks joins the default hook handlers. A Project without hooks installed raises a POI as a reminder; a Project opts out by blessing it. The hook scans only the commit; a full history scan runs on request.
<!-- tarav.breadcrumb e4dfc227e5a3 -->

A stopped commit is overruled with the existing comma-separated `TARAV_GIT_HOOKS_OVERRULE` (request 916), for example `gitleaks,tarav-change`; nothing in that contract changes.
<!-- tarav.breadcrumb 842ac906bc84 -->

Repositories scanned from Tarav that no Project owns record their POIs in the System Project, the fallback Project.
<!-- tarav.breadcrumb c60c26e9a649 -->

Detection and verification are separate steps. Gitleaks runs independently of the checks, on request or in the hook, and every run leaves a new report in a depot. Tarav's check double-checks each reported finding: the finding still being there is the situation that raises the POI and opens the action. The action closes when the data disappears, when the fingerprint is in `.gitleaksignore`, or when the latest report no longer lists it. For a finding in a commit, "still there" means the commit is reachable and the file and lines exist in it: Git addresses content by hash, so that is exactly what gitleaks scanned.
<!-- tarav.breadcrumb 344b18bf259a -->

Blessing a finding's action is appending its fingerprint to `.gitleaksignore`, the source of truth shared with gitleaks; the closing is recorded on the Action tape like any other.
<!-- tarav.breadcrumb 1d1ccef4c1f2 -->

Working trees are not verified. A report without a commit (the hook's staged findings) opens an action that is closed by hand. Keep the system simple.
<!-- tarav.breadcrumb 1a14650ebd23 -->

### Decisions taken in Autonomous mode (Agent, not User)

- Default handlers apply when a Project's config has no `git.hooks` section and its root is a Git repository root. An explicit handler list is respected as written; tarav-py's own config gains `gitleaks`.
- A repository is keyed in the depot by its root commit (the first parentless commit reachable from HEAD), with its path kept in each run. Moving the folder keeps the key; a history rewrite starts a new one. A repository without commits is not scanned.
- Owner: the nearest Project marker at or above the repository root; otherwise the System Project.
- Hand-appended fingerprints close the action as gone; blessing closes it as blessed. Both leave a closing on the tape.
- Gitleaks missing from PATH: a POI from the check; the hook warns and lets Git continue.

## Current implementation observations

Inspected on 2026-10-18:

- `src/tarav/l1/git/hooks.py`: `GitHookHandler` (name, hooks, `run(call)`, `check(project)`), `GitHookRefusal`, `GitHookCall.overrules`, `hooks_config`, `git_hook_checks` (returns nothing when a Project configures no hooks), `HooksNotInstalled` (a `CheckPOI`, not blessable).
- `src/tarav/l1/git/change.py`: the model for a handler whose stops become actions (`_hand_to_project`, which reads the Project marker to avoid importing the Project Type).
- `src/tarav/l1/actions/pois.py`: `POIResolutionAction` closes `gone` when a conclusive suite no longer raises the POI and `blessed` by an operator; a POI whose check type never runs in a suite stays open. `action_id(poi)` follows the POI identity.
- `src/tarav/l1/actions/__init__.py`: `close_run` calls the action's `output(exit, run, context)` when an exit is taken.
- `src/tarav/l2/project/system.py`: `TaravSystemProject` at `~/Documents/tarav/system/` (present on this machine).
- gitleaks 8.30.1: `gitleaks git [path] --redact --report-format json --report-path <file> --exit-code <n> --gitleaks-ignore-path <dir>`, and `--pre-commit --staged` for staged changes. A finding carries RuleID, File, StartLine, EndLine, StartColumn, EndColumn, Match, Secret (redacted), Commit, Author, Email, Date, Message, Fingerprint (`commit:file:rule:line`).

## Impl.Req.Wiki

Product: `tarav-py`. Documentation owner: `tarav-md/notes/wiki/` (new topic note `gitleaks.md`, daily `2026-10-18.md`). Supporting turns are attached above.

## Execution.Plan

Data shape:

- `GitleaksRun` Record (`Tarav.Git.Gitleaks.Run`): repository path, key (root commit), kind (`history` or `staged`), HEAD, gitleaks version, time, report file name, finding count. Depot `~/Documents/tarav/gitleaks/<key>/` (override `TARAV_GITLEAKS_ROOT`): `runs/<time>.json` and `reports/<time>.json`, the report exactly as gitleaks wrote it.
- POIs, family `Tarav.Git.Gitleaks.POI`: `Finding` (blessable; situation `{repository, fingerprint}`; its action blesses by appending to `.gitleaksignore`), `Staged` (blessable; situation `{repository, run}`; raised only through the hook), `NeverScanned` and `Missing` (blessable).
- `GitleaksCheck(root)` raises Finding, NeverScanned and Missing; `GitleaksStagedCheck` raises Staged and never runs in a suite.

1. **Feature — runs and depot.** Done. `scan(root)` runs a history scan and records a run; `tarav git gitleaks scan --repo PATH`. Check: a temporary repository with a committed token yields a run whose report lists it; a repository whose fingerprint is in `.gitleaksignore` yields none.
2. **Feature — verification, POIs and actions.** Done. The check, the owner resolution, registration after a scan, the System Project's checks for unowned repositories, and blessing that appends to `.gitleaksignore`. Check: a finding raises one POI; ignoring it, rewriting the commit away, or a later clean report removes it; blessing appends the fingerprint and closes the action as blessed; an unowned repository's actions land in the System Project.
3. **Feature — hook handler and defaults.** Done. The `gitleaks` handler on pre-commit, default handlers, blessable `HooksNotInstalled`, tarav-py enabling it. Check: a commit with a staged token is stopped and opens a Staged action; the overrule lets it through; a clean commit passes; without gitleaks on PATH the hook warns and Git continues.
4. **Documentation.** Done. AGENTS.md (SKW source), ARCHITECTURE.md, the Wiki.

Tests build tokens at run time so no literal secret enters the repository. Run `uv run pytest tests/test_git_gitleaks.py`, then the full suite and ruff.

## Impl.Log

- 2026-10-18: Designed from the discussion above and started Develop in Autonomous mode.
- Start checkpoints: tarav-py `b1ec6ff` (this note); tarav-md `ee6dc22` (empty; another session had just committed its own edits).
- Slice 1 (runs and depot): `tarav.l1.git.gitleaks` with `GitleaksRun`, `GitleaksDepot`, `repository_key`, `run_gitleaks` (history or staged), and `tarav git gitleaks scan --repo`. `tests/test_git_gitleaks.py` failed at import before and passes after (3 tests: a committed token is reported with its commit, file and line and a redacted secret; an ignored fingerprint is not; the CLI scans). Record contract tests pass; ruff clean. Breadcrumbs on `gitleaks.py` (2).
- Slice 2 (verification, POIs, actions): `GitleaksCheck` verifies each finding of the latest history report (fingerprint not in `.gitleaksignore`, commit reachable from a ref, file and lines present, read with one `git cat-file --batch`); POIs `Finding`, `Staged`, `NeverScanned`, `Missing` (all blessable); `GitleaksFindingResolution` appends the fingerprint to `.gitleaksignore` when blessed (`output` of the blessed exit, the one hook `close_run` offers); `owner_of` (nearest Project marker, else the System Project); `register_run` after a scan; the System Project's suite gains `unowned_checks()`. The scan command registers on the owner. Tests: 9 in `tests/test_git_gitleaks.py` (a finding raises one POI; ignoring, an unreachable commit after reset and gc, and a later report without it each remove it; blessing writes the fingerprint and the action closes as blessed; owner resolution and System Project registration; the CLI registers on the owner with an isolated records root; unowned checks). Full suite 345 passed; ruff and architecture clean. Breadcrumbs: `gitleaks.py` (4 more), `system.py` (1).
- Slice 3 (hook and defaults): the `gitleaks` handler scans staged changes on pre-commit (`run_gitleaks(kind=staged)`, inheriting Git's `GIT_INDEX_FILE`); findings open a `Staged` action on the owner through `GitleaksStagedCheck`, a check that never runs in a suite, so the action stays open until closed by hand; without an overrule the commit is stopped. A missing binary is a warning and Git continues. `DEFAULT_HANDLERS = ("gitleaks",)`: install starts from it when the config has no `git.hooks`, and `git_hook_checks` uses it for Projects without that section whose root is a repository root. `HooksNotInstalled` is blessable. Two `test_git_hooks.py` assertions encoded the old "no section, nothing to check" behavior and were updated for the new default. Four new tests (stop and action, overrule recorded, clean commit and missing binary, default checks and blessable POI). Full suite 349 passed; ruff clean. tarav-py now runs `tarav-change` and `gitleaks`; this slice's own commit is the first through the gitleaks hook.
- User, mid-slice: do not scan `~/Documents/tarav/chatlas` for now; it is dealt with later. Nothing in this request scans it: checks only read the depot, and a repository is scanned only by an explicit `tarav git gitleaks scan`.
- Defect found after slice 3: with gitleaks a default handler, the suite's hooked commits (tarav-change and hooks tests) wrote 27 staged runs into the machine's depot. `tests/conftest.py` now points `TARAV_GITLEAKS_ROOT` at a temporary folder, as it does for records and the run registry; rerunning those tests leaves the depot with tarav-py's own run only. The 27 leaked runs, all from pytest temporary repositories, were deleted.
- Slice 4 (documentation): tarav-py `8de81e8`: AGENTS.md (SKW source; Breadcrumb submitted on the product, copied back, rebuild byte-identical) and ARCHITECTURE.md, both audited clean.
- Wiki capture: tarav-md, `notes/wiki/gitleaks.md` (new) and `notes/wiki/daily/2026-10-18.md`; 9 Breadcrumbs, audits clean.
- Open: run the cleanup scan from Tarav over the project repositories (Chatlas excluded for now), and triage the findings.
