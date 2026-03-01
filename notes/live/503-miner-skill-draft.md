---
name: miner-base
description: Guide for building miner skills — skills that scan sources, extract findings, and write them to a tape. Describes the workflow, finding schema, and the sections a concrete miner skill must include.
---

# Miner Base

A miner is a skill that scans sources for findings and writes them to a tape.

This is a guide for building miner skills, not a referenceable base. Each concrete miner skill is self-contained — it embeds everything it needs from this guide and selects the workflow alternatives that apply to its domain.

## What Is a Miner

- A miner's job is to **find** things. Not to dedup, not to orchestrate, not to log.
- The cognitive work (deciding what is a finding) belongs to the agent.
- The deterministic work (querying tapes, writing entries) belongs to `agentcli`.
- Reading sources uses the agent's built-in tools (Read, Glob, Grep in Claude Code/Codex) — not custom CLI commands.

## Entry Type Convention

A miner produces entries of a single type: `{name}.miner.finding`.

Each concrete miner chooses its name prefix. Examples:
- `todo.miner.finding`
- `debt.miner.finding`
- `convention.miner.finding`

## Sections a Miner Skill Must Include

A concrete miner skill is a self-contained SKILL.md. It must include these sections (not necessarily in this order, not necessarily all of them):

1. **What it mines** — domain description and what counts as a finding
2. **How to read sources** — which agent tools to use, what file patterns to target, exclude patterns, chunking strategy for large files

## Miner Workflow

The general workflow. A concrete miner selects and orders from these steps.

### Step 1: Resolve scan targets

Determine which files/resources to scan. At miner construction, the builder picks one (or more) scanning modes. Each mode defines *where targets come from*.

#### Mode: `discovery`

The agent explores freely using its built-in tools (Glob, Grep, Read). No AgentOS capability needed — the agent decides what to scan based on the miner's scan instructions.

Best for: exploratory miners, broad sweeps, first-run scenarios.

```
Agent uses Glob/Grep/Read to find and select targets autonomously.
No agentcli command involved.
```

**AgentOS dependency:** none.

#### Mode: `prompted`

Targets are written directly in the skill definition or provided by the user at invocation time. The skill includes explicit file patterns, directories, or file lists.

Best for: focused miners that always scan the same areas, user-driven ad-hoc scans.

```
Skill definition includes target patterns, e.g.:
  scan: src/**/*.py, tests/**/*.py
  exclude: **/vendor/**, **/__pycache__/**
```

**AgentOS dependency:** none.

#### Mode: `pipeline`

Targets come from an AgentOS pipeline — a CLI command or external process produces a file (e.g. JSONL) listing what to scan. The miner reads this file as input.

Best for: orchestrated workflows where a prior step curates targets.

```sh
# Example: a prior step produces a target list
agentcli targets resolve --root {root} --include "src/**/*.py" --exclude "**/vendor/**" > /tmp/targets.jsonl

# Miner reads the target list
# (agent reads /tmp/targets.jsonl and scans each entry)
```

**AgentOS dependency:** target resolution CLI (not yet implemented).

#### Mode: `tape-sourced`

Targets come from entries in another tape. A previous miner or agent wrote entries identifying files/resources of interest; this miner scans those.

Best for: chained miners, composable workflows, narrowing down from a broad scan.

```sh
# Load targets from another tape's entries
agentcli tape list --tape {source_tape} --entry-type {source_type} --last N
# Agent extracts file paths from the returned entries and scans them
```

**AgentOS dependency:** `tape list` (implemented). May need field projection for extracting specific cargo fields (not yet implemented).

#### Mode: `git-diff`

Targets are files changed in git — by diff against a branch, a commit range, or uncommitted changes. Only changed files are scanned.

Best for: incremental mining, CI-triggered scans, change-aware miners.

```sh
# Example: list files changed vs main branch
agentcli git diff-files --base main

# Example: list files changed in last N commits
agentcli git diff-files --commits N

# Agent scans only the returned files
```
