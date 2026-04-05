---
name: agentos-git-commit-trigger
description: Run a deterministic semantic git commit flow across existing repositories. USE WHEN the user explicitly invokes `$git-commit-trigger` and wants changes grouped into focused Conventional Commits without tests, pushes, or repository initialization.
allowed-tools: Bash(git status *, git rev-parse *, git add *, git diff *, git diff --staged *, git commit *, git log *, git show *, git -C *, find *, rg *, sed *, mktemp, cat *, rm *)
---

# Git Commit Trigger

Commit changes in existing Git repositories using a deterministic semantic multi-commit flow.

## Trigger Policy

Use this skill only when explicitly invoked by name (for example: `$git-commit-trigger`).
Do not run this workflow automatically at the end of unrelated tasks.

## Workflow

### 1) Preflight

1. Detect target repositories:
   - First try current directory:
     - `git rev-parse --is-inside-work-tree`
   - If current directory is not a repo, scan immediate child directories and keep only Git repos:
     - `for d in */; do git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1 && echo "$d"; done`
2. Work only with repositories that already exist. Do not create or initialize repositories as part of this workflow.
3. If no repos are found, stop and report: `No Git repository found in current directory or immediate child directories.`
4. For each target repo, check pending changes and branch state:
   - `git -C <repo> status --porcelain`
   - `git -C <repo> symbolic-ref --quiet --short HEAD`
5. If any target repo is on detached `HEAD`, stop and report the repo path and blocker instead of committing there.
6. Inspect repo-local guidance that might affect commit format or workflow when relevant:
   - candidate files include `README.md`, `CONTRIBUTING.md`, and `.github/` guidance files
   - use targeted search such as `rg -n "commit|conventional|branch|commitlint" <repo>/README.md <repo>/CONTRIBUTING.md <repo>/.github`
7. Apply repo-local guidance only when it does not conflict with this skill's fixed constraints.
8. If all target repos are clean, stop and report: `No changes to commit.`

### 2) Plan Semantic Commit Groups (Per Repository)

For each target repo, plan how to split changes into granular commits before staging:

- `git -C <repo> status --porcelain`
- `git -C <repo> diff --name-status`
- `git -C <repo> diff --staged --name-status`

Rules:

1. If the repo already has staged files or hunks, treat that staged set as the first commit group's current intent.
2. Do not unstage or broadly restage existing staged hunks unless needed to finish the same logical group.
3. Group changes by concern (feature, fix, refactor, docs, tests, build/CI, chore).
4. Avoid a single big commit when more than one concern exists.
5. Prefer 2+ focused commits when the diff contains separable concerns.
6. If all changes are one indivisible concern, a single commit is acceptable.
7. When staged and unstaged changes share a file, use hunk-based staging so the current commit does not accidentally absorb unrelated edits.

### 3) Gather Commit Context

For each planned group in the current target repo, preserve any existing staged intent, stage only that group's files/hunks, and inspect staged changes:

- `git -C <repo> diff --staged --name-status`
- `git -C <repo> diff --staged --stat`
- `git -C <repo> diff --staged`
- `git -C <repo> add <pathspec...>` (only when more files belong in the current group)
- `git -C <repo> add -p <pathspec>` (for mixed files or partial staging)

Rules:

1. If the first commit group is already staged, inspect that staged diff before adding anything else.
2. Never use `git add -A` in this skill.
3. Review the staged diff for obvious secrets or sensitive material before committing.
4. If the staged diff appears to include `.env` files, raw credentials, private keys, tokens, API keys, or connection strings, stop and report the blocker instead of committing that group.

### 4) Compose Commit Message (Conventional Commit)

Generate a concrete and complete message inferred from the current staged group only.

Rules:

1. Subject format:
   - `<type>(<optional-scope>): <specific summary>`
   - For breaking changes: `<type>(<optional-scope>)!: <specific summary>`
   - Example types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
2. Subject quality:
   - specific, descriptive, and behavior-oriented
   - imperative mood and present tense
   - keep the subject concise, ideally under 72 characters
   - avoid vague summaries like `update files` or `misc changes`
3. Body requirements:
   - include 1 to 6 bullet points depending on diff size
   - each bullet must describe a concrete change (what changed and where)
4. If the diff shows a breaking change, reflect it with `!` or a `BREAKING CHANGE:` footer.
5. Keep the message faithful to the diff; do not invent intent not visible in changes.

### 5) Commit Immediately

Commit each staged group in the current target repo without running tests and without requesting additional confirmation.

Use:

- `git -C <repo> commit -m "<subject>" -m "<bullet1>\n<bullet2>\n..."`

If multiline shell quoting is awkward, use a temporary message file and `git -C <repo> commit -F <file>`.

If `git commit` fails, stop and report the blocker immediately.

- Do not fall back to `--no-verify`.
- Do not amend.
- Do not silently restage the current group into a different shape.
- Preserve the staged state as found at the point of failure so the user can inspect or resume cleanly.

Repeat steps 3-5 until `git -C <repo> status --porcelain` is empty, then continue with the next repo.

## Safety Rules

- Never run `git init` in this skill.
- Never create a new repository in this skill; it only operates on existing repos.
- Never create or switch branches in this skill.
- Never run tests in this skill.
- Never push in this skill.
- Never use `--amend` unless explicitly requested by the user in the same prompt.
- Never use `--no-verify` unless explicitly requested by the user in the same prompt.
- Never commit obvious secrets or sensitive local environment files.

## Output Contract

After committing, report:

1. Created commit list for this run per repo (newest first, e.g. `git -C <repo> log --oneline -n <N>`)
2. Files changed summary per created commit (`git -C <repo> show --name-status --oneline --no-patch <sha>`)
3. Confirmation that no push was performed

If the workflow stops early on a blocker, report:

1. Which repo stopped
2. The blocker that prevented committing
3. Whether staged changes were preserved
