# Split agent config entry decoding - impl-req

## Impl.Abstract

- **scope:** split the 1,210-line agent configuration module by extracting config-entry decoding and validation while preserving `agentos.agent.config` as the stable API
- **status:** implemented and fully verified
- **source:** third theme of `hugentics-codebase-cleaner --AUTO --codebase agentos-py`, focused on long files
- **target project:** `agentos-py`

## Impl.Index

### Current.State

- `src/agentos/agent/config.py` combines provider specifications, config/profile document orchestration, selection/default construction, and a 645-line config-entry decoding/validation layer
- the decoding layer begins at `agent_config_from_config_entry` and owns provider policy, account contexts, home/path normalization, ping/env parsing, JSON helpers, and explicit anchor construction
- upper-level orchestration already calls the decoding layer through named functions, providing a narrow existing dependency seam
- 44 focused profile, preflight, session, and testing tests pass before extraction

### Scope.Boundary

- keep `agentos.agent.config` as the stable public module with the exact existing `__all__`
- keep provider specs, config/profile loading, selection, default configs, and home overrides in `config.py`
- move shared provider/config models and canonical chat-provider specs to `_config_models.py`
- move config-entry decoding and its validation/normalization helpers to `_config_entry.py`
- preserve error messages, default values, policy validation, path expansion, atomic writes, and returned dataclass values
- preserve public and private names used by the remaining orchestration module
- update `AGENTS.md` only enough to document the module ownership boundary
- do not alter configuration schemas, provider defaults, compatibility policy, CLI behavior, or tests

## Execution.Plan

### Slice 1 - Entry decoder extraction

- extract shared provider/config dataclasses and canonical chat-provider specs into `_config_models.py`
- extract `agent_config_from_config_entry`, provider validation, provider config application, account/home/ping/env/path parsing, JSON helpers, and anchor construction into `_config_entry.py`
- observable: the extracted module imports and focused configuration tests pass
- status: completed

### Slice 2 - Stable config facade

- re-export the decoder’s public functions and retain private JSON/path helpers needed by profile orchestration
- preserve the exact ordered `__all__` and all previously defined public names
- observable: import and API parity audits pass against checkpoint
- status: completed

### Slice 3 - Documentation and verification

- document config ownership, run focused tests, full Ruff, focused formatting, and the complete suite
- observable: both implementation modules are cohesive and materially smaller than the original, with no behavioral regression
- status: completed

## Risks And Deviation Triggers

- shared provider/config definitions must remain dependency-neutral so both orchestration and decoding import normally without circular initialization
- preserve exact `CliError` messages because they are part of configuration diagnostics
- stop rather than redesign provider schemas, defaults, or profile persistence
- do not broaden into session discovery, account runtime, or provider implementation changes

## Acceptance Signals

- `config.py`, `_config_models.py`, and `_config_entry.py` are each materially smaller than the original and own distinct concerns
- all originally defined public symbols and the exact `__all__` remain available through `agentos.agent.config`
- full Ruff and focused formatting checks pass
- all 44 focused tests pass
- the full test suite passes
- the diff contains only the planned config split, required guidance, and this execution record

## Impl.Log

- 2026-07-29: selected `agent/config.py` over larger routing/session candidates because its decoding seam has materially stronger direct regression coverage
- 2026-07-29: focused baseline passed with 44 tests
- 2026-07-29: mandatory pre-execution checkpoint created at `a848ed4`
- 2026-07-29: an initial late-import composition passed the size goal but failed Ruff's import-order gate; shared definitions were extracted instead of suppressing the architectural issue
- 2026-07-29: extracted shared models/specs and config-entry decoding while retaining `agentos.agent.config` as the stable orchestration/API module
- 2026-07-29: focused Ruff and all 44 focused tests passed after extraction
- 2026-07-29: API audit preserved all 33 originally defined public symbols and the exact ordered 37-name `__all__`
- 2026-07-29: full Ruff, focused formatting, all 44 focused tests, and all 551 repository tests passed
