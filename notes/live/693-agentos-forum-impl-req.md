# Agentos Forum — Impl.Req

## Impl.Abstract

- implement `agentos forum`: a cross-project news board — a place to post what other projects should know ("update your anchors because of X, see more..."), with agents checking it and banner nudges on high-traffic commands promoting distribution
- design source: design session `agentos-md/notes/live/591-touched-surface-index-design-session.md` (axis 10 adjacent); user design turns anchored `^20260717-5` (chatlas anchory depot); agendix capture at `agentos-md/skills/agentos-pkg/agendix/Agentos.Forum-agendix.md`
- the accepted model: posts are **appended sections on date-named `.md` files** — append-only, human-readable, machine-appendable; the goal is awareness between projects, not coordination machinery — very simple follow mechanics, nothing more
- scope: `agentos-py` new `forum` subsystem (library + CLI), banner helper wired into one high-traffic command, tests; plus one final slice for a minimal `agentos-forum` skill in `agentos-md/skills/`
- out of scope: multi-forum federation, per-project cursors, post editing/deletion, any moderation, structured post schemas beyond the section convention
- status: executed

## Impl.Index

### Current.State (inspected 2026-07-17)

- no `forum` subsystem exists; `agentos --help` command families: agent, anchory, canvas, init, rev-parse, projects, doctor, test, chatlas, future, tara-tapes, stdlib, skills, skillware, index, mission
- subsystem layout convention: `src/agentos/<name>/` with `core.py` (library) + `commands.py` (thin CLI) + registration in the main parser — `anchory/` is the smallest clean example of the pattern (library-first, depot rooted at an explicit directory, `register_anchory_commands`)
- central-dataset location precedent: chatlas lives at `~/Documents/chatlas/` (its anchory depot at `<chatlas-root>/anchory/`)
- tests: one file per subsystem under `agentos-py/tests/`
- read `agentos-py/AGENTS.md` (and root `AGENTS.md`) before editing

### Design.Decisions (resolved in AUTO mode — recorded, not hidden)

- **forum root** — default `~/Documents/agentos/forum/`, overridable via `AGENTOS_FORUM_ROOT` env var; posts live at `<root>/posts/YYYY-MM-DD.md` (UTC date names the file)
- **post format** — one appended section per post:
  - `## <HH:MM:SS>Z — <title>` heading, body lines below, then a meta line `- from: <project-path-or-name>` (the posting cwd's project, best-effort; `--from` overrides)
  - sections separated by a blank line; no `****` separators (this is not an index surface — plain readable md)
- **CLI surface** —
  - `agentos forum post --title <t> [--body <text>]` (body also accepted on stdin when `--body` omitted and stdin is piped)
  - `agentos forum check` — unread summary: count + titles of posts newer than the cursor; exit 0 always (informational)
  - `agentos forum read [--date YYYY-MM-DD | --all]` — print posts (default: unread only, then advance the cursor; `--date`/`--all` do not move the cursor)
  - `--json` on check/read per house convention
- **cursor** — v1 keeps ONE per-user global cursor at `~/.agentos/forum-cursor.json`: `{"last_read": "<ISO-Z timestamp>", "last_banner": "<ISO-Z>"}`; per-project cursors are a recorded non-goal for v1
- **unread definition** — a post is unread when its (file-date, section-time) timestamp is strictly newer than `last_read`; missing cursor file means everything is unread
- **banner** — library helper `forum_banner_line() -> str | None`: returns one line like `agentos forum: 2 unread post(s) — run 'agentos forum check'` when there are unread posts AND `last_banner` is older than 24h (then stamps `last_banner`); returns None otherwise; must never raise (any error → None) and must stay cheap (stat/scan only the post files newer than cursor date)
- **banner wiring** — v1 wires into `agentos chatlas update` only (print to stderr after the command's normal output); other commands adopt later; the helper is public so wiring is one line per command
- **skill** — minimal `agentos-md/skills/agentos-forum/SKILL.md` Batchy.Skill: orient + `--post`/`--check` arg docs mapping to the CLI, and the posting convention (when a change deserves a post: anything other projects must react to — renames, contract changes, new shared systems)

## Execution.Plan

Run `python -m pytest agentos-py/tests/test_forum.py` per slice; RED→GREEN where marked. Checkpoint commits per execution workflow before starting.

### Slice 1 — forum core library
- `src/agentos/forum/core.py`: `ForumDepot(root)` with `post(title, body, source) -> PostRef`, `posts_since(ts) -> list[Post]`, `read_all()/read_date(date)`; parsing = section splitting on `^## ` in date-named files
- RED: post twice into a tmp root → file `posts/<today>.md` has two sections in order; `posts_since` filters correctly across two date files; malformed sections are skipped, not fatal
- GREEN: implement; append is atomic (write temp + rename, or O_APPEND single write)

### Slice 2 — cursor + banner helper
- `cursor.py` (or in core): read/write `~/.agentos/forum-cursor.json` (path overridable for tests via env var); `forum_banner_line()` per Design.Decisions
- RED: unread posts + stale `last_banner` → line returned and `last_banner` stamped; second call within 24h → None; no unread → None; unreadable root → None (never raises)

### Slice 3 — CLI
- `commands.py`: `post`, `check`, `read` per the surface above; register in the main parser
- RED: CLI-level tests — post → check shows 1 unread → read prints it and advances cursor → check shows 0
- check: `agentos forum --help` lists the three commands; `--json` shapes stable

### Slice 4 — banner wiring
- call `forum_banner_line()` at the end of `agentos chatlas update` (stderr, one line, only when non-None)
- RED: with a fresh unread post and cleared throttle, running the wired command surfaces the line; with no unread, output unchanged
- check: the wired command's existing tests stay green

### Slice 5 — skill
- create `agentos-md/skills/agentos-forum/SKILL.md` per the Design.Decisions skill note (follow `agentos-md` skill conventions — read `agentos-md/AGENTS.md` and an existing small Batchy.Skill as the template)
- check: skill loads/reads coherently; no skillware machinery needed (plain skill)

### Risks / deviation triggers
- `agentos chatlas update` may have output modes (json) where a stderr banner is unwanted → suppress banner when `--json` is set; log the choice
- `~/.agentos/` may not exist → create on first cursor write
- concurrent posts from two agents → appends must not interleave mid-section; if plain append proves racy, use the anchory flock pattern on a `.forum.lock`
- project-name detection for `- from:` may be ambiguous outside a project → fall back to the cwd path; log

### Acceptance signals
- full suite green including `test_forum.py`
- manual round trip: `agentos forum post --title "hello" --body "world"` → `agentos forum check` shows it → `agentos forum read` prints and clears → next `agentos chatlas update` within a fresh throttle window shows the banner for a new post
- the forum root is human-readable md a person can open and scan

## Impl.Log

- 2026-07-18: checkpoint commits created before edits:
  - `agentos-py` `a274be7 chore: checkpoint before forum implementation`
  - `agentos-cli` `de22934 chore: checkpoint before forum cli registration`
  - `agentos-chatlas-py` `dd7e3dd chore: checkpoint before forum banner wiring`
  - `agentos-md` `cdd87ef chore: checkpoint before forum skill implementation`
- 2026-07-18: implementation deviation recorded: an older `agentos future forum` JSONL/thread subsystem already existed despite `Current.State`; v1 replaced it with the accepted top-level Markdown-board model and did not add compatibility aliases.
- 2026-07-18: implemented `agentos.forum` as a simple append-only Markdown board with `ForumDepot`, global cursor helpers, `forum_banner_line()`, `AGENTOS_FORUM_ROOT`, and `AGENTOS_FORUM_CURSOR`.
- 2026-07-18: registered top-level `agentos forum post|check|read`; removed nested `future forum` registration; updated CLI tests and docs accordingly.
- 2026-07-18: wired `forum_banner_line()` into `agentos chatlas update` only, printing to stderr after normal output and suppressing the banner for `--output-mode json`.
- 2026-07-18: created `agentos-md/skills/agentos-forum/SKILL.md` as a CLI-first orientation skill.
- 2026-07-18: default forum root corrected to `~/Documents/agentos/forum/` per user direction.
- 2026-07-18: verification:
  - `agentos-py`: `uv run python -m pytest tests/test_forum.py -q` → 3 passed
  - `agentos-cli`: `uv run python -m pytest tests/test_e2e_forum.py tests/test_e2e_stdlib.py -q` → 10 passed
  - `agentos-chatlas-py`: `uv run python -m pytest tests/test_forum_banner.py -q` → 2 passed
  - `agentos-cli`: `uv tool install --reinstall --editable .` → installed 1 executable: `agentos`
  - manual isolated round trip with temp `AGENTOS_FORUM_ROOT`/`AGENTOS_FORUM_CURSOR`: `post` → `check` showed 1 unread → `read` printed and advanced → `check` showed 0 unread
