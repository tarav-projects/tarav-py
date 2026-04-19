---
name: agentos-skills
description: Master router skill for discovering and loading skills through the public `agentos skills` CLI only.
---

# agentos-skills

Use this skill when the task requires discovering, selecting, or loading another skill, or when the user asks what skills are available through `agentos`.

This skill exists as a compatibility hook for traditional skill loaders. It teaches the public skill-routing protocol and should usually trigger once per session.

## Required Protocol

1. Run `agentos skills list` to inspect the routed skill catalog for the current caller context.
2. If acting on another project, pass `--project <root>` to the command.
3. If the routed catalog is non-empty, run `agentos skills import` once for that caller context to materialize the local skill depot.
4. Choose one skill from that routed catalog.
5. Run `agentos skills path <name>` to resolve the local routed loadable path for that skill.
6. Read the target skill from the returned path and follow it.

## Rules

- Treat `agentos skills` as the only public discovery surface for skills.
- `agentos skills import` is the only public sync step that materializes routed skills into the local depot.
- Do not inspect other skill folders directly for discovery.
- Do not assume hidden registries, depots, or imports are available.
- If `agentos skills list` returns no skills, treat that result as authoritative.
- Do not retry discovery through other folders when the routed catalog is empty.

## Trigger Guidance

- Trigger when a skill needs to be found or loaded.
- Trigger when the user asks about available skills or skill routing.
- Do not trigger for casual discussion that mentions skills without needing discovery or loading.
