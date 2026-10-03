# 840 — LineMarkdown: a strict floor parser for owned Markdown formats

<!-- tarav.sessions
5a029cbf = claude-code:8c55cc60-f28a-439f-a6a0-0521567e600e @5a029cbf49a299c9709013b8ccb3fc517b2fb56fed373d3da819b6ea842afa2f
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented.

Add `LineMarkdownModel`, a strict sibling of `MarkdownNormalModel` in
`tarav.l1.surfaces.markdown`. It parses a restricted, explicitly named Markdown
dialect in which every block delimiter (code fences and `$$` math blocks) sits
alone on its own line. It is a floor: the first violation raises a structured
error and no model is returned. Its result is a `MarkdownNormalModel` subtype,
so existing helpers keep working, and it adds recognized math blocks.

Non-goals: no change to `MarkdownNormalModel` or its four lenient consumers
(Wiki, Breadcrumb auditing, `mdblocks`, Chatlas context); no block, paragraph or
inline layer (higher-resolution layers belong to consumers); no POI or Check
types in the surface module (consumers map the error to their own POIs).

The first consumer is md-library's transcript linter, designed in
`md-library-py/notes/live/582-tarav-transcript-checks-impl-req.md`.

## Design narrative

### User direction

Tarav's Markdown parser is deliberately minimal because it is the base other
parsers build on. md-library's needs are met by extending it, and Tarav is
changed where it does not support that.
<!-- tarav.breadcrumb 36971b13a1a97e2f3700208e919849cbbdc4d7c044f4b56fa1d1722dc6977e4e -->

A higher-level parser consumes the lower-level model, never the original file:
"you can use me as your representation of the file, and now you can further
parse this representation".
<!-- tarav.breadcrumb 6b29da8ffe7d9f0e3a298b899e7c2741adbcc43f8078e1a9917108f231d90e8e -->

The base parser is a line parser, named as such: block delimiters may not be
mixed with content on a line. A single-line `$$ … $$` equation is not allowed;
there is a single way to write an equation block. The dialect is deliberately
restricted for formats we own, because a restricted base is easier to build on.
<!-- tarav.breadcrumb eeea6c1422d0d5e653c2e07889bab43c4bcdc0cc006d904de4cc6396110612da -->

This parser is a floor linter: minimal ground truth about structure. Its
findings are not blessable. Above it, heuristic linting favours recall and
accepts false positives because agents judge the long tail.
<!-- tarav.breadcrumb 7e20c04d1292ee0de3c494399a0aa3399f06c7bdeb5b7fd8134db46ac8f190cc -->

Like a compiler, it stops hard at the first violation: once fencing is not
trusted, nothing after it can be reliably checked.
<!-- tarav.breadcrumb 85e4b6c5ffd218c5926dda302bc329e8cacb1fbe9fd63f317df7fbd6e1296750 -->

To avoid disturbing existing users of the current parser, the line parser is an
additional parser rather than a change to `MarkdownNormalModel`.
<!-- tarav.breadcrumb ff402e90fbdf53a4b097f6fbe6f2a8e67df0134fdc25de4acd766f4f3254a070 -->

### Current behaviour (inspected)

`src/tarav/l1/surfaces/markdown/model.py::_parse` never fails. An unclosed
fence is recorded with `end=None`; a line like ```` ```x``` ```` opens a fence
whose info string swallows the closer, and that fence then absorbs the rest of
the document silently. `$$` is unknown, so headings inside math blocks are
reported as headings. Consumers are `l1/wiki`, `l1/breadcrumbs/auditing.py`,
`l1/stdlib/mdblocks/core.py` and `l2/breadcrumb_workflows/chatlas_context`.

### Dialect rules (agent proposal, derived from the User's rule)

Outside code fences, a line containing an unescaped `$$` must consist of
exactly `$$` once stripped of surrounding whitespace; it opens or closes a math
block. Inside a math block the same holds for its closer. Code-fence lines
inside a math block, and `$$` inside a code fence, are content.

Violations, each with a stable rule code and source span:

| Rule | Meaning |
| --- | --- |
| `LineMarkdown.Math.NotAlone` | `$$` shares its line with other text |
| `LineMarkdown.Math.Unclosed` | a math block is still open at end of text |
| `LineMarkdown.Fence.InlineClose` | a backtick fence opener's info string contains a backtick (```` ```x``` ````) |
| `LineMarkdown.Fence.Unclosed` | a code fence is still open at end of text |

Headings are recognized only outside fences and math blocks. `diagnostics` is
always empty: a model exists only when the text conforms.

Corpus evidence from md-library (422 transcripts): 12,223 own-line `$$`
delimiters versus 495 violating lines in 42 files (338 single-line blocks, 59
openers and 47 closers carrying content, 25 with a trailing `(N)` number, 26
mid-line). md-library's transcript spec already prescribes own-line `$$`.

## Impl.Req.Wiki

Product owner: `tarav-py`.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: `tarav-md/notes/wiki/checks-workflow.md`,
`tarav-md/notes/wiki/poi-system.md`, `tarav-md/notes/wiki/projects.md`.
Supporting chat: claude-code session `8c55cc60-f28a-439f-a6a0-0521567e600e`.
Capture status: completed in `tarav-md/notes/wiki/line-markdown-floor.md` (tarav-md 193f118); a daily section was added to `notes/wiki/daily/2026-10-02.md` but left uncommitted because another session has uncommitted edits in that file.

## Execution.Plan

1. **Model and error.** Add `src/tarav/l1/surfaces/markdown/line.py` with
   `MarkdownMathBlock`, `LineMarkdownViolation(ValueError)` (rule, message,
   span) and `LineMarkdownModel(MarkdownNormalModel)` with its own TypeShip,
   `math_blocks`, an extended RecordInterface and `math_line_numbers()`.
   Export from `tarav.l1.surfaces.markdown`; register the Type in
   `tarav.l3.runtime`.
   Check: conforming text parses; fences, math blocks and headings are correct;
   headings inside blocks are excluded; Record round-trip holds.
2. **Floor behaviour.** Each rule raises at the first violation with its rule
   code and line; later violations are not reported; the lenient parser is
   unchanged on the same inputs.
   Check: focused tests in `tests/test_line_markdown.py`.
3. **Architecture and docs.** Extend the surfaces assertion in
   `tests/test_architecture.py`; update `ARCHITECTURE.md`'s surfaces row and
   `src/tarav/l1/surfaces/README.md`.
   Check: architecture and surfaces tests pass; ruff on touched files.

Risks: the shared worktree carries unrelated in-progress changes from another
session; commits must stay scoped to this request's files, and test failures
outside the touched area are reported, not fixed.

## Impl.Log

- Design: the error is a plain exception rather than a POI, keeping
  `surfaces` free of Check/POI imports; consumers own the POI mapping.
- Slices 1–2: `src/tarav/l1/surfaces/markdown/line.py` adds
  `LineMarkdownModel`, `MarkdownMathBlock` and `LineMarkdownViolation`; it
  reuses the base module's line, heading and fence types and regexes. Exported
  from `tarav.l1.surfaces.markdown` and registered in `tarav.l3.runtime`.
  `tests/test_line_markdown.py`: 13 passed (conforming parse, Record round
  trip, each rule with its line, first-violation stop, escaped `\$$` and tilde
  info strings, lenient parser unchanged).
- Slice 3: surfaces assertion in `tests/test_architecture.py` extended; it
  passes within the full architecture run (in isolation it fails before and
  after this change because Workflow resolution is not configured).
  `test_subsystem_import_graph_is_acyclic` fails on a `project` →
  `project.reading` cycle from another session's uncommitted work; unrelated.
  README updated. Ruff clean on touched files.
- Deviation: `ARCHITECTURE.md`'s surfaces row is updated in the worktree but
  left out of this request's commit, because another live session changed the
  same file (SKW ReadingGraph) during execution and evidence commits take whole
  files. It will land with that session's commit or a later scoped one.
- Product Breadcrumbs: three on `line.py` (dialect rules, hard stop, sibling
  parser), audit clean.
