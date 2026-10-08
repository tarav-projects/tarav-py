# 878 — Settings capability — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive (the User is working elsewhere; ordinary ambiguities are resolved as recorded agent choices). Status: ready. Phase: Develop.

Add a small Settings capability to `tarav-py`. A Type that needs configuration extends one provider class and gets a bound `.settings` namespace on its objects. The Type declares a template of its expected keys for its own partition, values can be given at construction or written afterwards, the standard path checks keys and value types, and the settings appear in the object's context. One existing object, the agents file, adopts it as a worked example.

Non-goals: POI tracking; a notification log; migrating Tarav's configuration files; renaming "finding"; any locking mechanism; any rule about how a workflow uses the values it reads; built-in layering of sources.

## Design narrative

### What the User decided

A type may extend many capability classes, and each capability's controls could then be custom and messy. One shared, namespaced place for them, comparable to Visual Studio Code's dotted settings keys, makes Tarav more predictable and more extensible.
<!-- tarav.breadcrumb ea6da3185aa7cb75dce7bcd217c10e3f24e01de831fd3154fa9ddd9e5115747a -->

Settings are for configuration and not for object data, which is a typical failure point. Each type that uses them declares a template of expected keys in the spirit of the record system, and the type controls it. The rules stay as simple as possible: every type has its own partition, and inheriting a parent's settings is explicit, like including the parent's checks. The system is type-internal. A capability may also have no settings.
<!-- tarav.breadcrumb 71da207d2e9f674147ae27326949a260de6cec5c8adac5fef1a782616fbf3289 -->

Instances receive values through two standard entry points: a settings object passed at construction, and a write operation on a settings namespace afterwards. They are conventions; a type may do otherwise. The standard path gives key checking for free and connects the settings to the object's context. How a value is used is not regulated, and locking is the business of the workflow that reads the setting.
<!-- tarav.breadcrumb b0db33633368b372690b397dfb4da3d72504f5d8db27d6fd1d832a352c8cc602 -->

Object settings and files are one workflow: settings may be loaded from a file, and how defaults are created and settings loaded stays flexible.
<!-- tarav.breadcrumb d1bd7ed0c9b6542a90342546dda275d535150f6bb96cf10346845a55387f43ce -->

Data and settings are different. Loading a record does not put its data in `.settings`. A class may represent settings as its data and still have `.settings` of its own that configure how it behaves.
<!-- tarav.breadcrumb 73ad51657cf67ae54204cf1730c68edb3a9841a05c7a481ecd8544cdd666380f -->

Settings is itself a capability. An object has `.settings` only when something it extends needs it.
<!-- tarav.breadcrumb 94487046a5285846b9522860ab1f140863bed4fd771fead913fcd2ff184222c6 -->

The User asked for this to be captured and implemented.
<!-- tarav.breadcrumb 2af83667a5586883ca74f6c98de44518a8997470494fe4786747b6ac3b9ffbb1 -->

The Wiki note `tarav-md/notes/wiki/settings-capability.md` records the convention in full; `capabilities-by-subtyping.md` records the principle behind it.

### Current behavior (inspected 2026-10-08)

- Bound namespaces are `NamespaceBase` views in `src/tarav/l0/kernel/namespaces.py`; a host selects them through a nested class and a property, as `CheckProvider.Checks` and `.checks` do in `src/tarav/l1/checks/__init__.py`. `check_namespace_composition` rejects a host that drops a base's namespace.
- `BlessablePOI` (`l1/blessings/capability.py`) is the existing example of a capability expressed by extending a class.
- Record Types declare their shape as a nested pydantic `RecordInterface` and an example in a `Records` namespace (`l0/kernel/records.py`).
- Context views are built in `l1/context/__init__.py`: a class view calls `class_context`, an object view calls `obj_context`, then the runtime's contributors. `TaravObject` defines `obj_context` itself, so a mixin listed after it cannot add object entries through that hook. The runtime's `context()` (`l3/runtime.py`) is the single opener used by `.context()` and by `tarav context`.
- `AgentsMd.__init__` (`l1/project/agents.py`) reads the marker's `agents` entry and validates four values by hand: `main`, `aliases`, and the two switches `tarav_system_prompt` and `project_system_prompt`.
- Small workflows declare a `TaravWorkflow` with its own Ship and are listed in `create_runtime()`.

### Design (agent proposal under the decisions above)

**Place.** A new workflow package `tarav.l1.settings`, with `SettingsWorkflow`, beside `l1/checks`. It imports only the kernel.

**Declaring.** A Type extends `SettingsProvider` and declares a nested pydantic model named `SettingsInterface`. Each field is one setting: its name is the key, its annotation the value type, its default the default, and its `description` the one-line description. Every field must have a default; a declaration that breaks this fails when the class is created. This mirrors `RecordInterface`.

**Partitions.** The partition of a Type is named by its Tarav Type name. An object has the partition its own class declares, plus the partitions of the classes its own class lists in `settings_include`. Both are read from the class itself and are not inherited through Python, so including a parent's settings is always an explicit line. A class that declares neither has `.settings` with no partitions.

**Giving values.** `SettingsValues` is a small record Type holding values by partition. `SettingsValues.of(SomeType, key=value)` builds one, and `SettingsValues.from_path(path=...)` loads one through the record registry. The construction convention is an optional `settings` argument that the type passes to `self.settings.apply(values=..., origin="construction")`.

**Reading and writing.** `obj.settings.get("key", partition=SomeType)`, `obj.settings.set("key", value=..., partition=SomeType)`, `obj.settings.apply(values=..., origin=...)`, `obj.settings.origin("key", partition=SomeType)` and `obj.settings.describe()`. The partition may be omitted when the key is declared in exactly one partition.

**Checking.** The standard path raises `SettingsError`, a `ValueError`, for an unknown partition, an unknown key, an ambiguous key, or a value that does not fit the declared type (validated strictly by pydantic). Raising was chosen because comparable mistakes nearby raise: bad marker values in `AgentsMd`, and declaration errors in the kernel. These are programming or configuration errors at the point of the call, not states to be surfaced later.

**Origins.** Each value records where it came from: `default`, `construction`, `runtime`, or `file:<path>`. This is the agent proposal the User has not confirmed; it is small and can be removed.

**Context.** The runtime adds one contributor to its context opener: an object that is a `SettingsProvider` gains a `settings` entry opening a record with every partition, key, current value, origin, type, default and description. A provider Type's class view gains a `settings-template` entry through the ordinary `class_context` hook.

**Reusable contract tests.** `tarav.l1.settings.testing.SettingsContractTests`, in the style of `l0/explorer_testing.py`: a provider's test class supplies an object and inherits checks that defaults are readable, a write round-trips, unknown keys are rejected, and `describe()` covers every declared key.

**Worked consumer.** `AgentsMd` extends `SettingsProvider` and declares the two prompt switches as its partition. Their values are read from the same `agents` marker entry as before and applied with origin `file:<marker>`. The main file and the aliases remain ordinary data. Behaviour, the marker format and the existing tests are unchanged. The User has not confirmed this classification of the marker entry; the change is confined to `AgentsMd.__init__` and two properties so it is easy to back out. If it does not fit cleanly it is skipped and logged.

### Open questions

None blocking. For the User to confirm afterwards: the origin record, the `AgentsMd` classification, and the names `SettingsInterface` and `settings_include`.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `settings-capability.md`, `capabilities-by-subtyping.md`, `context-graph.md`, `record-framework.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. **Capability core.** `l1/settings`: workflow, `SettingsProvider`, the `Settings` namespace, `SettingsValues`, `SettingsError`, declaration checks. Tests with a test-only provider: defaults, set and get, apply at construction, origins, explicit inclusion, a class with no partitions, every rejection.
2. **File source.** `SettingsValues.from_path` through the record registry; test loading and applying a JSON file.
3. **Context.** The runtime contributor and `class_context`; register the workflow and record Types in `create_runtime()`. Test both entries.
4. **Contract tests.** `l1/settings/testing.py`, used by the test-only provider's test class.
5. **Worked consumer.** `AgentsMd`; the existing agents tests must pass unchanged, plus one test that the switches are settings with a file origin.
6. **Guidance and closure.** `ARCHITECTURE.md`, `AGENTS.md` through its Skillware source. Full suite, Ruff, the isolated commit tree, CLI reinstall and root harness sync, the root Project check compared with the previous totals, and a real script through `tarav run --project --`. Inlined Capture, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): kernel namespaces and records, `l1/checks`, `l1/blessings/capability.py`, `l1/context`, `l1/context/query.py`, `l3/runtime.py`, `l3/cli/cli.py`, `l1/project/agents.py`, `l0/explorer_testing.py`. `l3/runtime.py`, `tests/test_architecture.py`, `ARCHITECTURE.md` and `pyproject.toml` carry unrelated uncommitted edits; this request's hunks in them are staged in isolation.
- Wiki capture of the convention preceded this note: `tarav-md` start checkpoint `815f9d7fd6284ab8782c2af6c4dd0c8acb967308`, completion commit `e837731a12726a533c7c903978cf8dcbb6d82c68` (`settings-capability.md` 9 Breadcrumbs, audit clean).
