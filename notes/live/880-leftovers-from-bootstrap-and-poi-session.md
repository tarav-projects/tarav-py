# 880 — Leftovers from the bootstrap and POI session

Informal note, written by the agent on 2026-10-08 at the User's request. It
lists what that session discussed and left unimplemented. It is a reminder
list, not a design and not an Impl.Req. Source chat: Claude Code session
`d82f1801-d3f2-4deb-9c95-297028a54b7a`.

POI unification and rendering is not listed here: it is Impl.Req 879
(`879-one-poi-system-and-rendering-impl-req.md`), designed and not executed.

## Designed or agreed, not built

- **Diagram `Finding` family.** About 74 codes across about 85 sites in
  `l2/unsorted` and `l2/lines`, nearly untested. 879 defers it; it needs its
  own request to become atomic POI types without `code`.
- **Tracked POIs.** Persistent, issue-like states (open, blessed, closed,
  reappearing) exist in `l1/poi/tracking.py` and `l2/poi/board.py` and nothing
  uses them. `tarav check` is not wired to them. Idea from the discussion: a
  base class signals "tracked", with a constructor overrule where the type
  allows it.
- **Notification log.** A typed event log for notification POIs, as the second
  axis beside tracked states. Only discussed.
- **Emitting code in the POI view.** The User agreed to an `emitted-at` entry
  in the `reported-poi` view: file and line of the statement that raised the
  POI. Today `raised-by` shows the check class line. Not started.
- **"What was done before" entry** in the `reported-poi` view. Mentioned, not
  designed.

## Discussed, never turned into a request

- **Contextualization evaluation.** The opening goal: a test workflow that
  measures whether an arriving agent contextualizes well in a Tarav Project.
- **Redundancy of bootstrapping.** The User wanted at least three independent
  ways. Built so far: the agents file checks and the skill checks.
- **Live help from the run registry.** The registry retains what `tarav run`
  executed; nothing surfaces it as recent usage examples in help or context.
- **Speed-bump alternatives for the import guard.** Only `tarav_bypass` was
  done; the file check and the CLI flag were set aside.
- **Agents-file adoption.** The root and `tarav-md` do not yet have a
  Skillware source for their agents file. Deliberately not done: current POIs
  are a test bench and are not being repaired.

## Decisions waiting on the User

- The four questions in the 879 note: root POI type in `l0`; deferring the
  Diagram family; the name `occurrence` for the view entry replacing
  `finding`; which second renderer matters.
- Are check POIs tracked by default, or opt-in?
- Is the marker `agents` entry data or settings? Request 878 already treats
  the two prompt switches of `AgentsMd` as settings and the main file and
  aliases as data; the User has not confirmed this.
- Request 878 agent choices to confirm: settings mistakes raise
  `SettingsError` and are not POIs; every setting needs a default; a key may
  be addressed without its partition when only one declares it.

## Loose ends

- About 60 uncommitted entries in `tarav-py` from another agent's refactor
  (`l0/project`, `l0/_core/home.py`, skills moved to `l2/project/skills`, and
  others). Not reviewed, not committed.
- Nine Wiki notes in `tarav-md` still carry unsubmitted provisional markers;
  one sentence in `assertions-scoring.md` is out of date.
- Wiki capture for 879 is pending.
- `tarav breadcrumbs submit` does not mention the registration fallback in its
  error message.
- Obsolete tests outside the test paths: `tests/cli/test_check.py` and one in
  `tests/test_scoped_lines.py`.
- `tarav skw skills poi` was not updated with the rest of the POI work.
- Some POI messages are still labels, for example "unannotated-output-link".
  The coverage check planned in 879 should surface these.
- The PaperSON automatic dataflow loop stopped working with the Iterante
  removal.
- `md-library-py` and `g70203-py` will break on the POI interface and the
  import guard. Declared not our concern; listed so nobody is surprised.
- Edits in folders without Git have no history: root `AGENTS.md` and README,
  the HTI catalog, `~/.tarav/config.json`.
- An empty, out-of-order commit `c11be05` in `tarav-md`. Harmless.
