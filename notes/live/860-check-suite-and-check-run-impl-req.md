# 860 — A provider's checks are a CheckSuite, and running one gives a CheckRun

<!-- tarav.sessions
5a029cbf = claude-code:8c55cc60-f28a-439f-a6a0-0521567e600e @5a029cbf49a299c9709013b8ccb3fc517b2fb56fed373d3da819b6ea842afa2f
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Autonomous
Status: ready.

The Checks workflow gains two typed objects. `CheckSuite` is what
`CheckProvider.checks()` returns: the provider's Checks as one object that can
be composed and run. `CheckRun` is what running a suite gives: the accumulated
results with summary, selection, sorting and paging. `tarav check --project`
prints the summary and the first 20 POIs instead of every result.

Non-goals: parallel execution; hooks; profiles; storing runs; changing POI
identity or blessings.

## Design narrative

### User direction

A Project's `checks()` is the standard place to look for checks, not the only
one, and it need not be about the whole Project. The check machinery can sit
on individual objects, in their own `checks()`, and be collected elsewhere.
<!-- tarav.breadcrumb a681ceed94db7372cd9899e1b124bca0b9ceb27378bca94fb3edd6769dc1f368 -->

Everything is defined through the check-provider interface. The Checks
workflow should provide basic collecting tools: a place where results
accumulate, with summaries and sorting. Results are not all dumped on screen:
show 20 by default and report the amounts and the types.
<!-- tarav.breadcrumb 7da22cffa975bd4f8b4c980851dedada1d2f6acff981e3304142bd71d089c79a -->

`checks()` should return a typed object that unifies more than a generator of
checks does: it can be told to run them, and it is the place where control
over a run is added later. The name is open; "check suite" was offered. The
design is left to the agent.
<!-- tarav.breadcrumb b5ce132017bf5cd08b021300ae55c28e61be7d3f8daaac8b0193a6ff99c526d7 -->

### Observed (inspected)

- `CheckProvider.checks()` returns an iterable. `run_checks` and
  `check_report` run everything and return one flat dump.
- `POICollector` pages POIs (20 by default) and counts them, but knows nothing
  about Checks: which ran, which did not complete, which found nothing.
- `tarav check --project` prints every result. On md-library that is one line
  per Check of every transcript, thousands of lines.
- md-library's `TranscriptReport` groups results by Check type, tallies open
  POIs per rule and pages a listing with one row per POI. That is this
  workflow's missing tooling, written locally.

### Decisions (agent)

- **`CheckSuite`.** Built from a source of Checks. The source is an iterable,
  or a callable that receives the `CheckRun` in progress and returns an
  iterable; the callable form lets a provider decide what comes next from the
  results so far (a parser Check that stops the rest). A source may also
  yield another `CheckSuite`, which is how checks are collected from other
  providers, or a ready `CheckResult` for a Check that cannot run now.
  Iterating a suite yields its Checks lazily. `CheckSuite.of(value)` accepts a
  suite or any iterable of Checks, so providers that still return a tuple or
  generator keep working.
- **`suite.run()`** runs each Check as it arrives and returns the `CheckRun`.
  A Check that raises becomes a `failed` result; one bad Check does not hide
  the others. Options are keyword-only (`into`, `on_result`); this is where
  later control is added.
- **`CheckRun`.** Holds results in run order. `summary()` counts Checks by
  type and status and POIs by code. `report()` lists POIs, one row per POI
  identity with its findings, filtered by code or Check type, sorted by run
  order, code or number of findings, 20 per page. Given a blessing store it
  adds standing, puts open POIs first and tallies the open ones per code.
  `clean` is true when every Check completed and no POI is open.
- **Names.** `CheckSuite` and `CheckRun`: "collector" is `POICollector`'s word
  and "runtime" means something else in Tarav.
- `run_checks` and `check_report` stay for existing callers.
- Tarav's own providers (`TaravProject`, SKW skills, Workspace, CLI Command)
  return a `CheckSuite`.

## Interface sketch

In `tarav.l1.checks`, both `TaravObject`s of the Checks workflow:

```python
class CheckSuite:
    def __init__(self, source=(), *, name: str | None = None): ...
    @classmethod
    def of(cls, value) -> "CheckSuite": ...        # a suite, or any iterable of Checks
    def __iter__(self): ...                         # Checks, lazily, nested suites flattened
    def run(self, *, into: "CheckRun | None" = None, on_result=None) -> "CheckRun": ...

class CheckRun:                                     # also a POIProvider
    results: list[CheckResult]
    def add(self, result: CheckResult) -> CheckResult: ...
    def results_of(self, check_type) -> tuple[CheckResult, ...]: ...
    def pois(self) -> tuple[POI, ...]: ...
    def summary(self) -> dict: ...
    def report(self, *, offset=0, limit=20, code=None, check=None,
               sort="run", store=None, blessing=None, detail=False) -> dict: ...
    def clean(self, *, store=None) -> bool: ...

def render_check_run(report: dict) -> str: ...
```

- `source` is an iterable, or a callable `(run) -> iterable`. Items are a
  `Check`, a `CheckSuite`, or a `CheckResult`.
- `summary()`: `checks`, `by_status`, `incomplete` (not completed), `pois`
  (distinct identities), `findings` (emissions), `by_check` (per Check type:
  runs, statuses, POIs), `by_code`.
- A `report()` row is one POI identity: the first emission's record plus
  `findings`, `subjects` and `messages` (distinct, in order). With `store`:
  `blessing` standing per row, open rows first, `open_by_code`. The result
  carries the summary, `matching`, `offset`, `shown`, `next_offset`, `items`.
- `render_check_run` prints the rows, then one line of Checks by type and
  status, one of POIs by code, and the paging hint.

`tarav check --project`: build `CheckSuite.of(project.checks())`, run it,
print `render_check_run(run.report(...))` or the JSON report. Exit 0 when
clean, 1 otherwise, 2 when the Project declares no checks (unchanged). Options
`--limit`, `--offset`, `--code`, `--check`, `--sort`. While running, progress
goes to stderr when it is a terminal, so a long run is not silent.

## Acceptance

- A suite built from a generator, a tuple, a nested suite and a callable
  source all run in order; the callable sees earlier results in the run.
- A raising Check gives a `failed` result and the run continues.
- `report()` pages at 20, groups emissions of one identity into one row,
  filters by code and by Check type, and sorts three ways.
- With a store, a blessed POI does not make the run unclean.
- `tarav check --project` on a Project with more than 20 POIs prints 20 rows,
  the totals and the next offset.
- Existing tests of workspaces, SKW and live help pass with providers
  returning a suite (tests that index `checks()[0]` are adjusted).

## Impl.Req.Wiki

Product owner: `tarav-py`.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: requests 858 and 859; md-library-py request 620.
Capture status: pending.

## Execution.Plan

1. `CheckSuite`, `CheckRun`, `render_check_run` in `tarav.l1.checks`; tests.
2. `tarav check --project`: summary, 20 POIs, `--limit`, `--offset`,
   `--code`, `--check`, `--sort`; tests.
3. Tarav's providers return a suite; `ARCHITECTURE.md`/`AGENTS.md` where they
   describe the interface.
4. Full suite; wiki capture.

## Impl.Log
