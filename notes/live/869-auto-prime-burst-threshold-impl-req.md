# 869 — Auto-prime burst-threshold simplification — Impl.Req

<!-- tarav.sessions
4d59cf87 = claude-code:d237f00a-2da8-4b96-9b54-a1addd3a5b4e @4d59cf8708efc859c0e9288a51784c98da8592021f8fe020fe298adc78972589
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: Complete. Phase: Develop (Execute).

Make the account monitor's pings work again and reduce the `auto-prime-zero-limits` workflow to one rule: every `interval_sec` (default 600), for each configured target, read the last limits-tracking usage reading; when its burst `used_percent` is below `threshold_percent` (default 5), run the account's configured ping. Change the default Codex ping model from `gpt-5.4-mini` to `gpt-6-luna`.

Non-goals: no new workflow or renamed workflow; no change to limits-tracking refresh or account-rotation; no fix for the separate Codex `workspace routing discovery failed` error; no change to the `pi` ping default; no deletion of the retained `~/.tarav/agent/monitor/auto-prime-events.jsonl` data.

## Design narrative

The User asked to make the monitor's ping work again with a simple workflow, originally framed as an hourly ping for each working account.
<!-- tarav.breadcrumb 9c3485b85adc2cda97e8c61e6b27071f3dacb163c606f274ade512e85de4a7f7 -->

A read-only investigation found that every Codex auto-prime ping has failed since 2026-09-09 (last success 2026-09-08): the default Codex ping model `gpt-5.4-mini` (`src/tarav/l1/agent/_config_models.py`) is rejected with "not supported when using Codex with a ChatGPT account". Failures retried every 10 minutes and flooded `~/.tarav/agent/monitor-log/` and `auto-prime-events.jsonl` (≈72k lines). The current workflow is trigger-driven (`zero_usage`, `near_zero_full_window`, `sliding_reset`, `period_key_churn`), keeps period keys, primed-period memory, a 15-minute verification pass, and a retry cooldown — about 1,175 lines in `monitor/workflows/auto_prime.py`.

The User rejected a new workflow and redirected to simplifying the current one: the frequency is a changeable parameter (10 minutes preferred over 1 hour); each check reads the last usage reading and pings when burst usage is below 5%.
<!-- tarav.breadcrumb 0182cf94852a1ed5082a87530fd68ab6ca2793e8db2b5e2f37afdb3546b3b267 -->

Targets are the accounts the monitor shows, limited to Claude and Codex, but the ping configuration stays explicit so the User can exclude accounts — for instance all monitored Claude/Codex accounts except Claude `om`.
<!-- tarav.breadcrumb a95f1a3a01c6be4f286e9128d66303220a000ef280c16f0175f5c60a6f1b2719 -->
<!-- tarav.breadcrumb 8c32142419b728c27d219564117017e1e2dfa63a6903d8a4a66fb32215ced60c -->
<!-- tarav.breadcrumb 18dbf1d1008df1f0eab80b61ccb37c606aec1ba4d6ffe899bbc20cb16ce95a63 -->

Codex pings should use Luna. All four Codex accounts' model caches list `gpt-6-luna` and `gpt-5.6-luna`; the agent proposed `gpt-6-luna` as the newer one.
<!-- tarav.breadcrumb 56cbad29340fba8b65b2623f35e2cdf537e72d8a8f94ec9ec9913dff757dce25 -->

### Decisions

- Keep the workflow name `auto-prime-zero-limits` and its periodic alarm so existing config and the loop's alarm arming keep working. The name now overstates the rule; renaming is a separate choice.
- Config keys: `targets` (required; providers `codex` and `claude-code` only), `interval_sec` (default 600), `threshold_percent` (default 5). Retire `target_limits`, `triggers`, and `retry_cooldown_sec`; `MonitorWorkflowConfig` drops `target_limit_ids`, `triggers`, `retry_cooldown_sec` and gains `threshold_percent`.
- The reading is the limits-tracking target state for the same target key. Skip a target when that state is missing, not `ok`, or has no `burst` limit with an integer `used_percent`. Both providers already map their short window to `burst` (Codex `primary`, Claude `five_hour`).
- No repeat-ping guard. The agent raised that an idle account stays below 5% after a ping and is therefore pinged at each interval; the User's subsequent `--impl --dev` invocation did not ask for a guard, so the literal rule ships. A "no repeat within N minutes" guard remains an open alternative.
- Remove `auto_prime_registry.py` and its event file writes. Each ping attempt appends one monitor-log event (`auto_prime_pinged` or `auto_prime_failed`); skips are not logged, which ends the log flood.
- The account row status part shows the last ping outcome and age (for example `ping ok 3m ago`, `ping failed 3m ago`); the frame block keeps the per-target failure rows.
- Multiple auto-prime config entries still merge: union of targets, minimum interval, maximum threshold.

### Open questions

- Whether to add a repeat-ping guard after observing real behavior.
- Whether `gpt-6-luna` is accepted for these ChatGPT-account Codex logins; the first post-change ping verifies it.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`; new topical Note `agent-accounts-monitor.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d237f00a-2da8-4b96-9b54-a1addd3a5b4e`. Capture status: complete.

## Execution.Plan

1. Cold-read this note and current monitor code; checkpoint the clean product scope (`src/tarav/l1/agent/monitor/`, `_config_models.py`, the new test) while preserving unrelated dirty files, including the two pre-existing one-line import edits in `monitor/config.py` and `monitor/auto_prime_registry.py`.
2. Rewrite `monitor/workflows/auto_prime.py` around the threshold rule; slim `AutoPrimeTargetState`/`AutoPrimeWorkflowState`, `MonitorWorkflowConfig`, config parsing, builder merge, models constants, package exports, and the limits-tracking status part. Delete `monitor/auto_prime_registry.py`.
3. Set the Codex default ping model to `gpt-6-luna`.
4. Add `tests/test_agent_monitor_auto_prime.py`: pings below threshold, skips at/above threshold, skips without an ok reading, records failures, and config defaults/rejections.
5. Run focused tests, the full suite, and Ruff; reinstall the editable tool. Verify with one manual `tarav agent ping --provider codex -a jp/file`.
6. Update the User's `~/.tarav/config.json` auto-prime entry (back it up first): `interval_sec: 600`, `threshold_percent: 5`, drop retired keys, targets = Codex jp/mm/tk/br + Claude jp/br.
7. Capture changed Product.Surfaces, commit only this slice, capture daily/topical Wiki notes, and close this request.

## Impl.Log

- Design start checkpoint `f900aaa761dc71e7e3099b73af6a2bd3b5d7829e` (empty scope).
- Monitor tests were pruned in `2b01171`; only `tests/_monitor_helpers.py` remains, so the new test file restores focused coverage for this behavior.
- Design commit `2f8c06b5d869da3b3bf22df2fb16d1a62fe4a360`; six note Breadcrumbs audited with no POIs. Execute start checkpoint `5fbbd730a2bf7f46d2022a2da7ff81a313c1b69a` (empty scope). The pre-existing `tarav.l0._core.home` import edits in `monitor/config.py` and the deleted `auto_prime_registry.py` belong to an uncommitted refactor (`_core/home.py` is untracked); the completion commit keeps `config.py`'s HEAD import so HEAD stays importable, and the worktree keeps the refactor's line.
- `auto_prime.py` is now ≈270 lines: per interval, each configured target with an ok limits-tracking reading whose `burst` `used_percent` is below `threshold_percent` is pinged; each attempt logs `auto_prime_pinged` or `auto_prime_failed` to the monitor log. Trigger, period, verification, retry-cooldown state and constants are gone; `auto_prime_registry.py` is deleted. Config defaults `interval_sec` 600 and `threshold_percent` 5; providers limited to `codex` and `claude-code`; builder merge keeps union/min/max. The account row shows `ping ok|failed just now|<age> ago`. Codex default ping model is `gpt-6-luna`.
- Checks: new `tests/test_agent_monitor_auto_prime.py` passes (7). Ruff passes on `src` and `tests`. The maintained suite (explicit `testpaths` in `pyproject.toml`) passes (179) but does not collect the new file; adding it is left to the User because `pyproject.toml` carries an unrelated pending edit and the monitor tests were deliberately pruned in `2b01171`. Editable tool reinstalled.
- Live verification through the monitor's `resolve_account_runtime_agent(...).ping()` path: Codex jp `gpt-6-luna` ok (11.4 s); Claude jp `haiku` ok (3.8 s).
- User config `~/.tarav/config.json` (backup `config.json.pre-auto-prime-simplify`): auto-prime entry now `interval_sec` 600, `threshold_percent` 5, retired keys dropped, targets Codex jp/mm/tk/br + Claude jp/br (Claude om excluded). It loads as 600 s / 5% / six targets. A running monitor must be restarted to pick up the code change.
- Product.Surface capture: Breadcrumbs `cbc3ba5f…` (`auto_prime.py` workflow class), `59253674…` (`config.py` supported providers), `80e2a23a…` (`_config_models.py` Luna default); all three surfaces audit with no POIs.
- Not addressed: the Codex `workspace routing discovery failed` errors seen for tk/br/mm since 2026-09-25.
- Product completion commit `2fbb77820e40986a75552a5b806c0484717327ca`; its evidence audit passed (6 Breadcrumbs, 0 POIs). Wiki start checkpoint `102e107db85f82e8debfd9ed75d89e518f75f50e`; daily and new `agent-accounts-monitor.md` captured in `615df0e05cf63dc32b3995b7a7c2f02bffeb98a2` (10 new labels resolve; commit audit passed). The daily Note's older 868 Breadcrumb now reports `breadcrumb-position-missing` because the added session declaration shifted it one line; left unrepaired.
