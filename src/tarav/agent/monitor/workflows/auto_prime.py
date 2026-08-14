# $kw: --from Account.Management
"""Auto-prime-zero-limits workflow: trigger detection, eligibility, and prime pings."""

from __future__ import annotations

import datetime
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tarav._core.errors import CliError
from tarav.agent.monitor.auto_prime_registry import (
    AUTO_PRIME_EVENT_ATTEMPT_FAILED,
    AUTO_PRIME_EVENT_ATTEMPT_STARTED,
    AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
    AUTO_PRIME_EVENT_ELIGIBLE,
    AUTO_PRIME_EVENT_SKIPPED_ALREADY_PRIMED,
    AUTO_PRIME_EVENT_VERIFICATION_EFFECTIVE,
    AUTO_PRIME_EVENT_VERIFICATION_INEFFECTIVE,
    append_auto_prime_event,
)
from tarav.agent.monitor.clock import (
    AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
    MonitorClockSnapshot,
)
from tarav.agent.monitor.models import (
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
    MonitorFrame,
    MonitorInfoRow,
    MonitorRow,
    MonitorState,
    MonitorWorkflowConfig,
)
from tarav.agent.monitor.workflows.state import (
    AutoPrimeTargetState,
    AutoPrimeWorkflowState,
    LimitsTargetState,
    LimitsWorkflowState,
)
from tarav.agent.monitor.workflows._common import (
    _float_value,
    _format_age_duration,
    _int_value,
    _parse_datetime,
    _string_value,
    _target_key,
)
from tarav.agent.monitor_log import append_monitor_log_event
from tarav.agent.ping import AgentPingResult
from tarav.agent.providers.registry import resolve_account_runtime_agent


_AUTO_PRIME_VERIFICATION_TIMEOUT_SEC = 900.0


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
        workflow_state.setup_tick = frame.tick
        workflow_state.interval_sec = self.config.refresh_interval_sec
        workflow_state.retry_cooldown_sec = self.retry_cooldown_sec
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
        workflow_state.last_tick = frame.tick
        workflow_state.run_count = run_count
        workflow_state.interval_sec = self.config.refresh_interval_sec
        workflow_state.retry_cooldown_sec = self.retry_cooldown_sec
        workflow_state.fired_alarms = list(trigger.fired_alarm_names)
        self._write_config_state(workflow_state)

        if trigger.fired(AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM):
            self._scan_and_prime(state, workflow_state=workflow_state, tick=frame.tick)

        self._write_frame_block(frame, workflow_state=workflow_state)

    def _workflow_state(self, state: MonitorState) -> AutoPrimeWorkflowState:
        existing = state.data.get(self.name)
        if isinstance(existing, AutoPrimeWorkflowState):
            return existing
        workflow_state = AutoPrimeWorkflowState()
        state.data[self.name] = workflow_state
        return workflow_state

    def _write_config_state(self, workflow_state: AutoPrimeWorkflowState) -> None:
        workflow_state.loaded_at = self.config.loaded_at
        workflow_state.config_fingerprint = self.config.config_fingerprint
        workflow_state.target_summary = [
            target.summary() for target in self.config.targets
        ]
        workflow_state.target_limit_ids = {
            provider: tuple(sorted(limit_ids))
            for provider, limit_ids in self.target_limit_ids.items()
        }
        workflow_state.triggers = {
            provider: tuple(sorted(trigger_names))
            for provider, trigger_names in self.triggers.items()
        }

    def _scan_and_prime(
        self,
        state: MonitorState,
        *,
        workflow_state: AutoPrimeWorkflowState,
        tick: int,
    ) -> None:
        limits_state = state.data.get(LIMITS_TRACKING_WORKFLOW)
        if not isinstance(limits_state, LimitsWorkflowState):
            workflow_state.last_scan = {
                "tick": tick,
                "status": "skipped",
                "message": "limits-tracking state is not available",
                "pinged": 0,
                "failed": 0,
            }
            return

        scan_at = datetime.datetime.now(tz=datetime.UTC)
        monotonic_now = time.monotonic()
        pinged = 0
        failed = 0
        for target_key, raw_target_state in limits_state.targets.items():
            if target_key not in self.target_keys:
                continue
            target_state = self._target_state(
                workflow_state, raw_target_state, target_key
            )
            target_state.last_decisions = []
            target_state.last_decision = None
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
        workflow_state.last_scan = {
            "tick": tick,
            "status": "ok",
            "pinged": pinged,
            "failed": failed,
        }

    def _target_state(
        self,
        workflow_state: AutoPrimeWorkflowState,
        source_target_state: LimitsTargetState,
        target_key: str,
    ) -> AutoPrimeTargetState:
        existing = workflow_state.targets.get(target_key)
        if existing is not None:
            return existing
        target_state = AutoPrimeTargetState(
            provider=source_target_state.provider,
            account=source_target_state.account,
            home=source_target_state.home,
            profile=source_target_state.profile,
            start_path=source_target_state.start_path,
        )
        workflow_state.targets[target_key] = target_state
        return target_state

    def _eligible_periods(
        self,
        source_target_state: LimitsTargetState,
        *,
        target_state: AutoPrimeTargetState,
        scan_at: datetime.datetime,
        monotonic_now: float,
        tick: int | None = None,
    ) -> list[dict[str, object]]:
        if source_target_state.status != "ok":
            return []
        target_limit_ids = self.target_limit_ids.get(source_target_state.provider)
        if not target_limit_ids:
            return []
        trigger_names = self.triggers.get(source_target_state.provider)
        if not trigger_names:
            return []
        retry_after = target_state.retry_after_monotonic
        if retry_after is not None and monotonic_now < retry_after:
            self._record_retry_blocked_decisions(
                source_target_state,
                target_state=target_state,
                target_limit_ids=target_limit_ids,
                retry_after_monotonic=float(retry_after),
                tick=tick,
            )
            return []

        account_status = source_target_state.account_status
        if not isinstance(account_status, dict):
            return []
        limits = account_status.get("limits")
        if not isinstance(limits, list):
            return []
        primed_periods = target_state.primed_periods
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
                observations=target_state.observations,
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

    def _prime_target(
        self,
        target_state: AutoPrimeTargetState,
        *,
        source_target_state: LimitsTargetState,
        eligible_periods: list[dict[str, object]],
        tick: int,
        monotonic_now: float,
        scan_at: datetime.datetime,
    ) -> bool:
        target_state.last_attempt_tick = tick
        for period in eligible_periods:
            self._record_period_event(
                AUTO_PRIME_EVENT_ATTEMPT_STARTED,
                source_target_state=source_target_state,
                period=period,
                tick=tick,
            )
        try:
            result = _run_account_prime_ping(source_target_state)
        except Exception as exc:

            self._record_prime_failure(
                target_state,
                source_target_state=source_target_state,
                eligible_periods=eligible_periods,
                tick=tick,
                monotonic_now=monotonic_now,
                message=str(exc),
                error_type=type(exc).__name__,
            )
            return False
        if not result.ok:

            self._record_prime_failure(
                target_state,
                source_target_state=source_target_state,
                eligible_periods=eligible_periods,
                tick=tick,
                monotonic_now=monotonic_now,
                message=result.failure or "agent ping failed",
                error_type="ping-failed",
            )
            return False

        target_state.last_success_tick = tick
        target_state.retry_after_monotonic = None
        target_state.last_error = None
        primed_periods = target_state.primed_periods
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
                "ping_model": result.model,
                "ping_elapsed_ms": result.elapsed_ms,
            }
            self._record_period_event(
                AUTO_PRIME_EVENT_ATTEMPT_SUCCEEDED,
                source_target_state=source_target_state,
                period=period,
                tick=tick,
                status=AUTO_PRIME_VERIFICATION_PENDING,
                extra={
                    "attempt_count": attempt_count,
                    "ping_model": result.model,
                    "ping_elapsed_ms": result.elapsed_ms,
                },
            )
        return True

    def _record_prime_failure(
        self,
        target_state: AutoPrimeTargetState,
        *,
        source_target_state: LimitsTargetState,
        eligible_periods: list[dict[str, object]],
        tick: int,
        monotonic_now: float,
        message: str,
        error_type: str,
    ) -> None:
        target_state.retry_after_monotonic = monotonic_now + self.retry_cooldown_sec
        target_state.last_error = {
            "message": message,
            "error_type": error_type,
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
                error={"type": error_type, "message": message},
            )

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
        source_target_state: LimitsTargetState,
        *,
        target_state: AutoPrimeTargetState,
        target_limit_ids: set[str],
        retry_after_monotonic: float,
        tick: int | None,
    ) -> None:
        account_status = source_target_state.account_status
        if not isinstance(account_status, dict):
            return
        limits = account_status.get("limits")
        if not isinstance(limits, list):
            return
        primed_periods = target_state.primed_periods
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            limit_id = _string_value(limit.get("limit_id"))
            if limit_id is None or limit_id not in target_limit_ids:
                continue
            period_key = _uninitialized_period_key(source_target_state, limit_id)
            existing = primed_periods.get(period_key)
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
        target_state: AutoPrimeTargetState,
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
        target_state.last_decisions.append(decision)
        existing = target_state.last_decision
        if existing is None or _decision_priority(decision) >= _decision_priority(
            existing
        ):
            target_state.last_decision = decision
        self._log_decision_error(target_state, decision=decision, action=action)

    @staticmethod
    def _log_decision_error(
        target_state: AutoPrimeTargetState,
        *,
        decision: dict[str, object],
        action: str,
    ) -> None:
        event = {
            "ping failed": "auto_prime_failed",
            "retry": "auto_prime_retry_blocked",
        }.get(action)
        if event is None:
            return
        append_monitor_log_event(
            event=event,
            tick=decision.get("tick") if isinstance(decision.get("tick"), int) else None,
            provider=target_state.provider,
            account=target_state.account,
            home=target_state.home,
            payload={
                "limit_id": decision.get("limit_id"),
                "classification": decision.get("classification"),
                "period_key": decision.get("period_key"),
                "trigger_reasons": list(decision.get("trigger_reasons", ()))
                or None,
                "retry_after_monotonic": decision.get("retry_after_monotonic"),
            },
        )

    def _verify_existing_primes(
        self,
        source_target_state: LimitsTargetState,
        *,
        target_state: AutoPrimeTargetState,
        scan_at: datetime.datetime,
        tick: int,
    ) -> None:
        if source_target_state.status != "ok":
            return
        account_status = source_target_state.account_status
        if not isinstance(account_status, dict):
            return
        limits = account_status.get("limits")
        if not isinstance(limits, list):
            return
        primed_periods = target_state.primed_periods
        if not primed_periods:
            return
        observed_at = _observation_time(source_target_state, fallback=scan_at)
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            limit_id = _string_value(limit.get("limit_id"))
            if limit_id is None:
                continue
            period_key = _uninitialized_period_key(source_target_state, limit_id)
            existing = primed_periods.get(period_key)
            if existing is None:
                continue
            if existing.get("verification_status") == AUTO_PRIME_VERIFICATION_EFFECTIVE:
                continue
            trigger_names = self.triggers.get(source_target_state.provider, set())
            reasons = _uninitialized_trigger_reasons(
                source_target_state,
                limit,
                trigger_names=trigger_names,
                observations=target_state.observations,
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
        source_target_state: LimitsTargetState,
        period: dict[str, object],
        tick: int | None,
        status: object = None,
        error: Mapping[str, object] | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        append_auto_prime_event(
            event_type,
            provider=source_target_state.provider,
            account=source_target_state.account,
            home=source_target_state.home,
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
        self, frame: MonitorFrame, *, workflow_state: AutoPrimeWorkflowState
    ) -> None:
        rows: list[MonitorRow] = []
        last_scan = workflow_state.last_scan
        if last_scan is not None:
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
        for target_state in workflow_state.targets.values():
            last_error = target_state.last_error
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
            and workflow_state.setup_tick is None
            and workflow_state.last_scan is None
        ):
            return
        data = {
            "workflow": self.name,
            "periodic_alarm_name": AUTO_PRIME_ZERO_LIMITS_PERIODIC_ALARM,
            "interval_sec": self.config.refresh_interval_sec,
            "retry_cooldown_sec": self.retry_cooldown_sec,
            "loaded_at": workflow_state.loaded_at,
            "config_fingerprint": workflow_state.config_fingerprint,
            "target_summary": workflow_state.target_summary,
            "target_limit_ids": workflow_state.target_limit_ids,
            "triggers": workflow_state.triggers,
            "run_count": workflow_state.run_count,
            "last_scan": last_scan,
            "targets": {
                key: target.payload()
                for key, target in workflow_state.targets.items()
            },
        }
        frame.add_block(self.name, rows=rows, data=data)


def _auto_prime_target_state(
    state: MonitorState, *, target_key: str
) -> AutoPrimeTargetState | None:
    workflow_state = state.data.get(AUTO_PRIME_ZERO_LIMITS_WORKFLOW)
    if not isinstance(workflow_state, AutoPrimeWorkflowState):
        return None
    return workflow_state.targets.get(target_key)


def _auto_prime_status_part(target_state: AutoPrimeTargetState | None) -> str | None:
    if target_state is None:
        return None
    decision_part = _auto_prime_decision_status_part(target_state.last_decision)
    if decision_part is not None:
        return decision_part
    if target_state.last_error is not None:
        return "prime failed"
    primed_periods = target_state.primed_periods
    retry_after_monotonic = _auto_prime_retry_after_monotonic(
        target_state,
        primed_periods=primed_periods,
    )

    has_ineffective = False
    has_pending = False
    has_effective = False
    for primed_period in primed_periods.values():
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
    target_state: AutoPrimeTargetState,
    *,
    primed_periods: dict[str, dict[str, object]],
) -> float | None:
    retry_after_monotonic = target_state.retry_after_monotonic
    for primed_period in primed_periods.values():
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


def _observation_time(
    source_target_state: LimitsTargetState, *, fallback: datetime.datetime
) -> datetime.datetime:
    account_status = source_target_state.account_status
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


@dataclass(frozen=True)
class _LimitPeriod:
    limit_id: str
    usage_over_time: dict[str, object]
    used_percent: int | None
    period_key: str
    period_end: datetime.datetime
    uninitialized_period_key: str


def _parse_limit_period(
    source_target_state: LimitsTargetState,
    limit: dict[str, object],
    *,
    now: datetime.datetime,
) -> _LimitPeriod | None:
    limit_id = _string_value(limit.get("limit_id"))
    usage_over_time = limit.get("usage_over_time")
    if limit_id is None or not isinstance(usage_over_time, dict):
        return None
    period_started_at = _string_value(usage_over_time.get("period_started_at"))
    period_ends_at = _string_value(usage_over_time.get("period_ends_at"))
    resets_at = _string_value(usage_over_time.get("resets_at"))
    period_end_key = period_ends_at or resets_at
    if period_started_at is None or period_end_key is None:
        return None
    period_end = _parse_datetime(period_end_key)
    if period_end is None or period_end <= now:
        return None
    provider = source_target_state.provider
    account = source_target_state.account
    home = source_target_state.home
    if provider is None or account is None or home is None:
        return None
    return _LimitPeriod(
        limit_id=limit_id,
        usage_over_time=usage_over_time,
        used_percent=_int_value(usage_over_time.get("used_percent")),
        period_key="|".join(
            (provider, account, home, limit_id, period_started_at, period_end_key)
        ),
        period_end=period_end,
        uninitialized_period_key="|".join(
            (provider, account, home, limit_id, "uninitialized")
        ),
    )


def _parsed_trigger_reasons(
    parsed: _LimitPeriod,
    limit: dict[str, object],
    *,
    trigger_names: set[str],
    observations: dict[str, object],
    now: datetime.datetime,
) -> tuple[str, ...]:
    previous_observation = observations.get(parsed.limit_id)
    return _auto_prime_trigger_reasons(
        limit,
        parsed.usage_over_time,
        used_percent=parsed.used_percent,
        trigger_names=trigger_names,
        previous_observation=previous_observation
        if isinstance(previous_observation, dict)
        else None,
        period_key=parsed.period_key,
        period_end=parsed.period_end,
        now=now,
    )


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
    parsed = _parse_limit_period(source_target_state, limit, now=now)
    if parsed is None or parsed.limit_id not in target_limit_ids:
        return None
    reasons = _parsed_trigger_reasons(
        parsed,
        limit,
        trigger_names=trigger_names,
        observations=observations,
        now=now,
    )
    observations[parsed.limit_id] = {
        "period_key": parsed.period_key,
        "period_end": parsed.period_end.isoformat(),
        "observed_at": now.isoformat(),
        "used_percent": parsed.used_percent,
        "remaining_ratio": _remaining_window_ratio(
            limit, parsed.usage_over_time, parsed.period_end, now
        ),
    }
    if not reasons:
        return None

    uninitialized = any(
        reason in AUTO_PRIME_UNINITIALIZED_TRIGGERS for reason in reasons
    )
    return {
        "limit_id": parsed.limit_id,
        "period_key": parsed.uninitialized_period_key
        if uninitialized
        else parsed.period_key,
        "trigger_reasons": reasons,
        "uninitialized": uninitialized,
        "observed_at": now.isoformat(),
        "scan_at": scan_at.isoformat(),
    }


def _uninitialized_period_key(
    source_target_state: LimitsTargetState, limit_id: str
) -> str:
    return "|".join(
        (
            source_target_state.provider or "",
            source_target_state.account or "",
            source_target_state.home or "",
            limit_id,
            "uninitialized",
        )
    )


def _uninitialized_trigger_reasons(
    source_target_state: LimitsTargetState,
    limit: dict[str, object],
    *,
    trigger_names: set[str],
    observations: dict[str, object],
    now: datetime.datetime,
) -> tuple[str, ...]:
    parsed = _parse_limit_period(source_target_state, limit, now=now)
    if parsed is None:
        return ()
    reasons = _parsed_trigger_reasons(
        parsed,
        limit,
        trigger_names=trigger_names,
        observations=observations,
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


def _run_account_prime_ping(source_target_state: LimitsTargetState) -> AgentPingResult:
    provider = _required_target_string(source_target_state.provider, "provider")
    account = _required_target_string(source_target_state.account, "account")
    home = Path(_required_target_string(source_target_state.home, "home"))
    profile = source_target_state.profile
    start_path = Path(source_target_state.start_path or ".")
    agent = resolve_account_runtime_agent(
        provider=provider,
        account=account,
        home=home,
        profile=profile,
        start_path=start_path,
    )





    return agent.ping(cwd=Path.cwd().resolve())


def _required_target_string(value: str | None, key: str) -> str:
    if not value:
        raise CliError(f"limits-tracking target state is missing {key}")
    return value


def _target_state_name(target_state: AutoPrimeTargetState) -> str:
    provider = target_state.provider or "unknown"
    account = target_state.account or "unknown"
    return f"{provider}/{account}"
