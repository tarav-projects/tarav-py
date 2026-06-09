from __future__ import annotations

import datetime
import json
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_status import (
    AccountIdentity,
    AccountLimit,
    AccountStatus,
    USAGE_RECORD_STATUS_FRESH,
    USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
    USAGE_RECORD_STATUS_REGISTRY_LATEST,
    registry_latest_usage_record_metadata,
)
from agentos.agent.monitor.clock import (
    AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
    LIMITS_TRACKING_PERIODIC_ALARM,
    MONITOR_ENTER_ALARM,
    MONITOR_STARTUP_ALARM,
    MonitorClockSnapshot,
)
from agentos.agent.monitor.auto_prime_registry import (
    AUTO_PRIME_EVENT_ATTEMPT_FAILED,
    AUTO_PRIME_EVENT_ATTEMPT_STARTED,
    AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
    AUTO_PRIME_EVENT_ELIGIBLE,
    AUTO_PRIME_EVENT_SKIPPED_ALREADY_PRIMED,
    AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE,
    append_auto_prime_event,
)
from agentos.agent.monitor.loop import (
    MonitorWorkflow,
)
from agentos.agent.monitor.models import (
    AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW,
    AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN,
    AUTO_PRIME_TRIGGER_SLIDING_RESET,
    AUTO_PRIME_TRIGGER_ZERO_USAGE,
    AUTO_PRIME_UNINITIALIZED_TRIGGERS,
    AUTO_PRIME_PING_SUCCEEDED_STATUS,
    AUTO_PRIME_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_VERIFICATION_INEFFECTIVE,
    AUTO_PRIME_VERIFICATION_PENDING,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorAccountRow,
    MonitorFrame,
    MonitorInfoRow,
    MonitorResetRow,
    MonitorRow,
    MonitorState,
    MonitorTarget,
    MonitorTextRow,
    MonitorUsageTimeRow,
    MonitorWorkflowConfig,
)
from agentos.agent.providers import build_registered_account_agent
from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig
from agentos.agent.usage_registry import latest_usage_record
from agentos.claude.account_status import (
    CLAUDE_STATUSLINE_USAGE_SOURCE,
    claude_statusline_usage_record_limits,
)
from agentos.codex.account_status import (
    CODEX_APP_SERVER_USAGE_SOURCE,
    codex_usage_record_limits,
)
from agentos.copilot.account_status import (
    COPILOT_INTERNAL_USER_USAGE_SOURCE,
    copilot_usage_record_limits,
)


_PING_NUMBER_PATTERN = re.compile(r"(?<![\d.])-?\d+(?![\d.])")
_AUTO_PRIME_VERIFICATION_TIMEOUT_SEC = 900.0
_WEEKLY_BURST_PERCENT_BY_PROVIDER = {
    "codex": 15.7,
    "claude-code": 9.0,
}


class LimitsTrackingWorkflow:
    name = LIMITS_TRACKING_WORKFLOW
    periodic_alarm_name = LIMITS_TRACKING_PERIODIC_ALARM

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self.refresh_interval_sec = config.refresh_interval_sec

    def setup(
        self,
        state: MonitorState,
        frame: MonitorFrame,
    ) -> None:
        workflow_state = self._workflow_state(state)
        workflow_state["setup_tick"] = frame.tick
        workflow_state["refresh_interval_sec"] = self.config.refresh_interval_sec
        target_states = self._target_states(workflow_state)
        for target in self.config.targets:
            target_key = _target_key(target)
            target_state = self._target_state(
                target_states, target=target, target_key=target_key
            )
            self._prime_target_from_usage_registry(target_state, target=target)

        self._write_frame_block(frame, state=state, workflow_state=workflow_state)

    def loop(
        self,
        state: MonitorState,
        frame: MonitorFrame,
        trigger: MonitorClockSnapshot,
    ) -> None:
        run_count = state.workflow_run_counts.get(self.name, 0) + 1
        state.workflow_run_counts[self.name] = run_count
        workflow_state = self._workflow_state(state)
        workflow_state["last_tick"] = frame.tick
        workflow_state["run_count"] = run_count
        workflow_state["refresh_interval_sec"] = self.config.refresh_interval_sec
        workflow_state["fired_alarms"] = list(trigger.fired_alarm_names)

        should_refresh = bool(
            {
                MONITOR_STARTUP_ALARM,
                MONITOR_ENTER_ALARM,
                LIMITS_TRACKING_PERIODIC_ALARM,
            }.intersection(trigger.fired_alarm_names)
        )
        target_states = self._target_states(workflow_state)
        for target in self.config.targets:
            target_key = _target_key(target)
            target_state = self._target_state(
                target_states, target=target, target_key=target_key
            )
            if should_refresh:
                self._refresh_target(target_state, target=target, tick=frame.tick)

        self._write_frame_block(frame, state=state, workflow_state=workflow_state)

    def _prime_target_from_usage_registry(
        self,
        target_state: dict[str, object],
        *,
        target: MonitorTarget,
    ) -> None:
        source = _usage_record_source_for_target(target)
        if source is None:
            target_state.update(
                {
                    "status": "pending",
                    "setup_message": "waiting for first fetch",
                    "account_status": None,
                    "error": None,
                }
            )
            return
        record = latest_usage_record(
            provider=target.provider,
            account=target.account,
            home=target.home,
            source=source,
        )
        if record is None:
            target_state.update(
                {
                    "status": "pending",
                    "setup_message": "waiting for first fetch",
                    "account_status": None,
                    "error": None,
                }
            )
            return
        try:
            account_status = _account_status_summary_from_usage_record(
                target=target,
                source=source,
                record=record,
            )
        except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
            target_state.update(
                {
                    "status": "error",
                    "setup_message": None,
                    "account_status": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            return
        target_state.update(
            {
                "status": "ok",
                "setup_message": None,
                "account_status": account_status,
                "error": None,
            }
        )

    def _workflow_state(self, state: MonitorState) -> dict[str, object]:
        existing = state.data.get(self.name)
        if isinstance(existing, dict):
            return existing
        workflow_state: dict[str, object] = {
            "targets": {},
        }
        state.data[self.name] = workflow_state
        return workflow_state

    def _target_states(self, workflow_state: dict[str, object]) -> dict[str, object]:
        existing = workflow_state.get("targets")
        if isinstance(existing, dict):
            return existing
        target_states: dict[str, object] = {}
        workflow_state["targets"] = target_states
        return target_states

    def _target_state(
        self,
        target_states: dict[str, object],
        *,
        target: MonitorTarget,
        target_key: str,
    ) -> dict[str, object]:
        existing = target_states.get(target_key)
        if isinstance(existing, dict):
            return existing
        target_state = _new_target_state(target)
        target_states[target_key] = target_state
        return target_state

    def _refresh_target(
        self,
        target_state: dict[str, object],
        *,
        target: MonitorTarget,
        tick: int,
    ) -> None:
        try:
            agent = build_registered_account_agent(
                provider=target.provider, account=target.account, home=target.home
            )
            account_status = agent.account_status()
        except Exception as exc:
            target_state.update(
                {
                    "status": "error",
                    "last_refresh_tick": tick,
                    "refresh_count": _target_refresh_count(target_state) + 1,
                    "account_status": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            return
        target_state.update(
            {
                "status": "ok",
                "last_refresh_tick": tick,
                "refresh_count": _target_refresh_count(target_state) + 1,
                "account_status": account_status.summary(),
                "error": None,
            }
        )

    def _write_frame_block(
        self,
        frame: MonitorFrame,
        *,
        state: MonitorState,
        workflow_state: dict[str, object],
    ) -> None:
        rows: list[MonitorRow] = []
        target_summaries: list[dict[str, object]] = []
        target_states = self._target_states(workflow_state)
        for index, target in enumerate(self.config.targets):
            if index > 0:
                rows.append(MonitorTextRow(""))
            target_key = _target_key(target)
            raw_target_state = target_states.get(target_key)
            target_state = (
                raw_target_state if isinstance(raw_target_state, dict) else {}
            )
            auto_prime_target_state = _auto_prime_target_state(
                state, target_key=target_key
            )
            target_summaries.append(_target_state_summary(target_state))
            rows.extend(
                _target_rows(
                    target=target,
                    target_state=target_state,
                    auto_prime_target_state=auto_prime_target_state,
                )
            )
        data = {
            "workflow": self.name,
            "periodic_alarm_name": LIMITS_TRACKING_PERIODIC_ALARM,
            "refresh_interval_sec": self.config.refresh_interval_sec,
            "run_count": workflow_state.get("run_count"),
            "targets": target_summaries,
        }
        frame.add_block(self.name, rows=rows, data=data)


class AutoPrimeZeroLimitsWorkflow:
    name = AUTO_PRIME_ZERO_LIMITS_WORKFLOW
    periodic_alarm_name = AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self.refresh_interval_sec = config.refresh_interval_sec
        self.retry_cooldown_sec = (
            config.retry_cooldown_sec
            if config.retry_cooldown_sec is not None
            else 600.0
        )
        self.target_limit_ids = {
            provider: set(limit_ids)
            for provider, limit_ids in config.target_limit_ids.items()
        }
        self.triggers = {
            provider: set(trigger_names)
            for provider, trigger_names in config.triggers.items()
        }
        self.target_keys = {_target_key(target) for target in config.targets}

    def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
        workflow_state = self._workflow_state(state)
        workflow_state["setup_tick"] = frame.tick
        workflow_state["interval_sec"] = self.config.refresh_interval_sec
        workflow_state["retry_cooldown_sec"] = self.retry_cooldown_sec
        self._write_config_state(workflow_state)
        self._write_frame_block(frame, workflow_state=workflow_state)

    def loop(
        self,
        state: MonitorState,
        frame: MonitorFrame,
        trigger: MonitorClockSnapshot,
    ) -> None:
        run_count = state.workflow_run_counts.get(self.name, 0) + 1
        state.workflow_run_counts[self.name] = run_count
        workflow_state = self._workflow_state(state)
        workflow_state["last_tick"] = frame.tick
        workflow_state["run_count"] = run_count
        workflow_state["interval_sec"] = self.config.refresh_interval_sec
        workflow_state["retry_cooldown_sec"] = self.retry_cooldown_sec
        workflow_state["fired_alarms"] = list(trigger.fired_alarm_names)
        self._write_config_state(workflow_state)

        if trigger.fired(AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM):
            self._scan_and_prime(state, workflow_state=workflow_state, tick=frame.tick)

        self._write_frame_block(frame, workflow_state=workflow_state)

    def _workflow_state(self, state: MonitorState) -> dict[str, object]:
        existing = state.data.get(self.name)
        if isinstance(existing, dict):
            return existing
        workflow_state: dict[str, object] = {
            "targets": {},
            "last_scan": None,
        }
        state.data[self.name] = workflow_state
        return workflow_state

    def _target_states(self, workflow_state: dict[str, object]) -> dict[str, object]:
        existing = workflow_state.get("targets")
        if isinstance(existing, dict):
            return existing
        target_states: dict[str, object] = {}
        workflow_state["targets"] = target_states
        return target_states

    def _write_config_state(self, workflow_state: dict[str, object]) -> None:
        workflow_state["loaded_at"] = self.config.loaded_at
        workflow_state["config_fingerprint"] = self.config.config_fingerprint
        workflow_state["target_summary"] = [
            target.summary() for target in self.config.targets
        ]
        workflow_state["target_limit_ids"] = {
            provider: tuple(sorted(limit_ids))
            for provider, limit_ids in self.target_limit_ids.items()
        }
        workflow_state["triggers"] = {
            provider: tuple(sorted(trigger_names))
            for provider, trigger_names in self.triggers.items()
        }

    def _scan_and_prime(
        self,
        state: MonitorState,
        *,
        workflow_state: dict[str, object],
        tick: int,
    ) -> None:
        target_states = self._target_states(workflow_state)
        limits_state = state.data.get(LIMITS_TRACKING_WORKFLOW)
        if not isinstance(limits_state, dict):
            workflow_state["last_scan"] = {
                "tick": tick,
                "status": "skipped",
                "message": "limits-tracking state is not available",
                "pinged": 0,
                "failed": 0,
            }
            return
        raw_targets = limits_state.get("targets")
        if not isinstance(raw_targets, dict):
            workflow_state["last_scan"] = {
                "tick": tick,
                "status": "skipped",
                "message": "limits-tracking targets state is not available",
                "pinged": 0,
                "failed": 0,
            }
            return

        scan_at = datetime.datetime.now(tz=datetime.UTC)
        monotonic_now = time.monotonic()
        pinged = 0
        failed = 0
        for target_key, raw_target_state in raw_targets.items():
            if not isinstance(target_key, str) or not isinstance(
                raw_target_state, dict
            ):
                continue
            if target_key not in self.target_keys:
                continue
            target_state = self._target_state(
                target_states, raw_target_state, target_key
            )
            target_state["last_decisions"] = []
            target_state["last_decision"] = None
            self._verify_existing_primes(
                raw_target_state,
                target_state=target_state,
                scan_at=scan_at,
                tick=tick,
            )
            eligible_periods = self._eligible_periods(
                raw_target_state,
                target_state=target_state,
                scan_at=scan_at,
                monotonic_now=monotonic_now,
                tick=tick,
            )
            if not eligible_periods:
                continue
            if self._prime_target(
                target_state,
                source_target_state=raw_target_state,
                eligible_periods=eligible_periods,
                tick=tick,
                monotonic_now=monotonic_now,
                scan_at=scan_at,
            ):
                pinged += 1
            else:
                failed += 1
        workflow_state["last_scan"] = {
            "tick": tick,
            "status": "ok",
            "pinged": pinged,
            "failed": failed,
        }

    def _target_state(
        self,
        target_states: dict[str, object],
        source_target_state: dict[str, object],
        target_key: str,
    ) -> dict[str, object]:
        existing = target_states.get(target_key)
        if isinstance(existing, dict):
            return existing
        target_state: dict[str, object] = {
            "provider": source_target_state.get("provider"),
            "account": source_target_state.get("account"),
            "home": source_target_state.get("home"),
            "observations": {},
            "primed_periods": {},
        }
        target_states[target_key] = target_state
        return target_state

    def _eligible_periods(
        self,
        source_target_state: dict[str, object],
        *,
        target_state: dict[str, object],
        scan_at: datetime.datetime,
        monotonic_now: float,
        tick: int | None = None,
    ) -> list[dict[str, object]]:
        if source_target_state.get("status") != "ok":
            return []
        provider = _string_value(source_target_state.get("provider"))
        if provider is None:
            return []
        target_limit_ids = self.target_limit_ids.get(provider)
        if not target_limit_ids:
            return []
        trigger_names = self.triggers.get(provider)
        if not trigger_names:
            return []
        retry_after = target_state.get("retry_after_monotonic")
        if isinstance(retry_after, int | float) and monotonic_now < retry_after:
            self._record_retry_blocked_decisions(
                source_target_state,
                target_state=target_state,
                target_limit_ids=target_limit_ids,
                retry_after_monotonic=float(retry_after),
                tick=tick,
            )
            return []

        account_status = source_target_state.get("account_status")
        if not isinstance(account_status, dict):
            return []
        limits = account_status.get("limits")
        if not isinstance(limits, list):
            return []
        primed_periods = self._primed_periods(target_state)
        observed_at = _observation_time(source_target_state, fallback=scan_at)
        eligible: list[dict[str, object]] = []
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            limit_id = _string_value(limit.get("limit_id"))
            if limit_id is None or limit_id not in target_limit_ids:
                continue
            period = _eligible_limit_period(
                source_target_state,
                limit,
                target_limit_ids=target_limit_ids,
                trigger_names=trigger_names,
                observations=self._observations(target_state),
                now=observed_at,
                scan_at=scan_at,
            )
            if period is None:
                self._record_decision(
                    target_state,
                    limit_id=limit_id,
                    classification="primed",
                    action="skipped",
                    tick=tick,
                )
                continue
            period_key = period["period_key"]
            existing: dict[str, object] | None = None
            if isinstance(period_key, str):
                raw_existing = primed_periods.get(period_key)
                existing = raw_existing if isinstance(raw_existing, dict) else None
                if isinstance(existing, dict) and not self._period_can_retry(
                    period,
                    existing=existing,
                    monotonic_now=monotonic_now,
                ):
                    self._record_decision(
                        target_state,
                        limit_id=limit_id,
                        classification=_auto_prime_period_classification(existing),
                        action="skipped",
                        period=period,
                        tick=tick,
                    )
                    self._record_period_event(
                        AUTO_PRIME_EVENT_SKIPPED_ALREADY_PRIMED,
                        source_target_state=source_target_state,
                        period=period,
                        tick=tick,
                        status=existing.get("verification_status")
                        or existing.get("status"),
                    )
                    continue
            period["decision_classification"] = (
                _auto_prime_period_classification(existing)
                if existing is not None
                else "non-primed"
            )
            self._record_period_event(
                AUTO_PRIME_EVENT_ELIGIBLE,
                source_target_state=source_target_state,
                period=period,
                tick=tick,
            )
            eligible.append(period)
        return eligible

    def _observations(self, target_state: dict[str, object]) -> dict[str, object]:
        existing = target_state.get("observations")
        if isinstance(existing, dict):
            return existing
        observations: dict[str, object] = {}
        target_state["observations"] = observations
        return observations

    def _primed_periods(self, target_state: dict[str, object]) -> dict[str, object]:
        existing = target_state.get("primed_periods")
        if isinstance(existing, dict):
            return existing
        primed_periods: dict[str, object] = {}
        target_state["primed_periods"] = primed_periods
        return primed_periods

    def _prime_target(
        self,
        target_state: dict[str, object],
        *,
        source_target_state: dict[str, object],
        eligible_periods: list[dict[str, object]],
        tick: int,
        monotonic_now: float,
        scan_at: datetime.datetime,
    ) -> bool:
        target_state["last_attempt_tick"] = tick
        for period in eligible_periods:
            self._record_period_event(
                AUTO_PRIME_EVENT_ATTEMPT_STARTED,
                source_target_state=source_target_state,
                period=period,
                tick=tick,
            )
        try:
            _run_account_prime_ping(source_target_state)
        except Exception as exc:
            target_state["retry_after_monotonic"] = (
                monotonic_now + self.retry_cooldown_sec
            )
            target_state["last_error"] = {
                "message": str(exc),
                "error_type": type(exc).__name__,
                "last_attempt_tick": tick,
            }
            for period in eligible_periods:
                self._record_decision(
                    target_state,
                    limit_id=period.get("limit_id"),
                    classification=period.get("decision_classification"),
                    action="ping failed",
                    period=period,
                    tick=tick,
                )
                self._record_period_event(
                    AUTO_PRIME_EVENT_ATTEMPT_FAILED,
                    source_target_state=source_target_state,
                    period=period,
                    tick=tick,
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            return False

        target_state["last_success_tick"] = tick
        target_state["retry_after_monotonic"] = None
        target_state["last_error"] = None
        primed_periods = self._primed_periods(target_state)
        for period in eligible_periods:
            period_key = period.get("period_key")
            if not isinstance(period_key, str):
                continue
            self._record_decision(
                target_state,
                limit_id=period.get("limit_id"),
                classification=period.get("decision_classification"),
                action="pinged",
                period=period,
                tick=tick,
            )
            existing = primed_periods.get(period_key)
            attempt_count = 1
            if isinstance(existing, dict):
                raw_count = existing.get("attempt_count")
                if isinstance(raw_count, int):
                    attempt_count = raw_count + 1
            primed_periods[period_key] = {
                "limit_id": period.get("limit_id"),
                "status": AUTO_PRIME_PING_SUCCEEDED_STATUS,
                "verification_status": AUTO_PRIME_VERIFICATION_PENDING,
                "uninitialized": bool(period.get("uninitialized")),
                "trigger_reasons": period.get("trigger_reasons"),
                "attempt_count": attempt_count,
                "last_attempt_tick": tick,
                "last_success_tick": tick,
                "last_attempt_at": scan_at.isoformat(),
                "next_retry_after_monotonic": (
                    monotonic_now + self.retry_cooldown_sec
                    if period.get("uninitialized")
                    else None
                ),
            }
            self._record_period_event(
                AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
                source_target_state=source_target_state,
                period=period,
                tick=tick,
                status=AUTO_PRIME_VERIFICATION_PENDING,
                extra={"attempt_count": attempt_count},
            )
        return True

    def _period_can_retry(
        self,
        period: dict[str, object],
        *,
        existing: dict[str, object],
        monotonic_now: float,
    ) -> bool:
        if not period.get("uninitialized"):
            return False
        verification_status = existing.get("verification_status")
        if verification_status == AUTO_PRIME_VERIFICATION_EFFECTIVE:
            return False
        retry_after = existing.get("next_retry_after_monotonic")
        return isinstance(retry_after, int | float) and monotonic_now >= retry_after

    def _record_retry_blocked_decisions(
        self,
        source_target_state: dict[str, object],
        *,
        target_state: dict[str, object],
        target_limit_ids: set[str],
        retry_after_monotonic: float,
        tick: int | None,
    ) -> None:
        account_status = source_target_state.get("account_status")
        if not isinstance(account_status, dict):
            return
        limits = account_status.get("limits")
        if not isinstance(limits, list):
            return
        primed_periods = self._primed_periods(target_state)
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            limit_id = _string_value(limit.get("limit_id"))
            if limit_id is None or limit_id not in target_limit_ids:
                continue
            period_key = _uninitialized_period_key(source_target_state, limit_id)
            existing = primed_periods.get(period_key) if period_key else None
            self._record_decision(
                target_state,
                limit_id=limit_id,
                classification=_auto_prime_period_classification(existing)
                if isinstance(existing, dict)
                else "non-primed",
                action="retry",
                retry_after_monotonic=retry_after_monotonic,
                tick=tick,
            )

    def _record_decision(
        self,
        target_state: dict[str, object],
        *,
        limit_id: object,
        classification: object,
        action: str,
        period: dict[str, object] | None = None,
        retry_after_monotonic: float | None = None,
        tick: int | None,
    ) -> None:
        limit_id_value = _string_value(limit_id)
        classification_value = _string_value(classification)
        if limit_id_value is None or classification_value is None:
            return
        decision: dict[str, object] = {
            "limit_id": limit_id_value,
            "classification": classification_value,
            "action": action,
            "tick": tick,
        }
        if period is not None:
            period_key = _string_value(period.get("period_key"))
            if period_key is not None:
                decision["period_key"] = period_key
            trigger_reasons = period.get("trigger_reasons")
            if isinstance(trigger_reasons, tuple | list):
                decision["trigger_reasons"] = tuple(trigger_reasons)
        if retry_after_monotonic is not None:
            decision["retry_after_monotonic"] = retry_after_monotonic
        decisions = target_state.get("last_decisions")
        if not isinstance(decisions, list):
            decisions = []
            target_state["last_decisions"] = decisions
        decisions.append(decision)
        existing = target_state.get("last_decision")
        if not isinstance(existing, dict) or _decision_priority(
            decision
        ) >= _decision_priority(existing):
            target_state["last_decision"] = decision

    def _verify_existing_primes(
        self,
        source_target_state: dict[str, object],
        *,
        target_state: dict[str, object],
        scan_at: datetime.datetime,
        tick: int,
    ) -> None:
        if source_target_state.get("status") != "ok":
            return
        account_status = source_target_state.get("account_status")
        if not isinstance(account_status, dict):
            return
        limits = account_status.get("limits")
        if not isinstance(limits, list):
            return
        primed_periods = self._primed_periods(target_state)
        if not primed_periods:
            return
        provider = _string_value(source_target_state.get("provider"))
        observed_at = _observation_time(source_target_state, fallback=scan_at)
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            limit_id = _string_value(limit.get("limit_id"))
            if limit_id is None:
                continue
            period_key = _uninitialized_period_key(source_target_state, limit_id)
            if period_key is None:
                continue
            existing = primed_periods.get(period_key)
            if not isinstance(existing, dict):
                continue
            if existing.get("verification_status") == AUTO_PRIME_VERIFICATION_EFFECTIVE:
                continue
            trigger_names = self.triggers.get(provider or "", set())
            reasons = _uninitialized_trigger_reasons(
                source_target_state,
                limit,
                trigger_names=trigger_names,
                observations=self._observations(target_state),
                now=observed_at,
            )
            new_status = self._verification_status(
                existing,
                still_uninitialized=bool(reasons),
                observed_at=observed_at,
            )
            if new_status is None:
                continue
            previous_status = existing.get("verification_status")
            if previous_status == new_status:
                continue
            existing["verification_status"] = new_status
            existing["last_verified_tick"] = tick
            existing["last_verified_at"] = observed_at.isoformat()
            event_type = (
                AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE
                if new_status == AUTO_PRIME_VERIFICATION_EFFECTIVE
                else AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE
            )
            self._record_period_event(
                event_type,
                source_target_state=source_target_state,
                period={
                    "limit_id": limit_id,
                    "period_key": period_key,
                    "trigger_reasons": reasons
                    or existing.get("trigger_reasons")
                    or (),
                    "observed_at": observed_at.isoformat(),
                    "scan_at": scan_at.isoformat(),
                },
                tick=tick,
                status=new_status,
            )
            if new_status == AUTO_PRIME_VERIFICATION_EFFECTIVE:
                primed_periods.pop(period_key, None)

    def _verification_status(
        self,
        existing: dict[str, object],
        *,
        still_uninitialized: bool,
        observed_at: datetime.datetime,
    ) -> str | None:
        if not still_uninitialized:
            return AUTO_PRIME_VERIFICATION_EFFECTIVE
        last_attempt_at = _parse_datetime(_string_value(existing.get("last_attempt_at")))
        if last_attempt_at is None:
            return None
        elapsed = (observed_at - last_attempt_at).total_seconds()
        if elapsed >= min(self.retry_cooldown_sec, _AUTO_PRIME_VERIFICATION_TIMEOUT_SEC):
            return AUTO_PRIME_VERIFICATION_INEFFECTIVE
        return None

    def _record_period_event(
        self,
        event_type: str,
        *,
        source_target_state: dict[str, object],
        period: dict[str, object],
        tick: int | None,
        status: object = None,
        error: Mapping[str, object] | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        append_auto_prime_event(
            event_type,
            provider=source_target_state.get("provider"),
            account=source_target_state.get("account"),
            home=source_target_state.get("home"),
            limit_id=period.get("limit_id"),
            period_key=period.get("period_key"),
            trigger_reasons=period.get("trigger_reasons"),
            tick=tick,
            observed_at=period.get("observed_at"),
            scan_at=period.get("scan_at"),
            status=status,
            error=error,
            extra=extra,
        )

    def _write_frame_block(
        self, frame: MonitorFrame, *, workflow_state: dict[str, object]
    ) -> None:
        rows: list[MonitorRow] = []
        last_scan = workflow_state.get("last_scan")
        if isinstance(last_scan, dict):
            pinged = _int_value(last_scan.get("pinged"))
            failed = _int_value(last_scan.get("failed"))
            if pinged:
                rows.append(
                    MonitorInfoRow(label="    auto-prime", value=f"pinged {pinged}")
                )
            if failed:
                rows.append(
                    MonitorInfoRow(label="    auto-prime", value=f"failed {failed}")
                )
        for target_state in self._target_states(workflow_state).values():
            if not isinstance(target_state, dict):
                continue
            last_error = target_state.get("last_error")
            if not isinstance(last_error, dict):
                continue
            message = _string_value(last_error.get("message")) or "unknown error"
            rows.append(
                MonitorInfoRow(
                    label="    auto-prime",
                    value=f"{_target_state_name(target_state)} failed: {message}",
                )
            )
        if (
            not rows
            and workflow_state.get("setup_tick") is None
            and workflow_state.get("last_scan") is None
        ):
            return
        data = {
            "workflow": self.name,
            "periodic_alarm_name": AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
            "interval_sec": self.config.refresh_interval_sec,
            "retry_cooldown_sec": self.retry_cooldown_sec,
            "loaded_at": workflow_state.get("loaded_at"),
            "config_fingerprint": workflow_state.get("config_fingerprint"),
            "target_summary": workflow_state.get("target_summary"),
            "target_limit_ids": workflow_state.get("target_limit_ids"),
            "triggers": workflow_state.get("triggers"),
            "run_count": workflow_state.get("run_count"),
            "last_scan": last_scan,
            "targets": self._target_states(workflow_state),
        }
        frame.add_block(self.name, rows=rows, data=data)


def build_monitor_workflows(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> tuple[MonitorWorkflow, ...]:
    workflows: list[MonitorWorkflow] = []
    limits_tracking_configs = tuple(
        config for config in configs if config.name == LIMITS_TRACKING_WORKFLOW
    )
    auto_prime_configs = tuple(
        config for config in configs if config.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
    )
    for config in configs:
        if config.name == LIMITS_TRACKING_WORKFLOW:
            if not any(
                workflow.name == LIMITS_TRACKING_WORKFLOW for workflow in workflows
            ):
                workflows.append(
                    LimitsTrackingWorkflow(
                        _merge_limits_tracking_configs(limits_tracking_configs)
                    )
                )
            continue
        if config.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW:
            if not any(
                workflow.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
                for workflow in workflows
            ):
                workflows.append(
                    AutoPrimeZeroLimitsWorkflow(
                        _merge_auto_prime_configs(auto_prime_configs)
                    )
                )
            continue
        raise CliError(f"unknown monitor workflow {config.name!r}")
    return tuple(workflows)


def _merge_limits_tracking_configs(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> MonitorWorkflowConfig:
    if len(configs) == 1:
        return configs[0]
    targets: list[MonitorTarget] = []
    target_keys: set[tuple[str, str, str]] = set()
    raw_configs: list[dict[str, object]] = []
    refresh_interval_sec = min(config.refresh_interval_sec for config in configs)
    for config in configs:
        for target in config.targets:
            target_key = (target.provider, target.account, str(target.home))
            if target_key in target_keys:
                continue
            target_keys.add(target_key)
            targets.append(target)
        raw_configs.append(config.raw_config)
    return MonitorWorkflowConfig(
        name=LIMITS_TRACKING_WORKFLOW,
        targets=tuple(targets),
        refresh_interval_sec=refresh_interval_sec,
        loaded_at=configs[0].loaded_at,
        config_fingerprint=configs[0].config_fingerprint,
        raw_config={
            "workflow": LIMITS_TRACKING_WORKFLOW,
            "refresh_interval_sec": refresh_interval_sec,
            "configs": raw_configs,
        },
    )


def _merge_auto_prime_configs(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> MonitorWorkflowConfig:
    if len(configs) == 1:
        return configs[0]
    targets: list[MonitorTarget] = []
    target_keys: set[tuple[str, str, str]] = set()
    target_limit_ids: dict[str, tuple[str, ...]] = {}
    triggers: dict[str, tuple[str, ...]] = {}
    raw_configs: list[dict[str, object]] = []
    interval_sec = min(config.refresh_interval_sec for config in configs)
    retry_cooldown_sec = min(
        config.retry_cooldown_sec
        for config in configs
        if config.retry_cooldown_sec is not None
    )
    for config in configs:
        for target in config.targets:
            target_key = (target.provider, target.account, str(target.home))
            if target_key in target_keys:
                continue
            target_keys.add(target_key)
            targets.append(target)
        for provider, limit_ids in config.target_limit_ids.items():
            existing = target_limit_ids.get(provider, ())
            target_limit_ids[provider] = tuple(dict.fromkeys((*existing, *limit_ids)))
        for provider, trigger_names in config.triggers.items():
            existing = triggers.get(provider, ())
            triggers[provider] = tuple(dict.fromkeys((*existing, *trigger_names)))
        raw_configs.append(config.raw_config)
    return MonitorWorkflowConfig(
        name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
        targets=tuple(targets),
        refresh_interval_sec=interval_sec,
        retry_cooldown_sec=retry_cooldown_sec,
        target_limit_ids=target_limit_ids,
        triggers=triggers,
        loaded_at=configs[0].loaded_at,
        config_fingerprint=configs[0].config_fingerprint,
        raw_config={
            "workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            "interval_sec": interval_sec,
            "retry_cooldown_sec": retry_cooldown_sec,
            "target_limits": target_limit_ids,
            "triggers": triggers,
            "configs": raw_configs,
        },
    )


def _target_key(target: MonitorTarget) -> str:
    return f"{target.provider}/{target.account}@{target.home}"


def _new_target_state(target: MonitorTarget) -> dict[str, object]:
    return {
        "provider": target.provider,
        "account": target.account,
        "home": str(target.home),
        "status": "pending",
        "refresh_count": 0,
    }


def _target_refresh_count(target_state: dict[str, object]) -> int:
    count = target_state.get("refresh_count", 0)
    if isinstance(count, int):
        return count
    return 0


def _usage_record_source_for_target(target: MonitorTarget) -> str | None:
    if target.provider == "codex":
        return CODEX_APP_SERVER_USAGE_SOURCE
    if target.provider == "claude-code":
        return CLAUDE_STATUSLINE_USAGE_SOURCE
    if target.provider == "copilot-cli":
        return COPILOT_INTERNAL_USER_USAGE_SOURCE
    return None


def _usage_record_limit_parser(
    source: str,
) -> Callable[[Mapping[str, Any]], tuple[AccountLimit, ...]]:
    if source == CODEX_APP_SERVER_USAGE_SOURCE:
        return codex_usage_record_limits
    if source == CLAUDE_STATUSLINE_USAGE_SOURCE:
        return claude_statusline_usage_record_limits
    if source == COPILOT_INTERNAL_USER_USAGE_SOURCE:
        return copilot_usage_record_limits
    raise CliError(f"unsupported monitor usage record source {source!r}")


def _account_status_summary_from_usage_record(
    *,
    target: MonitorTarget,
    source: str,
    record: Mapping[str, Any],
) -> dict[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise CliError("usage registry record payload must be an object")
    limits = _usage_record_limit_parser(source)(payload)
    status = AccountStatus(
        provider=target.provider,
        account=target.account,
        home=target.home,
        check_status="ok",
        usage_status="ok",
        auth_state="registry_latest",
        expected_identity=AccountIdentity(),
        fetched_identity=None,
        identity_match="unknown",
        usage_summary=_limits_summary(
            {"limits": [limit.summary() for limit in limits]}
        ),
        limits=limits,
        raw={
            "usage": payload,
            "usage_record": registry_latest_usage_record_metadata(
                source=source,
                recorded_at=_string_value(record.get("recorded_at")),
            ),
        },
    )
    return status.summary()


def _target_state_summary(target_state: dict[str, object]) -> dict[str, object]:
    return dict(target_state)


def _target_rows(
    *,
    target: MonitorTarget,
    target_state: dict[str, object],
    auto_prime_target_state: dict[str, object] | None = None,
) -> list[MonitorRow]:
    account_status = target_state.get("account_status")
    status_parts = _account_status_parts(
        target_state=target_state,
        account_status=account_status if isinstance(account_status, dict) else None,
        auto_prime_target_state=auto_prime_target_state,
    )
    rows: list[MonitorRow] = [
        MonitorAccountRow(
            label=f"  {_target_title(target)}",
            status=" · ".join(status_parts) if status_parts else None,
        )
    ]
    if target_state.get("status") == "error":
        rows.append(
            MonitorInfoRow(label="    error", value=_error_message(target_state))
        )
        return rows
    if isinstance(account_status, dict):
        limit_rows = _account_limit_rows(account_status, provider=target.provider)
        if limit_rows:
            rows.extend(limit_rows)
            fetch_error_row = _fetch_error_row(account_status)
            if fetch_error_row is not None:
                rows.append(fetch_error_row)
            return rows
        rows.append(
            MonitorInfoRow(label="    usage", value=_limits_summary(account_status))
        )
        return rows
    setup_message = target_state.get("setup_message")
    if isinstance(setup_message, str) and setup_message:
        rows.append(MonitorInfoRow(label="    usage", value=setup_message))
    return rows


def _target_title(target: MonitorTarget) -> str:
    prefix = "⬢ " if target.provider == "codex" else ""
    return f"{prefix}{target.provider}/{target.account}:"


def _error_message(target_state: dict[str, object]) -> str:
    error = target_state.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return "unknown error"


def _account_status_parts(
    *,
    target_state: dict[str, object],
    account_status: dict[str, Any] | None,
    auto_prime_target_state: dict[str, object] | None,
) -> tuple[str, ...]:
    parts: list[str] = []
    fetch_part = _usage_refresh_status_part(
        target_state=target_state,
        account_status=account_status,
    )
    if fetch_part is not None:
        parts.append(fetch_part)
    auto_prime_part = _auto_prime_status_part(auto_prime_target_state)
    if auto_prime_part is not None:
        parts.append(auto_prime_part)
    return tuple(parts)


def _account_limit_rows(
    account_status: dict[str, Any], *, provider: str
) -> list[MonitorRow]:
    limits = account_status.get("limits")
    if not isinstance(limits, list):
        return []

    rows: list[MonitorRow] = []
    now = datetime.datetime.now(tz=datetime.UTC)
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        usage_over_time = limit.get("usage_over_time")
        if not isinstance(usage_over_time, dict):
            continue
        used_percent = _int_value(usage_over_time.get("used_percent"))
        elapsed_percent = _elapsed_percent(usage_over_time, recorded_at=now)
        if used_percent is None or elapsed_percent is None:
            continue
        label = _limit_label(limit, usage_over_time)
        ratio = _usage_time_ratio(used_percent, elapsed_percent)
        value = _usage_time_value(
            used_percent=used_percent,
            elapsed_percent=elapsed_percent,
            ratio=ratio,
        )
        row_label = "    usage/time"
        label_variants: tuple[str, ...] = ()
        value_variants: tuple[str, ...] = ()
        burst_unit = _weekly_burst_unit_summary(
            provider=provider,
            limit=limit,
            usage_over_time=usage_over_time,
            used_percent=used_percent,
            recorded_at=now,
        )
        if burst_unit is not None:
            burst_value = burst_unit.get("value")
            if isinstance(burst_value, str):
                label_variants = (
                    "    usage/time [used]",
                    "    time/usage [left]",
                )
                row_label = label_variants[0]
                value_variants = (value, burst_value)
        rows.append(
            MonitorUsageTimeRow(
                label=row_label,
                value=value,
                suffix=label,
                used_percent=max(0, min(100, used_percent)),
                elapsed_percent=max(0, min(100, elapsed_percent)),
                ratio=ratio,
                label_variants=label_variants,
                value_variants=value_variants,
                burst_unit=burst_unit,
            )
        )
        reset_columns = _reset_columns(usage_over_time, recorded_at=now)
        if reset_columns is not None:
            marker_percent = (
                max(0, min(100, used_percent))
                if used_percent > elapsed_percent
                else None
            )
            rows.append(
                MonitorResetRow(
                    label="        resets",
                    value=reset_columns[0],
                    suffix=reset_columns[1],
                    elapsed_percent=max(0, min(100, elapsed_percent)),
                    marker_percent=marker_percent,
                )
            )
    return rows


def _usage_refresh_status_part(
    *,
    target_state: dict[str, object],
    account_status: dict[str, Any] | None,
) -> str | None:
    if target_state.get("status") == "error":
        return "error"
    if account_status is None:
        return None
    raw = account_status.get("raw")
    if not isinstance(raw, dict):
        return None
    usage_record = raw.get("usage_record")
    if not isinstance(usage_record, dict):
        return None
    status = usage_record.get("status")
    if status == USAGE_RECORD_STATUS_FRESH:
        return "fresh"
    if status not in {
        USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
        USAGE_RECORD_STATUS_REGISTRY_LATEST,
    }:
        return None
    recorded_at = _parse_datetime(_string_value(usage_record.get("recorded_at")))
    if recorded_at is None:
        return None
    age_sec = _int_value(usage_record.get("age_sec"))
    if age_sec is None:
        age_sec = int(
            (datetime.datetime.now(tz=datetime.UTC) - recorded_at).total_seconds()
        )
    label = (
        "fallback"
        if status == USAGE_RECORD_STATUS_REGISTRY_FALLBACK
        else "latest"
    )
    return f"{label} {_format_age_duration(age_sec)} ago"


def _auto_prime_target_state(
    state: MonitorState, *, target_key: str
) -> dict[str, object] | None:
    workflow_state = state.data.get(AUTO_PRIME_ZERO_LIMITS_WORKFLOW)
    if not isinstance(workflow_state, dict):
        return None
    target_states = workflow_state.get("targets")
    if not isinstance(target_states, dict):
        return None
    target_state = target_states.get(target_key)
    if not isinstance(target_state, dict):
        return None
    return target_state


def _auto_prime_status_part(target_state: dict[str, object] | None) -> str | None:
    if target_state is None:
        return None
    decision_part = _auto_prime_decision_status_part(target_state.get("last_decision"))
    if decision_part is not None:
        return decision_part
    if isinstance(target_state.get("last_error"), dict):
        return "prime failed"
    primed_periods = target_state.get("primed_periods")
    retry_after_monotonic = _auto_prime_retry_after_monotonic(
        target_state,
        primed_periods=primed_periods if isinstance(primed_periods, dict) else {},
    )
    if not isinstance(primed_periods, dict):
        if retry_after_monotonic is not None:
            return _auto_prime_retry_status_part(retry_after_monotonic)
        return None

    has_ineffective = False
    has_pending = False
    has_effective = False
    for primed_period in primed_periods.values():
        if not isinstance(primed_period, dict):
            continue
        verification_status = primed_period.get("verification_status")
        if verification_status == AUTO_PRIME_VERIFICATION_INEFFECTIVE:
            has_ineffective = True
        elif verification_status == AUTO_PRIME_VERIFICATION_PENDING:
            has_pending = True
        elif verification_status == AUTO_PRIME_VERIFICATION_EFFECTIVE:
            has_effective = True

    if has_ineffective:
        return "prime ineffective"
    if retry_after_monotonic is not None:
        return _auto_prime_retry_status_part(retry_after_monotonic)
    if has_pending:
        return "prime pending"
    if has_effective:
        return "primed"
    return None


def _auto_prime_decision_status_part(decision: object) -> str | None:
    if not isinstance(decision, dict):
        return None
    limit_id = _string_value(decision.get("limit_id"))
    classification = _string_value(decision.get("classification"))
    action = _string_value(decision.get("action"))
    if limit_id is None or classification is None or action is None:
        return None
    if action == "retry":
        retry_after_monotonic = _float_value(decision.get("retry_after_monotonic"))
        if retry_after_monotonic is not None:
            action = _retry_action_text(retry_after_monotonic)
    return f"{limit_id} {classification}/{action}"


def _retry_action_text(retry_after_monotonic: float) -> str:
    remaining_sec = int(retry_after_monotonic - time.monotonic())
    if remaining_sec <= 0:
        return "retry"
    return f"retry in {_format_age_duration(remaining_sec)}"


def _auto_prime_period_classification(period: object) -> str:
    if not isinstance(period, dict):
        return "primed"
    verification_status = period.get("verification_status")
    if verification_status == AUTO_PRIME_VERIFICATION_PENDING:
        return "primed-pending"
    if verification_status == AUTO_PRIME_VERIFICATION_EFFECTIVE:
        return "primed-effective"
    if verification_status == AUTO_PRIME_VERIFICATION_INEFFECTIVE:
        return "primed-ineffective"
    return "primed"


def _decision_priority(decision: dict[str, object]) -> int:
    action = decision.get("action")
    if action in {"pinged", "ping failed"}:
        return 40
    if action == "retry":
        return 30
    if decision.get("classification") in {
        "primed-pending",
        "primed-effective",
        "primed-ineffective",
    }:
        return 20
    return 10


def _auto_prime_retry_after_monotonic(
    target_state: dict[str, object], *, primed_periods: dict[object, object]
) -> float | None:
    retry_after_monotonic = _float_value(target_state.get("retry_after_monotonic"))
    for primed_period in primed_periods.values():
        if not isinstance(primed_period, dict):
            continue
        period_retry_after = _float_value(
            primed_period.get("next_retry_after_monotonic")
        )
        if period_retry_after is None:
            continue
        if retry_after_monotonic is None:
            retry_after_monotonic = period_retry_after
            continue
        retry_after_monotonic = min(retry_after_monotonic, period_retry_after)
    return retry_after_monotonic


def _auto_prime_retry_status_part(retry_after_monotonic: float) -> str:
    return f"prime {_retry_action_text(retry_after_monotonic)}"


def _fetch_error_row(account_status: dict[str, Any]) -> MonitorInfoRow | None:
    raw = account_status.get("raw")
    if not isinstance(raw, dict):
        return None
    usage_record = raw.get("usage_record")
    if not isinstance(usage_record, dict):
        return None
    if usage_record.get("status") != USAGE_RECORD_STATUS_REGISTRY_FALLBACK:
        return None
    live_error = usage_record.get("live_error")
    if not isinstance(live_error, dict):
        return None
    message = live_error.get("message")
    if not isinstance(message, str) or not message:
        return None
    retry_suffix = _fetch_error_retry_suffix(live_error)
    if retry_suffix is not None:
        message = f"{message} [{retry_suffix}]"
    return MonitorInfoRow(label="        fetch error", value=message)


def _fetch_error_retry_suffix(live_error: dict[str, object]) -> str | None:
    detail = live_error.get("detail")
    if not isinstance(detail, dict):
        return None
    remaining_sec = _int_value(detail.get("retry_after_remaining_sec"))
    if remaining_sec is None:
        retry_after_until = _parse_datetime(
            _string_value(detail.get("retry_after_until"))
        )
        if retry_after_until is None:
            return None
        remaining_sec = int(
            (retry_after_until - datetime.datetime.now(tz=datetime.UTC)).total_seconds()
        )
    if remaining_sec <= 0:
        return None
    return f"retry in {_format_age_duration(remaining_sec)}"


def _usage_time_value(
    *, used_percent: int, elapsed_percent: int, ratio: float | None
) -> str:
    return (
        f"{_format_usage_percent_plain(used_percent)} / {_format_usage_percent_plain(elapsed_percent)}"
        f" = {_format_usage_time_ratio_text(ratio)} [%]"
    )


def _weekly_burst_unit_summary(
    *,
    provider: str,
    limit: dict[str, Any],
    usage_over_time: dict[str, object],
    used_percent: int,
    recorded_at: datetime.datetime,
) -> dict[str, object] | None:
    weekly_burst_percent = _WEEKLY_BURST_PERCENT_BY_PROVIDER.get(provider)
    if weekly_burst_percent is None or not _is_weekly_limit(limit, usage_over_time):
        return None
    time_burst_units_left = _remaining_burst_windows(
        usage_over_time,
        recorded_at=recorded_at,
    )
    if time_burst_units_left is None:
        return None
    usage_burst_units_left = max(0, 100 - min(100, used_percent)) / weekly_burst_percent
    left_ratio = _usage_time_left_ratio(
        usage_burst_units_left=usage_burst_units_left,
        time_burst_units_left=time_burst_units_left,
    )
    return {
        "unit": "Burst",
        "weekly_burst_percent": weekly_burst_percent,
        "usage_burst_units_left": usage_burst_units_left,
        "time_burst_units_left": time_burst_units_left,
        "left_ratio": left_ratio,
        "value": _usage_time_burst_unit_value(
            usage_burst_units_left=usage_burst_units_left,
            time_burst_units_left=time_burst_units_left,
            ratio=left_ratio,
        ),
    }


def _is_weekly_limit(
    limit: dict[str, Any], usage_over_time: dict[str, object]
) -> bool:
    limit_id = _string_value(limit.get("limit_id"))
    if limit_id == "weekly":
        return True
    return _int_value(usage_over_time.get("period_duration_mins")) == 10_080


def _usage_time_burst_unit_value(
    *,
    usage_burst_units_left: float,
    time_burst_units_left: float,
    ratio: float | None,
) -> str:
    return (
        f"{time_burst_units_left:.1f} / {usage_burst_units_left:.1f}"
        f" = {_format_usage_time_ratio_text(ratio)} [Burst]"
    )


def _remaining_burst_windows(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> float | None:
    period_ends_at = _parse_datetime(_string_value(usage_over_time.get("period_ends_at")))
    if period_ends_at is None:
        period_ends_at = _parse_datetime(_string_value(usage_over_time.get("resets_at")))
    if period_ends_at is None:
        return None
    remaining_seconds = max(0.0, (period_ends_at - recorded_at).total_seconds())
    return remaining_seconds / (300 * 60)


def _usage_time_left_ratio(
    *,
    usage_burst_units_left: float,
    time_burst_units_left: float,
) -> float | None:
    if usage_burst_units_left <= 0:
        return None
    return time_burst_units_left / usage_burst_units_left


def _limits_summary(account_status: dict[str, Any]) -> str:
    usage_summary = account_status.get("usage_summary")
    if isinstance(usage_summary, str) and usage_summary:
        return usage_summary
    usage_error = _usage_error_message(account_status)
    if usage_error is not None:
        return f"error | {usage_error}"
    limits = account_status.get("limits")
    if not isinstance(limits, list) or not limits:
        return "none"
    summaries: list[str] = []
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        label = limit.get("limit_label") or limit.get("limit_name")
        usage = limit.get("usage_over_time")
        if isinstance(label, str) and isinstance(usage, dict):
            used_percent = usage.get("used_percent")
            if isinstance(used_percent, int | float):
                summaries.append(f"{label} {used_percent}%")
    if summaries:
        return ", ".join(summaries)
    return "unknown"


def _usage_error_message(account_status: dict[str, Any]) -> str | None:
    usage_errors = account_status.get("usage_errors")
    if not isinstance(usage_errors, list) or not usage_errors:
        return None
    first_error = usage_errors[0]
    if not isinstance(first_error, dict):
        return "unknown usage error"
    message = first_error.get("message")
    if isinstance(message, str) and message:
        return message
    error_type = first_error.get("type")
    if isinstance(error_type, str) and error_type:
        return error_type
    return "unknown usage error"


def _limit_label(limit: dict[str, Any], usage_over_time: dict[str, object]) -> str:
    duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
    if duration_mins == 300:
        return "Burst"
    if duration_mins == 10_080:
        return "Weekly"
    label = limit.get("limit_label") or limit.get("limit_name")
    if isinstance(label, str) and label:
        return label
    return "usage"


def _reset_columns(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> tuple[str, str | None] | None:
    reset_at = _parse_datetime(_string_value(usage_over_time.get("resets_at")))
    if reset_at is None:
        reset_at = _parse_datetime(_string_value(usage_over_time.get("period_ends_at")))
    if reset_at is None:
        return None
    reset_display = reset_at.astimezone().strftime("%a %m-%d %H:%M")
    remaining_display = _format_remaining_duration(
        int((reset_at - recorded_at).total_seconds())
    )
    return reset_display, remaining_display


def _elapsed_percent(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> int | None:
    period_started_at = _parse_datetime(
        _string_value(usage_over_time.get("period_started_at"))
    )
    period_ends_at = _parse_datetime(
        _string_value(usage_over_time.get("period_ends_at"))
    )
    if period_started_at is None:
        duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
        if duration_mins is not None and period_ends_at is not None:
            period_started_at = period_ends_at - datetime.timedelta(
                minutes=duration_mins
            )
    if period_ends_at is None:
        period_ends_at = _parse_datetime(
            _string_value(usage_over_time.get("resets_at"))
        )
    if (
        period_started_at is None
        or period_ends_at is None
        or period_ends_at <= period_started_at
    ):
        return None
    duration_seconds = (period_ends_at - period_started_at).total_seconds()
    if duration_seconds <= 0:
        return None
    elapsed_seconds = (recorded_at - period_started_at).total_seconds()
    elapsed_ratio = max(0.0, min(1.0, elapsed_seconds / duration_seconds))
    return round(elapsed_ratio * 100)


def _format_usage_percent_plain(value: int) -> str:
    return f"{max(0, min(100, value))}%".rjust(3)


def _usage_time_ratio(used_percent: int, elapsed_percent: int) -> float | None:
    clamped_elapsed_percent = max(0, min(100, elapsed_percent))
    if clamped_elapsed_percent == 0:
        return None
    clamped_used_percent = max(0, min(100, used_percent))
    return clamped_used_percent / clamped_elapsed_percent


def _format_usage_time_ratio_text(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio:.1f}"


def _format_remaining_duration(diff_seconds: int) -> str:
    if diff_seconds <= 0:
        return "0m"
    total_minutes = diff_seconds // 60
    if total_minutes == 0:
        total_minutes = 1
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


def _format_age_duration(diff_seconds: int) -> str:
    return _format_remaining_duration(max(0, diff_seconds))


def _parse_datetime(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _observation_time(
    source_target_state: dict[str, object], *, fallback: datetime.datetime
) -> datetime.datetime:
    account_status = source_target_state.get("account_status")
    if not isinstance(account_status, dict):
        return fallback
    raw = account_status.get("raw")
    if not isinstance(raw, dict):
        return fallback
    usage_record = raw.get("usage_record")
    if not isinstance(usage_record, dict):
        return fallback
    recorded_at = _parse_datetime(_string_value(usage_record.get("recorded_at")))
    return recorded_at or fallback


def _eligible_limit_period(
    source_target_state: dict[str, object],
    limit: dict[str, object],
    *,
    target_limit_ids: set[str],
    trigger_names: set[str],
    observations: dict[str, object],
    now: datetime.datetime,
    scan_at: datetime.datetime,
) -> dict[str, object] | None:
    limit_id = _string_value(limit.get("limit_id"))
    if limit_id is None or limit_id not in target_limit_ids:
        return None
    usage_over_time = limit.get("usage_over_time")
    if not isinstance(usage_over_time, dict):
        return None
    used_percent = _int_value(usage_over_time.get("used_percent"))
    period_started_at = _string_value(usage_over_time.get("period_started_at"))
    period_ends_at = _string_value(usage_over_time.get("period_ends_at"))
    resets_at = _string_value(usage_over_time.get("resets_at"))
    period_end_key = period_ends_at or resets_at
    if period_started_at is None or period_end_key is None:
        return None
    period_end = _parse_datetime(period_end_key)
    if period_end is None or period_end <= now:
        return None
    provider = _string_value(source_target_state.get("provider"))
    account = _string_value(source_target_state.get("account"))
    home = _string_value(source_target_state.get("home"))
    if provider is None or account is None or home is None:
        return None

    normal_period_key = "|".join(
        (provider, account, home, limit_id, period_started_at, period_end_key)
    )
    previous_observation = observations.get(limit_id)
    reasons = _auto_prime_trigger_reasons(
        limit,
        usage_over_time,
        used_percent=used_percent,
        trigger_names=trigger_names,
        previous_observation=previous_observation
        if isinstance(previous_observation, dict)
        else None,
        period_key=normal_period_key,
        period_end=period_end,
        now=now,
    )
    observations[limit_id] = {
        "period_key": normal_period_key,
        "period_end": period_end.isoformat(),
        "observed_at": now.isoformat(),
        "used_percent": used_percent,
        "remaining_ratio": _remaining_window_ratio(
            limit, usage_over_time, period_end, now
        ),
    }
    if not reasons:
        return None

    uninitialized = any(
        reason in AUTO_PRIME_UNINITIALIZED_TRIGGERS for reason in reasons
    )
    period_key = (
        "|".join((provider, account, home, limit_id, "uninitialized"))
        if uninitialized
        else normal_period_key
    )
    return {
        "limit_id": limit_id,
        "period_key": period_key,
        "trigger_reasons": reasons,
        "uninitialized": uninitialized,
        "observed_at": now.isoformat(),
        "scan_at": scan_at.isoformat(),
    }


def _uninitialized_period_key(
    source_target_state: dict[str, object], limit_id: str
) -> str | None:
    provider = _string_value(source_target_state.get("provider"))
    account = _string_value(source_target_state.get("account"))
    home = _string_value(source_target_state.get("home"))
    if provider is None or account is None or home is None:
        return None
    return "|".join((provider, account, home, limit_id, "uninitialized"))


def _uninitialized_trigger_reasons(
    source_target_state: dict[str, object],
    limit: dict[str, object],
    *,
    trigger_names: set[str],
    observations: dict[str, object],
    now: datetime.datetime,
) -> tuple[str, ...]:
    limit_id = _string_value(limit.get("limit_id"))
    usage_over_time = limit.get("usage_over_time")
    if limit_id is None or not isinstance(usage_over_time, dict):
        return ()
    used_percent = _int_value(usage_over_time.get("used_percent"))
    period_started_at = _string_value(usage_over_time.get("period_started_at"))
    period_ends_at = _string_value(usage_over_time.get("period_ends_at"))
    resets_at = _string_value(usage_over_time.get("resets_at"))
    period_end_key = period_ends_at or resets_at
    if period_started_at is None or period_end_key is None:
        return ()
    period_end = _parse_datetime(period_end_key)
    if period_end is None or period_end <= now:
        return ()
    provider = _string_value(source_target_state.get("provider"))
    account = _string_value(source_target_state.get("account"))
    home = _string_value(source_target_state.get("home"))
    if provider is None or account is None or home is None:
        return ()
    normal_period_key = "|".join(
        (provider, account, home, limit_id, period_started_at, period_end_key)
    )
    previous_observation = observations.get(limit_id)
    reasons = _auto_prime_trigger_reasons(
        limit,
        usage_over_time,
        used_percent=used_percent,
        trigger_names=trigger_names,
        previous_observation=previous_observation
        if isinstance(previous_observation, dict)
        else None,
        period_key=normal_period_key,
        period_end=period_end,
        now=now,
    )
    return tuple(
        reason for reason in reasons if reason in AUTO_PRIME_UNINITIALIZED_TRIGGERS
    )


def _auto_prime_trigger_reasons(
    limit: dict[str, object],
    usage_over_time: dict[str, object],
    *,
    used_percent: int | None,
    trigger_names: set[str],
    previous_observation: dict[str, object] | None,
    period_key: str,
    period_end: datetime.datetime,
    now: datetime.datetime,
) -> tuple[str, ...]:
    reasons: list[str] = []
    near_zero_full_window = _is_near_zero_full_window(
        limit,
        usage_over_time,
        used_percent=used_percent,
        period_end=period_end,
        now=now,
    )
    if AUTO_PRIME_TRIGGER_ZERO_USAGE in trigger_names and used_percent == 0:
        reasons.append(AUTO_PRIME_TRIGGER_ZERO_USAGE)
    if (
        AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW in trigger_names
        and near_zero_full_window
    ):
        reasons.append(AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW)
    if (
        AUTO_PRIME_TRIGGER_SLIDING_RESET in trigger_names
        and previous_observation is not None
        and _is_sliding_reset(previous_observation, period_end=period_end, now=now)
    ):
        reasons.append(AUTO_PRIME_TRIGGER_SLIDING_RESET)
    if (
        AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN in trigger_names
        and near_zero_full_window
        and previous_observation is not None
        and previous_observation.get("period_key") != period_key
    ):
        reasons.append(AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN)
    return tuple(reasons)


def _is_near_zero_full_window(
    limit: dict[str, object],
    usage_over_time: dict[str, object],
    *,
    used_percent: int | None,
    period_end: datetime.datetime,
    now: datetime.datetime,
) -> bool:
    if used_percent is None or used_percent > 1:
        return False
    remaining_ratio = _remaining_window_ratio(limit, usage_over_time, period_end, now)
    return remaining_ratio is not None and remaining_ratio >= 0.98


def _remaining_window_ratio(
    limit: dict[str, object],
    usage_over_time: dict[str, object],
    period_end: datetime.datetime,
    now: datetime.datetime,
) -> float | None:
    duration_mins = _period_duration_mins(limit, usage_over_time)
    if duration_mins is None or duration_mins <= 0:
        return None
    remaining_seconds = (period_end - now).total_seconds()
    if remaining_seconds <= 0:
        return None
    return remaining_seconds / (duration_mins * 60)


def _period_duration_mins(
    limit: dict[str, object], usage_over_time: dict[str, object]
) -> int | None:
    duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
    if duration_mins is not None:
        return duration_mins
    provider_limit = limit.get("provider_limit")
    if not isinstance(provider_limit, dict):
        return None
    duration_mins = _int_value(provider_limit.get("windowDurationMins"))
    if duration_mins is not None:
        return duration_mins
    return _int_value(provider_limit.get("window_duration_mins"))


def _is_sliding_reset(
    previous_observation: dict[str, object],
    *,
    period_end: datetime.datetime,
    now: datetime.datetime,
) -> bool:
    previous_end = _parse_datetime(
        _string_value(previous_observation.get("period_end"))
    )
    previous_observed_at = _parse_datetime(
        _string_value(previous_observation.get("observed_at"))
    )
    if previous_end is None or previous_observed_at is None:
        return False
    observation_delta = (now - previous_observed_at).total_seconds()
    end_delta = (period_end - previous_end).total_seconds()
    if observation_delta <= 0 or end_delta <= 0:
        return False
    return abs(end_delta - observation_delta) <= max(60.0, 0.20 * observation_delta)


def _run_account_prime_ping(source_target_state: dict[str, object]) -> None:
    provider = _required_target_string(source_target_state, "provider")
    account = _required_target_string(source_target_state, "account")
    home = Path(_required_target_string(source_target_state, "home"))
    agent = build_registered_account_agent(
        provider=provider,
        account=account,
        home=home,
    )
    if not agent.ping.enabled:
        raise CliError(
            f"agent {agent.instance_id or '<default>'} for provider {agent.provider} has ping disabled"
        )
    command_config = AgentCommandConfig(
        prompt=agent.ping.prompt,
        argv=agent.ping.argv,
        model=agent.ping.model,
        account=None,
        interaction_mode="non_interactive",
        credential_success_source=None,
    )
    result = agent.run(
        command_config,
        AgentRunConfig(cwd=Path.cwd().resolve(), process_mode="capture"),
    )
    _validate_prime_ping_result(result, expected_number=agent.ping.expected_number)
    _record_prime_ping_credential_success(agent)


def _record_prime_ping_credential_success(agent) -> None:
    if agent.home is None or agent.account is None:
        return
    try:
        if agent.provider == "claude-code":
            from agentos.claude.account_registry import (
                has_claude_oauth_token_kind,
                promote_verified_claude_ambient_auth_from_home,
            )

            if has_claude_oauth_token_kind(agent.account.account):
                return
            promote_verified_claude_ambient_auth_from_home(
                home=agent.home,
                account=agent.account.account,
                source="monitor.auto_prime",
            )
        elif agent.provider == "codex":
            from agentos.codex.account_registry import promote_verified_codex_auth_from_home

            promote_verified_codex_auth_from_home(
                home=agent.home,
                account=agent.account.account,
                source="monitor.auto_prime",
            )
    except CliError:
        return


def _validate_prime_ping_result(result, *, expected_number: int | None) -> None:
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.exit_code != 0:
        detail = output.strip()
        suffix = f": {detail}" if detail else ""
        raise CliError(
            f"agent ping failed: provider command exited with {result.exit_code}{suffix}"
        )
    if expected_number is None:
        return
    numbers = [int(match.group(0)) for match in _PING_NUMBER_PATTERN.finditer(output)]
    if expected_number not in numbers:
        raise CliError(
            f"agent ping failed: expected numeric answer {expected_number} "
            "was not present in provider output"
        )


def _required_target_string(target_state: dict[str, object], key: str) -> str:
    value = _string_value(target_state.get(key))
    if value is None:
        raise CliError(f"limits-tracking target state is missing {key}")
    return value


def _target_state_name(target_state: dict[str, object]) -> str:
    provider = _string_value(target_state.get("provider")) or "unknown"
    account = _string_value(target_state.get("account")) or "unknown"
    return f"{provider}/{account}"
