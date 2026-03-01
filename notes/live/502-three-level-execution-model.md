# The Three-Level Execution Model

A clean way to design flexible agentic systems is to separate **what the task is** from **how it is executed**.  
This leads to a three-level model: **Task Spec → Executors → Orchestrator**.

---

## 1) Task Spec (Runtime-Agnostic Definition)

The Task Spec defines the problem independently of execution strategy.

It contains:

- **Objective** — What must be achieved.
- **Inputs / Outputs** — Explicit contract.
- **Constraints** — What must not be violated.
- **Definition of Done** — Clear completion criteria.
- **Acceptance Tests** — How correctness is verified.
- **Known Edge Cases** — Important boundary conditions.

Properties:

- Execution-mode neutral.
- Deterministic in meaning.
- Stable across environments.
- Reusable by different executors.

The Task Spec is the semantic core of the system.

---

## 2) Executors (Runtime-Specific Implementations)

Executors are concrete strategies that act on a Task Spec.

### A) Skill Executor (Inline Mode)

- Runs inside the caller’s context.
- Shares memory, state, and active objective.
- Minimal overhead.
- Fast and deterministic.
- Suitable for bounded or repetitive tasks.

Strengths:
- Low latency.
- Simple mental model.
- Good for procedural workflows.

Limitations:
- No isolation.
- Context contamination possible.
- Limited parallelism.

---

### B) Agent Executor (Isolated Mode)

- Spawns a separate reasoning context.
- May have its own role, constraints, and sub-objectives.
- Returns a structured artifact (plan, patch, report).

Strengths:
- Isolation from caller context.
- Supports specialization.
- Enables parallel reasoning.
- Better for complex, multi-step tasks.

Limitations:
- Higher overhead.
- Requires integration step.

---

## 3) Orchestrator (Execution Strategy Layer)

The Orchestrator decides *how* to execute a Task Spec.

Responsibilities:

- Select execution mode (Skill vs Agent).
- Apply escalation rules (e.g., inline → agent if complexity grows).
- Handle retries and fallback strategies.
- Merge agent output back into the main workflow.

Decision heuristics may include:

- Task complexity.
- Number of affected files.
- Risk level.
- Required reasoning depth.
- Need for isolation or role specialization.

---

# Core Principle

**Separate semantics from execution.**

- The Task Spec defines meaning.
- Executors define strategy.
- The Orchestrator defines policy.

This separation allows:

- Adaptive execution models.
- Parallelization.
- Increased reliability.
- Clean cognitive boundaries.
- System scalability over time.

In mature agentic systems, the Task Spec remains stable,
while execution strategies evolve.