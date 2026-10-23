# Programs

A Program is a trusted Tarav class defined in a Project's Python code. It
declares States, StateActions and connections. The reusable runner owns tokens,
checked advancement, persistence and recovery. There is no Program script loader.
<!-- tarav.breadcrumb b0df5160af0b -->

`State` is a CheckProvider bound to a ProgramRun. Its `Checks.suite()` describes
conditions on the product. A `StateAction` names its destination through `State`,
supplies a prompt and optional `prerequisites(run)`, and reuses that destination's
checks. StateAction is a distinct Action kind; the operator StepRunner cannot
mark it done. A Program command closes it only after its checks pass.
<!-- tarav.breadcrumb b019ad23ed0d -->
<!-- tarav.breadcrumb 37f99848057d -->

The Program's `graph` is a tuple of `Transition(source_state, action_type)`
declarations. `initial` names the initial State; `terminal` lists terminal States.
Python loops may build the graph. Override `available(run)` to filter the base
method's outgoing connections from persisted `run.typed.data`. This hook cannot
invent an undeclared edge. Availability gates selection; Action prerequisites
and destination checks gate completion. There is no suspended Python stack.

## Python lifecycle

Register a concrete Program Type in the Project's trusted runtime like its other
Record Types. Each concrete State, Action and Program declares `class_entity()`.
The runtime registers graph-declared Action Types. `ProgramClass.runner()` opens
the library runner without provisioning storage. Its operations are:

1. `start(project={"id": ..., "name": ..., "root": ABSOLUTE_PATH}, data={...})`
   through `ProgramClass.start`, or construct the runner with that descriptor
   and call `start(data={...})`. Initial conditions must pass before storage is
   created and the initial arrival token is issued. The default State has no
   additional conditions.
2. `choose(current_token, action_type_uuid_or_name)` opens one available
   StateAction. Its prompt and parent Program run are visible in the returned
   frame and ordinary Action registry.
3. Work on the product, then `step(current_token, data={...})`. Data is explicit
   JSON program input; it cannot overwrite control fields. Failed/incomplete
   checks retain the StateAction and token. Successful checks close it, record
   arrival and issue a new token. A cycle receives a new token too.
4. `status(current_token)` reruns the same current State's conditions. It reports
   coherence without rotating tokens or writing run state. Later product drift
   is visible. A token selects a State to maintain, not permanent proof of it.
5. Terminal arrival closes the parent Program execution. `load(run_id)` retains
   data, action snapshots and history. `frame(loaded_run)` exposes its current
   token for explicit resumption; old tokens are rejected before writes.
<!-- tarav.breadcrumb 5fd6dbc50ba1 -->
<!-- tarav.breadcrumb e0b28acd7503 -->

ProgramRun records live in the Programs workflow's standard Record Registry
partition, outside the Project. Program-run state is authoritative; retained
ActionRun snapshots project into the existing Actions partition, including an
overall ProgramExecutionAction. Both parent and children carry the Project owner.
One lock serializes token use. Independent Git repositories are not one atomic
transaction: if projection fails after a run save, explicitly `recover(run_id)`.
It replays Action snapshots without advancing, issuing tokens or rerunning checks.
Read operations never repair or initialize storage. Tokens do not guarantee
exclusive access to other agents able to read the external registry.

Runs use the Project's current trusted class code. Code changes can change the
conditions checked; a removed current State is reported rather than guessed.
No per-run code snapshot or legacy Iterante dependency is introduced.

## Project commands

`project.programs` selects registered Program classes whose Python source belongs
to that Project. Import and register a concrete Program through its existing
trusted harness, using `get_runtime().records.register(YourProgram)` during that
module's initialization. A Program identity is a Type UUID or registered name;
commands do not accept Python files or import paths. Each graph-declared Action
is registered when its Program is prepared.
<!-- tarav.breadcrumb 9dd1b48ff90a -->

```sh
tarav program list --project .
tarav program start --project . --program MyProject.Program
# Use the returned token and one of the returned available Action identities.
tarav program choose --project . --token TOKEN --action MyProject.Write
# Work on the product, then attempt arrival.
tarav program step --project . --token TOKEN
tarav program status --project . --token NEW_TOKEN
tarav status --project . --program-token NEW_TOKEN
tarav program resume --project . --run RUN_UUID
tarav program show --project . --run RUN_UUID
tarav program recover --project . --run RUN_UUID
```

Program commands return JSON. `start` and `step` optionally accept `--data FILE`,
a JSON object merged into program data; control fields stay outside that object.
Exit 1 means a step did not advance or Program status found incoherence; exit 2
means invalid input or a runtime error. `resume` retrieves the current token
without changing it. `list` omits tokens. `show` includes the retained run and
history. These are explicit local operational reads, not token access controls.

`tarav status --program-token` runs normal Project checks plus the selected
State's conditions and opens a POI-resolution action on completed, failing
checks. Incomplete checks preserve earlier findings. Ordinary status without
the token does not assert coherence or close that run's drift action. Another
run's token cannot close it either. Restoration followed by contextual status
closes the drift action; Program state and token stay unchanged.
<!-- tarav.breadcrumb 7d5a7e8dac5a -->
<!-- tarav.breadcrumb abec83b6d84c -->

Minimal graph shape, after defining concrete State and StateAction classes with
their own `class_entity()` identities:

```python
class MyProgram(TaravProgram):
    initial = Ready
    terminal = (Done,)
    graph = (
        Transition(Ready, Write),   # Write.State is Written
        Transition(Written, Reset), # Reset.State is Ready: a cycle
        Transition(Written, Finish),# Finish.State is Done
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip("72ee47ce-673c-47c1-9ec1-a6e216ee3efa"),
                          name="MyProject.Program", workflow=PROGRAMS_WORKFLOW_SHIP)
```

State conditions describe the product at arrival and afterward. Put requirements
that apply only to the transition in `StateAction.prerequisites(run)`. During a
step these see the source context; destination conditions see the proposed State
and arrival number. The runner performs no product edits itself.
