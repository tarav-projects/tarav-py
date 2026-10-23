# Programs

A Program is a trusted Tarav class defined in a Project's Python code. It owns
an Action graph and selects checks. The runner handles graph movement, tokens,
persistence and recovery. Execution is represented by active Action occurrences.
<!-- tarav.breadcrumb 68c8cb9e2753 -->

`NodeAction` and `EdgeAction` are ordinary Action Types with two graph roles.
They supply prompts and class identities; the engine takes their checks from
the Program. A connection is `Transition(source_node, edge_action, target_node)`.
Each concrete class declares its own `class_entity()`. The operator StepRunner
cannot complete these Actions; the Program runner controls their lifecycle.

```python
class DocumentProgram(TaravProgram):
    initial = (Ready,)
    terminal = (Reviewed,)
    graph = (
        Transition(Ready, Rewrite, Draft),
        Transition(Draft, Revise, Draft),
        Transition(Draft, Review, Reviewed),
    )
    # Define this Program's class_entity() as for any concrete Tarav Type.
```

The example assumes those NodeAction/EdgeAction classes already exist. For
complete definitions with real checks see `tests/test_programs.py` and the
Project-only module in `tests/test_project_programs.py`.

## Check policy belongs to the Program

Override `checks(run, occurrence, *, operation)` to return a CheckSuite or an
iterable of Checks. `occurrence.action` is its Action TypeShip; `occurrence.id`
identifies this particular visit. `run.typed.data` contains explicit JSON input.
The Program can reuse a Check class anywhere and organize its Python code as
useful. The hook's lifecycle slots are:

| Operation | When called |
| --- | --- |
| `enter` | Before activating an initial or successor Action |
| `status` | When the caller asks about an active Action under its token |
| `complete` | Before closing a node or edge occurrence |

The default hook selects no checks. The engine does not automatically select
source-node status checks at departure or target-node status checks at arrival.
A Program can explicitly reuse those checks in `complete` or `enter` if that
is its policy. Checks for working on an edge can differ from its completion
requirements; an unfinished document need not violate its rewrite Action.
<!-- tarav.breadcrumb a75285fa04d0 -->

`available(run, occurrence)` may filter the base method's declared outgoing
connections using Python logic. It cannot invent a connection or authorize an
edge from a different node. `checks` receives the source run for completion
and the candidate run for entry. The candidate replaces only the selected
occurrence. Evidence names Action, occurrence, graph role and operation.

## Lifecycle and tokens

1. `ProgramClass.start(project={"id": ..., "name": ..., "root": ABSOLUTE_PATH},
   data={...})` verifies entry for each Type in `initial`, then opens the overall
   execution and its NodeAction occurrences. Failed entry creates no registry.
2. `runner.choose(node_token, edge_type_uuid_or_name)` checks graph permission,
   Program availability, source completion and edge entry. Success closes the
   NodeAction, opens the EdgeAction and issues its own token immediately.
3. Work on the product, then `runner.step(edge_token, data={...})`. Edge
   completion and destination entry must pass. Success closes the edge and
   activates the destination NodeAction with a new occurrence and token.
4. `runner.status(token)` evaluates that occurrence's Program-selected `status`
   checks. It never advances, rotates tokens or writes the run.
5. A node listed in `terminal` remains an active NodeAction until `step` passes
   its completion checks. Closing the last active occurrence completes the
   overall execution. A completed run has an empty active collection.

Both nodes and edges have fresh occurrence IDs and tokens. Revisiting a Type
does not restore a prior token. Failed/incomplete gates retain the active
occurrence and token and record the attempt. Invalid graph/token operations
fail before writes. Input can change only `data`, not execution control fields.
<!-- tarav.breadcrumb 7ed1d3505df6 -->

`initial` is a nonempty tuple and may open multiple occurrences, including
repeated Types. Moving one preserves the other occurrences and their tokens.
This supplies an active collection without a fork/join API. Node/edge prompts
and basic typed Closings use the existing Actions registry; the root execution
is an Action there too. There is no separate current-State object or field.
<!-- tarav.breadcrumb 5d06c9a6e3fb -->

## Project and CLI

`project.programs` selects registered Program Types owned by the Project's
source paths. Register a concrete Program through its trusted harness, using
`get_runtime().records.register(YourProgram)` during module initialization.
Program commands select a registered name or Type UUID, never a Python file
or import path. The Program's graph role Types are registered automatically.

```sh
tarav program list --project .
tarav program start --project . --program MyProject.Program
# Each entry in the returned active array has its own token.
tarav program choose --project . --token NODE_TOKEN --action MyProject.Rewrite
tarav program status --project . --token EDGE_TOKEN
tarav program step --project . --token EDGE_TOKEN
tarav status --project . --program-token NEXT_NODE_TOKEN
tarav program resume --project . --run RUN_UUID
tarav program show --project . --run RUN_UUID
tarav program recover --project . --run RUN_UUID
```

Output is JSON. `start` and `step` accept `--data FILE`, a JSON object.
Exit 1 means selected checks blocked a move or status found incoherence;
exit 2 reports invalid input or a runtime error. Frames contain `active`,
including each occurrence's identity, Type, role, token, Action Record and
available connections. `list` omits tokens; `resume` retrieves the current
frame and `show` reads retained history. A completed run has no current tokens.

`tarav status --program-token` adds the selected occurrence's status checks to
normal Project status. Findings open an ActionIncoherent POI-resolution Action;
incomplete checks preserve previous findings. An unselected active occurrence
keeps its own status, including another occurrence in the same Program run.
Normal status can retire a closed occurrence's warning from recorded closure
facts, even after terminal completion consumed its last token. It does not
evaluate another active occurrence without its token.

## Storage and limits

ProgramRun is authoritative in the external Programs Record Registry partition.
It stores active occurrences, JSON data, history and ActionRun snapshots. Those
snapshots project into the Actions partition. A Program lock serializes token
consumption. Independent Git partitions are not an atomic transaction: explicit
`recover(run_id)` replays Action projections after interruption, without issuing
tokens, changing history or rerunning checks. Reads do not initialize or repair.

Runs use the current trusted class code. A removed Action or connection fails
explicitly rather than being guessed. No code snapshot, external script loader,
legacy alias or automatic stored-run migration is provided. The previous State
schema is rejected by the new strict ProgramRun interface. Tokens are local
execution coordinates; reading the external registry is not an exclusive
capability restricted to the current agent.
