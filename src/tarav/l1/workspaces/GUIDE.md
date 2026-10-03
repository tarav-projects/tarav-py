# Workspaces

<!-- tarav.sessions
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

A Workspace is an identified working folder under `~/Documents/tarav/workspaces/`.
Its `manifest.json` describes what to create; `setup.json` records the last
setup's observed hashes, exact commits, and workspace-specific branches. The
folder may contain copied documents, live symlinks, seeded new documents, and
Git worktrees. Git operations use the user's configured `git` command.
<!-- tarav.breadcrumb 5602ec90ef8e38c54e71928a413ce53a0ff8dcd6a4b60af90254d0c043c72c7d -->

The library is the primary interface. Create a `WorkspaceManifest` with typed
entries and pass it to `WorkspaceDepot.create()`. A featured Project offers
`project.workspaces().create(label=...)` and `.list()`. Project creation pins
each discovered repository's current commit and retains the Project identity
for filtering; `repositories=` selects an explicit subset.

The CLI accepts a JSON manifest with `tarav workspace create --manifest FILE`.
Place initial content for `new` entries under `seeds/` beside that file. Copied
files receive retained seeds automatically, so later reset and clone use the
original bytes even if a source changes. Symlinks remain live and may reflect
target changes. Worktree entries require an exact commit ID, and each Workspace
gets its own branch.

`workspace check --id UUID` reports POIs without repairing anything. `reset`
refuses when it would discard edits or commits. `remove` requires a completed
state, uses Git to unregister every worktree, and refuses work that may be lost.
`sweep` only proposes completed Workspaces older than its age threshold; it
never ages an `open` Workspace into deletion. Use `--apply` for an explicit
removal attempt.

The old `AGENTS.md` manifest and unlock token are retired. A Workspace may
still include an `AGENTS.md` for instructions, but JSON owns setup and status.
