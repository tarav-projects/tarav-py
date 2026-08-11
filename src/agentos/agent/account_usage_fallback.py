# $kw: --from Normalization.Pipeline::Account.Usage.Model
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_status import (
    AccountLimit,
    AccountStatusError,
    registry_fallback_usage_record_metadata,
)
from agentos.agent.session_utils import string_or_none
from agentos.agent.usage_registry import latest_usage_record

AccountUsageReadResult = tuple[
    tuple[AccountLimit, ...],
    tuple[AccountStatusError, ...],
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]


def account_usage_registry_fallback(
    *,
    provider: str,
    account: str,
    home: Path | None,
    source: str,
    parser: Callable[[Mapping[str, Any]], tuple[AccountLimit, ...]],
    live_error: AccountStatusError,
    fallback_to_usage_registry: bool,
) -> AccountUsageReadResult:
    if not fallback_to_usage_registry:
        return (), (live_error,), None, None, None
    if home is None:
        return (), (live_error,), None, None, None
    record = latest_usage_record(
        provider=provider,
        account=account,
        home=home,
        source=source,
    )
    if record is None:
        return (), (live_error,), None, None, None
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return (), (live_error,), None, None, None
    try:
        limits = parser(payload)
    except (CliError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        fallback_error = AccountStatusError(
            error_type="invalid_registry_payload",
            message=str(exc),
        )
        return (), (live_error, fallback_error), None, None, None
    return (
        limits,
        (),
        payload,
        None,
        registry_fallback_usage_record_metadata(
            source=source,
            recorded_at=string_or_none(record.get("recorded_at")),
            live_error=live_error.summary(),
        ),
    )


__all__ = ["AccountUsageReadResult", "account_usage_registry_fallback"]
