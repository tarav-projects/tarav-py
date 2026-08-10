# Run.Workspace

A `Run.Workspace` holds one run of one agentic workflow. It lives outside every
project, at `~/.agentos/workspaces/<date>-<slug>/`.

## It is a Volatile.Surface

No `Stable.Surface` may depend on it, which is what makes deleting one routine
rather than a decision requiring an audit.

**The dependency arrow points one way.** A workspace may reference a stable
surface. Nothing stable may reference a path inside a workspace — not a script,
not a config, not another workflow. The moment something does, the guarantee is
gone and you have an untracked dependency nobody is maintaining.

**Content leaves only by copy.** When a workspace produces something worth
keeping, a stable surface takes that content and owns it. Never a link back in.
Promotion ends with the workspace deletable again.

Volatility says nothing about value. A good result found here is promoted, not
discounted.

## It is defined by its AGENTS.md

Exactly one surface is required. An agent landing here cold reads `AGENTS.md`
and knows what this is:

- **kind** — which workflow created it
- **purpose** — one line: what question this exists to answer
- **provenance** — what it was seeded from, and at what version
- **how to run it** — its own commands and scripts
- **status** — `open`, `harvested`, or `abandoned`
- **extracted** — what left, and where it went

`status` and `extracted` are what make disposal decidable. Without them nothing
is ever deleted, because nobody is ever sure. They live in a `### manifest`
section as `- key: value` lines, in the same file as the prose, so the two
cannot drift.

Nothing below `AGENTS.md` is mandated. Each kind of workspace imposes whatever
shape it needs.

## Git inside, never around

A workspace is its own repository, so its history is debuggable. It is never a
submodule, subtree, or sibling of a tracked repository, and never created inside
one.

## It is not the session scratchpad

Work that dies with the chat gets a temporary file. A workspace is for work that
must survive the session and be returned to. Everything below that threshold
would only fill this directory with things nobody reads.

## Disposing of one

`agentos workspace sweep` lists candidates and deletes nothing. `sweep --apply`
deletes them. A workspace whose work has been extracted is finished, and
deleting it is the normal end of its life rather than a loss.

---

surface-token: aws-unlock:6b1f04c73a92
