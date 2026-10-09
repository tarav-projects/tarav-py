# 885 — TypeScript Breadcrumb convention (draft) — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: ready.

Add TypeScript as a third native Breadcrumb surface beside Markdown and
Python, so `tarav breadcrumbs submit chatlas-context` and `audit` work on
`.ts`, `.tsx`, `.mts` and `.cts` files. First consumer: the Tarav Center
extension (`vscode-tarav-center/src/*.ts`), whose TypeScript carries no
Breadcrumbs today.

Non-goals: a TypeScript parser; JavaScript files; session declarations
inside TypeScript; block-comment markers; reviving the standalone
`tarav surfaces` command.

## Design narrative

Request 002 of the Tarav Center extension reported that its TypeScript
files carry no Breadcrumbs because no convention exists for TypeScript. The
User asked the agent to draft one itself and to run it as an autonomous
Develop pass.
<!-- tarav.breadcrumb 7949294907652d4a2aa267228f0bef23ed3265abb5b42a374f1e73cd606839a3 -->

### Current behavior

- `tarav.l1.breadcrumbs.surfaces`: `infer_surface_language` maps `.md`,
  `.markdown` and `.py`; `render_surface_label` renders `<!-- label -->` or
  `# label`.
- `tarav.l1.breadcrumbs.auditing._surface_labels` and
  `tarav.l2.breadcrumb_workflows.chatlas_context.workflow._markers` /
  `_malformed_marker_lines` branch on `markdown` and `python`. Python markers
  are tokenizer-confirmed comments from `PythonNormalModel.comments`
  (`tarav.l1.surfaces.python`), matched whole against `#\s*<core>\s*$`; a
  model with diagnostics raises `BreadcrumbError`.
- `tarav breadcrumbs submit|audit --language` accepts `markdown|python`.
- `tarav.l1.surfaces.commands` maps extensions to normalizers for the
  disconnected `tarav surfaces` command.
- A Python surface has no session declaration; submission takes
  `--provider/--session-id`, and the alias is declared in the related Wiki
  Note or Impl.Req. The inline-capture guidance says so.

### Agent choices (autonomous; not User decisions)

- **Surface model.** `tarav.l1.surfaces.typescript.TypeScriptNormalModel`, a
  registered TaravObject like the Python model, with `comments` (kind `line`
  or `block`, text, span) and `diagnostics`. A small lexer, not a parser: it
  skips single- and double-quoted strings, template literals including
  nested `${...}` expressions, block comments and regular-expression
  literals. A `/` starts a regular expression when the previous significant
  token is absent, an operator or opening punctuation, or a keyword such as
  `return`; otherwise it is division. Unterminated strings, templates, block
  comments or regular expressions are diagnostics.
- **Marker form.** Only a `//` line comment whose whole text is the marker
  counts: `// tarav.context <alias>:<prefix>` and `// tarav.breadcrumb <id>`,
  the same cores as Python with `//` for `#`. Submission replaces the
  comment span, as for Python.
- **Language key** `typescript`; suffixes `.ts`, `.tsx`, `.mts`, `.cts`.
- **Diagnostics block submission and audit**, as for Python, so a marker is
  never placed by a lexer that lost its place.
- **Session.** As for Python: no declaration in the file; pass
  `--provider/--session-id`.
- **Known limit.** In `.tsx`, `//` inside JSX text would read as a comment.
  Recorded, not handled.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`daily/2026-10-08.md`, and the inline-capture skill guidance
`tarav-md/skills/tarav-hugentics/references/inline-capture.md`. Supporting
session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status:
pending.

## Execution.Plan

1. Surface model and tests: comments found; strings, templates, regular
   expressions and block comments skipped; diagnostics.
2. Breadcrumb wiring: language inference, label rendering, audit labels,
   chatlas-context markers and malformed markers, CLI choices, surfaces
   command map. Tests through the CLI with a temporary store.
3. End to end on `vscode-tarav-center/src/*.ts` with the real session:
   provisional markers, submit, audit, compile.
4. Guidance: inline-capture lists TypeScript; Wiki capture; commits.

## Impl.Log
