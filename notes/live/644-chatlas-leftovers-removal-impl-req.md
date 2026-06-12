# Agentos-Py: Chatlas Migration Leftovers Removal + Micro-Fixes - impl-req

## Impl.Abstract

- **scope:** remove dead chatlas-era code from `agentos-py`: (1) the seven unreferenced per-provider `chatlas.py` constant modules; (2) the write-only `chatlas_includes`/`chatlas_excludes` plumbing through `agent/primitives.py` and `agent/config.py`; (3) two micro-fixes — make `AgentosProjectHandler.validate()` side effect explicit, add `strict=` to two `zip()` calls in the monitor.
- **status:** implemented (2026-06-12)
- **source:** general legacy/bug scan of agentos-py (2026-06-12), executed as a cleaner turn via `agentos-hugentics-codebase-cleaner`, fully autonomous per user instruction. Background: Chatlas mechanics moved to `agentos-chatlas-py` (root `AGENTS.md` migration note); these are the unswept remains of the supply side.

## Impl.Index

### Dead.Provider.Chatlas.Modules

- `src/agentos/{claude,codex,copilot,gemini,openclaw,opencode,pi}/chatlas.py` export `*_CHATLAS_DEFAULT_INCLUDES`/`*_CHATLAS_DEFAULT_EXCLUDES` constants (codex also has internal `_derived_codex_chatlas_excludes` helpers used only within its own module).
- Hard evidence: zero importers across `agentos-py/src`, `agentos-py/tests`, `agentos-chatlas-py/src`, `agentos-cli/src`, `agentos-canvas-py/src`. No re-exports in any provider `__init__.py`.
- Delete all seven files.

### Write.Only.Chatlas.Config.Plumbing

- `chatlas_includes` / `chatlas_excludes` flow: agent config `includes`/`excludes` keys → `agent/config.py` (~636-637, ~723-729, ~798-799) → `AgentConfig` + the agent-base dataclass in `agent/primitives.py` (~100-101, ~167-168) → `identity_key()` (~137-138), `summary()` payload (~215-218), `agent_base_kwargs_from_config` (~370-371). **No consumer reads them anywhere** (verified across all sibling packages and tests).
- Remove: the two dataclass fields (both dataclasses), the `identity_key()` entries, the `summary()` payload entries, the kwargs entries, and the config parsing (`raw_includes`/`raw_excludes` reads + `_load_optional_string_tuple` calls + constructor args).
- Safety notes (verified): `computed_fingerprint()` does not include these fields — agent fingerprints unchanged. Config loading has no unknown-key strictness, so existing user configs with `includes`/`excludes` keys are silently ignored after removal (correct: they already had no effect). No tests reference the fields.

### Micro.Fixes

- `src/agentos/_core/project.py:98` — `validate()` body is a bare `self.project_json` expression (relies on property's load-and-raise side effect; ruff B018). Replace with an explicit call to the loading path so the intent is readable (e.g. assign or call `load_project_marker` the way the property does — keep the cached-property behavior intact; simplest faithful form: `_ = self.project_json` is NOT acceptable per readability; prefer calling the property via a named local or invoking the same loader the property uses without duplicating logic — executer picks the clearest form that keeps caching semantics).
- `src/agentos/agent/monitor/models.py:404` and `src/agentos/agent/monitor/render.py:421` — `zip()` without `strict=`. models.py pairs frame rows across two frames (row counts may legitimately differ between frames → `strict=False` to preserve current truncation behavior, stated explicitly). render.py zips two RGB triples (always length 3 → `strict=True`).

### Out.Of.Scope

- The 11 `except Exception` defensive probes (sampled; deliberate return-None/False probes).
- The account_status/registry cross-provider parallelism (provider-specific by design).
- Any chatlas-side changes in `agentos-chatlas-py`.
- PLW2901 loop-name redefinitions.

## Execution.Plan

Behavior-preserving deletion + two lint-grade fixes; the regression harness is the existing suite. Baseline (2026-06-12): `uv run pytest -q` → 107 passed, 0 failed.

### Slice 1 — Delete the seven provider chatlas modules

- `git rm` the seven `chatlas.py` files.
- **observable:** suite green (107 passed); `grep -rn "CHATLAS_DEFAULT" src` returns nothing.
- **check:** import smoke: `uv run python -c "import agentos.claude, agentos.codex, agentos.copilot, agentos.gemini, agentos.openclaw, agentos.opencode, agentos.pi"`.
- **status:** done

### Slice 2 — Remove chatlas_includes/excludes plumbing

- Edit `agent/primitives.py` (fields ×2, identity_key, summary, kwargs map) and `agent/config.py` (raw reads, tuple loads, constructor args).
- **observable:** suite green; `grep -rn "chatlas_includes\|chatlas_excludes" src tests` returns nothing.
- **check:** also re-grep sibling packages to confirm still no external references.
- **status:** done

### Slice 3 — Micro-fixes

- `project.py` validate() explicit form; `zip(..., strict=False)` in monitor/models.py with the row-count rationale; `zip(..., strict=True)` in monitor/render.py.
- **observable:** suite green; `uvx ruff check src --select B018,B905` reports nothing for these three sites.
- **status:** done

### Risks And Deviation Triggers

- **Risk:** a dynamic/string-based reference to the deleted modules or fields (importlib, payload key probing). Mitigation: greps above cover string keys; smoke-import all provider packages.
- **Risk (models.py zip):** choosing `strict=True` there would turn a tolerated frame-shape mismatch into a crash — keep `strict=False`.
- **Deviation trigger:** any discovered consumer of the deleted code → hard boundary; abort and surface (cleanup never broadens scope).

### Acceptance Signals

- `uv run pytest -q` → 107 passed.
- Greps and smoke-import checks pass.
- Net deletion in `src/agentos/` (seven files + plumbing lines).

## Impl.Log

- 2026-06-12: executed all three slices in order (fully autonomous run per user instruction; cleanup boundary confirmation waived by the user's "fully autonomously").
  - **Rollback floor:** empty checkpoint commit `e9d5df2` ("chore: checkpoint before hugentics-codebase-cleaner (impl-req 644)").
  - **Decision (open space, Slice 2):** the `Agent` Protocol in `primitives.py` (~394) also declared `chatlas_includes`/`chatlas_excludes` — not listed in the plan's site inventory. Removing protocol attributes is squarely inside the theme (same write-only fields), so removed rather than aborting; recorded here as an inventory gap, not a scope change.
  - **Decision (open space, Slice 3):** `validate()` rewritten as `self._project_json = self.project_json` — explicit assignment through the caching property, avoiding both the bare expression and duplicated loader logic.
  - **Verification:** `uv run pytest -q` → 107 passed (matches baseline). Ruff B018/B905/F clean on the touched sites. Smoke imports of all seven provider packages and the edited modules pass. Greps confirm zero `CHATLAS_DEFAULT` / `chatlas_includes` / `chatlas_excludes` references in src, tests, and sibling packages.
  - Implementation changes left uncommitted for review per executer contract.
