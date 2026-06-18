---
name: agentos-chatlas-retention-audit
description: Audit Chatlas raw retention for a provider by comparing previous audit reports, current provider-home artifacts, and current Chatlas archive policy. USE WHEN deciding what raw provider data Chatlas should retain, keep for future analysis, track as telemetry, or exclude. Called like a terminal command — `--provider <name>`.
---

# Chatlas Retention Audit

Evaluate whether Chatlas is retaining the right provider-native artifacts for long-term transcript fidelity, behavioral analysis, and future study.

This is a `Batchy.Skill` — called like a terminal command. Load `agentos-batchy-skills` for the full convention.

- `-h` / `--help` prints the help into the chat instead of running (`Batchy.Skill.Help`).
- a bare provider name resolves to `--provider`.

## Skill.Arg.Section

### Skill.Arg:Provider
- the provider whose Chatlas raw retention to audit
- required: true
- help: "which provider's retention to audit"
- examples: --provider "claude-code"

Chatlas as a system has two stacked contracts:

- raw archive: preserved provider-native artifacts within an explicit archive scope
- normalization layer: canonical session and transcript derivations built from that archive

This skill audits only the raw archive contract.

Use this skill to produce or refresh a raw-retention audit report. Do not silently edit Chatlas policy unless the user explicitly asks for implementation after the audit.

## Retention Tiers

Classify retained evidence with these tiers:

- Tier 1: transcript fidelity
  - 100% user input on chat
  - 100% user-visible assistant output
  - visible session boundaries
  - user-visible portions of tool interaction
- Tier 2: behavioral analysis
  - reasoning traces when available
  - tool calls and tool results
  - state changes
  - checkpoints, plans, and other model-workflow artifacts
- Tier 3: telemetry
  - usage snapshots
  - account limits
  - quota or rate-limit evidence
  - other metrics useful for later usage study

## Decision Model

For each artifact family, make two decisions:

- `retention_tiers`: one or more of `tier1`, `tier2`, `tier3`
- `raw_decision`: one of:
  - `retain_raw_required`
  - `retain_raw_optional_future`
  - `telemetry_outside_session`
  - `exclude`

This skill answers one question only:

- should Chatlas archive this native artifact family as part of its raw corpus

## Inputs

- provider name
- optional instance name
- optional provider home override
- optional scope refinement such as one folder family or one open question
- optional prior report path, though the default is to auto-discover the latest matching report

If the user does not specify a provider, stop and ask which provider should be audited.

## Trigger Boundary

Use this skill when the task is to:

- audit what Chatlas should keep from a provider home
- compare current provider on-disk reality against Chatlas raw policy
- revisit an older retention decision after provider drift
- produce a durable audit report under `notes/reports`

Do not use this skill for:

- normal session lookup or transcript export through Chatlas
- live provider debugging that is unrelated to retention policy
- direct code implementation unless the user explicitly asks to apply audit conclusions

## Audit Sources

Use a focused evidence set:

- previous reports under `notes/reports/agentos-chatlas-retention-audit/`
- current raw archive code in:
  - `src/agentos/chat/providers.py`
  - `src/agentos/chatlas/raw.py`
  - relevant tests such as `tests/test_chatlas_commands.py`
- live provider evidence from:
  - `agentos chat debug list`
  - `agentos chat debug find`
  - `agentos chat debug extract`
  - direct provider-home inspection with shell tools such as `find`, `du`, and `rg`
- Chatlas dataset confirmation when useful:
  - `agentos chatlas update`
  - `agentos chatlas query`
  - `agentos chatlas views inline`

Prefer a small, explicit evidence set. The goal is not exhaustive crawling. The goal is enough evidence to defend the retention recommendation.

## Workflow

### 1. Fix the audit scope

- Resolve `provider`, optional `instance`, and effective `provider_home`.
- Restate the audit target briefly before deep inspection.
- If the user gave a narrow concern, keep the audit centered there and only expand when needed to make the recommendation coherent.

### 2. Load previous reports first

- Look in `notes/reports/agentos-chatlas-retention-audit/`.
- Select the most recent prior report with matching `provider` and matching `provider_home`.
- When `instance` is present, prefer a report with the same `instance`.
- If there is no match, treat the audit as a first baseline.
- Extract prior conclusions, open risks, suggested changes, and unresolved artifact families.

Old reports are evidence, not truth. Reuse them to avoid re-discovering the same issues, but revalidate conclusions against current code and provider data.

### 3. Inspect current Chatlas raw implementation

- Identify current raw archive scope:
  - provider home mapping
  - default includes
  - default excludes
  - traversal behavior
- Note any tests that defend the current behavior and any obvious coverage gaps.

### 4. Inspect current provider-home reality

- Identify the main artifact families rather than listing every file.
- For each family, estimate:
  - representative paths
  - rough file count
  - rough size or storage footprint when useful
  - whether it looks user-visible, behavioral, telemetry, secret, runtime, or cache-like
- Look for adjacent telemetry or account-usage artifacts even if they sit outside the main session subtree.
- Explicitly call out secrets, auth material, packages, editor residue, runtime locks, and copied workspace state when present.

### 5. Classify artifact families

For each meaningful family:

- assign retention tiers
- assign `raw_decision`
- explain why the family is necessary, optional, out-of-scope telemetry, or safe to exclude

Preserve anything necessary to avoid losing:

- user intent
- user-visible transcript content
- reasoning traces that matter for later evaluation
- tool invocation and result evidence
- durable usage or account-limit telemetry

Be conservative with exclusions when transcript fidelity or future raw re-analysis would be harmed.

### 6. Compare evidence against raw archive policy

- Identify under-retention:
  - required families not currently archived
- Identify over-retention:
  - high-volume families that add noise without improving transcript fidelity or future analysis
- Identify telemetry gaps:
  - useful usage data that should be tracked outside the session archive scope

### 7. Write a new report

- Never overwrite old audit reports.
- Write a new file at:
  - `notes/reports/agentos-chatlas-retention-audit/report-<YYYYMMDDTHHMMSSZ>.md`
- Use the stable report contract from `assets/report-template.md`.
- Keep the full `Current recommendation` section fully restated on every audit.
- Keep the delta sections focused on what changed since the baseline report.

### 8. Summarize for the user

Report the highest-signal outcome:

- what should be retained
- what should be excluded
- what sits in telemetry outside session scope
- what changed from the previous audit

If the user wants action, treat the report as the decision basis for a follow-up implementation step.

## Report Contract

Store reports at:

- `notes/reports/agentos-chatlas-retention-audit/report-<YYYYMMDDTHHMMSSZ>.md`

Keep target identity in frontmatter, not in the directory structure.

Required frontmatter:

```yaml
---
skill: agentos-chatlas-retention-audit
audited_at: 2026-04-20T15:04:05Z
provider: copilot
instance:
provider_home: /Users/pereiro/.copilot
baseline_report:
status: draft
---
```

Required top-level sections:

- `Audit scope`
- `Evidence reviewed`
- `Current recommendation`
- `Artifact family findings`
- `New since last audit`
- `Still unresolved`
- `Superseded prior conclusions`
- `Suggested retention changes`
- `Telemetry outside session scope`

Within `Artifact family findings`, create one subsection per family using the same field names each time:

- `sample_paths`
- `count_estimate`
- `size_estimate`
- `retention_tiers`
- `raw_decision`
- `delta_vs_previous`
- `rationale`

## Constraints

- Do not default to mirroring an entire provider home without argument.
- Do not drift into normalization design or extractor behavior.
- Do not treat old reports as authoritative without revalidation.
- Do not archive secrets, auth state, package payloads, editor/process residue, or other runtime junk unless the user explicitly overrides that rule.
- Do not optimize only for storage minimization. Favor transcript fidelity and future reconstructability first.
- Do not turn speculative ideas into implementation work unless the user asks to apply the audit conclusions.

## Response Shape

While auditing, communicate briefly:

- current audit target
- evidence being checked
- important drift or risk discovered

At the end, provide:

- report path
- top retention decisions
- main changes since the previous report
- whether raw-policy changes are recommended next
