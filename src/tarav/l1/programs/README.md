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
