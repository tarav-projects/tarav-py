from __future__ import annotations

import base64
import datetime
import hashlib
import io
import json
from pathlib import Path
from threading import Event

import pytest

from _helpers import set_fake_agentos_home as _set_fake_agentos_home
from _helpers import write_text_file as _write
from agentos.agent.account_status import (
    AccountIdentity,
    AccountLimit,
    AccountStatus,
    AccountStatusError,
    AgentAccountContext,
    UsageOverTimeLimitData,
)
from agentos.agent.providers import build_registered_account_agent
from agentos.cli import main


def _jwt(payload: dict[str, object]) -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return ".".join([encode({"alg": "none"}), encode(payload), "signature"])


def _auth_json(
    *,
    account_id: str = "acc_123",
    email: str = "person@example.com",
    last_refresh: str = "2026-05-12T17:00:07Z",
    iat: int = 1_776_000_000,
) -> str:
    return (
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {
                    "id_token": _jwt({"email": email, "iat": iat}),
                    "access_token": _jwt({"iat": iat}),
                    "refresh_token": "secret-refresh-token",
                    "account_id": account_id,
                },
                "last_refresh": last_refresh,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        assert isinstance(payload, dict)
        entries.append(payload)
    return entries


def _usage_registry_entries(agentos_home: Path) -> list[dict[str, object]]:
    registry_root = agentos_home / "agent" / "usage-registry"
    entries: list[dict[str, object]] = []
    for path in sorted(registry_root.glob("*-usage.jsonl")):
        entries.extend(_read_jsonl(path))
    return entries


def _register_args(
    auth_file: Path, *, account: str = "br", register_only: bool = False
) -> list[str]:
    args = [
        "agent",
        "accounts",
        "register",
        "--provider",
        "codex",
        "--account",
        account,
        "--auth-file",
        str(auth_file),
    ]
    if register_only:
        args.append("--register-only")
    return args


def _link_args(
    home: Path, *, account: str = "br", force: bool = False, json_output: bool = False
) -> list[str]:
    args = [
        "agent",
        "accounts",
        "link",
        "--provider",
        "codex",
        "--account",
        account,
        "--home",
        str(home),
    ]
    if force:
        args.append("--force")
    if json_output:
        args.append("--json")
    return args


def _status_args(
    home: Path, *, json_output: bool = True, provider: str = "codex"
) -> list[str]:
    args = [
        "agent",
        "accounts",
        "status",
        "--provider",
        provider,
        "--home",
        str(home),
    ]
    if json_output:
        args.append("--json")
    return args


def _registry_status_args(
    *, provider: str | None = None, json_output: bool = True
) -> list[str]:
    args = ["agent", "accounts", "status"]
    if provider is not None:
        args.extend(["--provider", provider])
    if json_output:
        args.append("--json")
    return args


def _claude_register_args(
    *,
    account: str = "main",
    email: str | None = "person@example.com",
    label: str | None = None,
) -> list[str]:
    args = [
        "agent",
        "accounts",
        "register",
        "--provider",
        "claude-code",
        "--account",
        account,
    ]
    if email is not None:
        args.extend(["--email", email])
    if label is not None:
        args.extend(["--label", label])
    return args


def _write_monitor_config(agentos_home: Path, monitor: list[dict[str, object]]) -> None:
    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {
                    "accounts": {
                        "monitor": monitor,
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def _assert_no_old_codex_layout(provider_root: Path) -> None:
    assert not (provider_root / "registry.jsonl").exists()
    assert not (provider_root / "files").exists()
    assert not (provider_root / "accounts" / "br" / "manifest.json").exists()
    assert not (provider_root / "accounts" / "br" / "auth.json").exists()


def _registered_linked_codex_home(
    tmp_path: Path,
    monkeypatch,
    capsys,
    *,
    account_id: str = "acc_123",
) -> Path:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {
                    "providers": {
                        "codex": {
                            "cli_command": ["/opt/homebrew/bin/codex"],
                        },
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex-home"
    _write(source_auth, _auth_json(account_id=account_id))

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home)) == 0
    capsys.readouterr()
    return target_home


def _registered_linked_claude_home(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> Path:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    claude_home = tmp_path / "claude-home"
    claude_home.mkdir()
    _write(
        claude_home / ".claude.json",
        json.dumps(
            {
                "oauthAccount": {
                    "accountUuid": "claude-account-id",
                    "emailAddress": "person@example.com",
                    "displayName": "Claude Person",
                }
            }
        )
        + "\n",
    )
    assert main(_claude_register_args(label="Claude main")) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "claude-code",
                "--account",
                "main",
                "--home",
                str(claude_home),
            ]
        )
        == 0
    )
    capsys.readouterr()
    return claude_home


def _claude_usage_get_agent(tmp_path: Path, monkeypatch):
    from agentos.claude.agent import ClaudeAgent

    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    return ClaudeAgent(
        home=tmp_path / "claude-home",
        account=AgentAccountContext(provider="claude-code", account="main"),
    )


def _claude_usage_get_payload(
    *,
    utilization: int,
    resets_at: str = "2026-05-15T20:29:59Z",
) -> dict[str, object]:
    return {
        "five_hour": {
            "utilization": utilization,
            "resets_at": resets_at,
        }
    }


def _claude_statusline_payload(
    *,
    burst_used: int = 20,
    weekly_used: int | None = None,
) -> dict[str, object]:
    rate_limits: dict[str, object] = {
        "five_hour": {
            "used_percentage": burst_used,
            "resets_at": 1_776_000_000,
        }
    }
    if weekly_used is not None:
        rate_limits["seven_day"] = {
            "used_percentage": weekly_used,
            "resets_at": 1_776_604_800,
        }
    return {"rate_limits": rate_limits}


def _codex_usage_payload(
    *,
    burst_used: int = 3,
    weekly_used: int = 1,
) -> dict[str, object]:
    return {
        "rateLimitsByLimitId": {
            "test-limit": {
                "primary": {
                    "usedPercent": burst_used,
                    "windowDurationMins": 300,
                    "resetsAt": 1_776_000_000,
                },
                "secondary": {
                    "usedPercent": weekly_used,
                    "windowDurationMins": 10080,
                    "resetsAt": 1_776_604_800,
                },
            }
        }
    }


def _append_claude_usage_get_record(agent, *, utilization: int = 20) -> None:
    from agentos.agent.usage_registry import append_usage_record

    append_usage_record(
        provider="claude-code",
        account="main",
        home=agent.home,
        source="oauth_usage_get",
        payload=_claude_usage_get_payload(utilization=utilization),
    )


def _append_claude_statusline_record(agent, *, burst_used: int = 20) -> None:
    from agentos.agent.usage_registry import append_usage_record

    append_usage_record(
        provider="claude-code",
        account="main",
        home=agent.home,
        source="statusline_rate_limits",
        payload=_claude_statusline_payload(burst_used=burst_used),
    )


def _claude_usage_http_429_error(
    *,
    retry_after_sec: int | None = None,
    retry_after_until: str | None = None,
) -> AccountStatusError:
    detail: dict[str, object] = {"status": 429}
    if retry_after_sec is not None:
        detail["retry_after_sec"] = retry_after_sec
    if retry_after_until is not None:
        detail["retry_after_until"] = retry_after_until
    return AccountStatusError(
        error_type="usage_api_http_error",
        message="claude usage API returned HTTP 429",
        exit_code=429,
        detail=detail,
    )


def _future_iso(minutes: int) -> str:
    return _iso_z(
        datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(minutes=minutes)
    )


def _monitor_account_status(
    *,
    provider: str,
    account: str,
    home: Path,
    usage_record: dict[str, object] | None = None,
) -> AccountStatus:
    burst_started_at, burst_ends_at = _usage_period(
        duration_mins=300, elapsed_percent=37
    )
    weekly_started_at, weekly_ends_at = _usage_period(
        duration_mins=10_080, elapsed_percent=18
    )
    return AccountStatus(
        provider=provider,
        account=account,
        home=home,
        check_status="ok",
        usage_status="ok",
        link_state="verified",
        expected_identity=AccountIdentity(provider_account_id=f"acc_{account}"),
        fetched_identity=AccountIdentity(provider_account_id=f"acc_{account}"),
        identity_match="verified",
        usage_summary="5 hours 3%, 168 hours 1%",
        raw={
            "usage_record": usage_record
            if usage_record is not None
            else {
                "status": "fresh",
                "recorded_at": None,
                "source": "app_server",
            }
        },
        limits=(
            AccountLimit(
                limit_class="usage_over_time",
                limit_name="5h",
                limit_label="5 hours",
                usage_over_time=UsageOverTimeLimitData(
                    used_percent=3,
                    period_started_at=burst_started_at,
                    period_ends_at=burst_ends_at,
                    period_duration_mins=300,
                    resets_at=burst_ends_at,
                ),
            ),
            AccountLimit(
                limit_class="usage_over_time",
                limit_name="168h",
                limit_label="168 hours",
                usage_over_time=UsageOverTimeLimitData(
                    used_percent=1,
                    period_started_at=weekly_started_at,
                    period_ends_at=weekly_ends_at,
                    period_duration_mins=10_080,
                    resets_at=weekly_ends_at,
                ),
            ),
        ),
    )


def _usage_period(*, duration_mins: int, elapsed_percent: int) -> tuple[str, str]:
    now = datetime.datetime.now(tz=datetime.UTC)
    duration = datetime.timedelta(minutes=duration_mins)
    elapsed = duration * (elapsed_percent / 100)
    started_at = now - elapsed
    ends_at = started_at + duration
    return _iso_z(started_at), _iso_z(ends_at)


def _iso_z(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


def _stub_monitor_account_status(
    monkeypatch,
    *,
    failures: set[str] | None = None,
    usage_records: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    import agentos.agent.monitor.workflows as monitor_workflows

    calls: list[str] = []
    failed_targets = set() if failures is None else failures
    usage_record_by_target = {} if usage_records is None else usage_records

    class FakeAgent:
        def __init__(self, *, provider: str, account: str, home: Path) -> None:
            self.provider = provider
            self.account = account
            self.home = home

        def account_status(
            self,
            *,
            record_usage: bool = True,
            fallback_to_usage_registry: bool = True,
        ) -> AccountStatus:
            del record_usage, fallback_to_usage_registry
            key = f"{self.provider}/{self.account}@{self.home}"
            calls.append(key)
            if key in failed_targets:
                raise RuntimeError(f"cannot refresh {self.account}")
            return _monitor_account_status(
                provider=self.provider,
                account=self.account,
                home=self.home,
                usage_record=usage_record_by_target.get(key),
            )

    def fake_build_registered_account_agent(
        *, provider: str, account: str, home: Path, start_path: Path | str = "."
    ):
        del start_path
        return FakeAgent(provider=provider, account=account, home=Path(home))

    monkeypatch.setattr(
        monitor_workflows,
        "build_registered_account_agent",
        fake_build_registered_account_agent,
    )
    return calls


def test_agent_accounts_register_codex_writes_consolidated_registry(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "named-anything.json"
    auth_text = _auth_json()
    auth_sha = _sha(auth_text)
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact_appended"] is True
    assert payload["account_record"]["active_artifact_id"] == auth_sha
    assert "secret-refresh-token" not in json.dumps(payload)

    provider_root = agentos_home / "accounts" / "codex"
    assert (provider_root / "artifacts" / f"{auth_sha}.auth.json").read_text(
        encoding="utf-8"
    ) == auth_text
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["br"]["provider"] == "codex"
    assert accounts["accounts"]["br"]["account_id"] == "acc_123"
    assert accounts["accounts"]["br"]["email"] == "person@example.com"
    assert accounts["accounts"]["br"]["active_artifact_id"] == auth_sha
    artifacts = _read_jsonl(provider_root / "artifacts.jsonl")
    assert len(artifacts) == 1
    assert artifacts[0]["account"] == "br"
    assert artifacts[0]["artifact_id"] == auth_sha
    assert artifacts[0]["file"] == f"artifacts/{auth_sha}.auth.json"
    _assert_no_old_codex_layout(provider_root)


def test_account_status_model_serializes_expected_shape(tmp_path: Path) -> None:
    from agentos.agent.account_status import (
        AccountIdentity,
        AccountLimit,
        AccountStatus,
        UsageOverTimeLimitData,
    )

    status = AccountStatus(
        provider="codex",
        account="br",
        home=tmp_path / "codex-home",
        check_status="ok",
        usage_status="ok",
        link_state="verified",
        expected_identity=AccountIdentity(provider_account_id="acc_123"),
        fetched_identity=AccountIdentity(provider_account_id="acc_123"),
        identity_match="verified",
        auth_summary="Logged in using ChatGPT",
        usage_summary="5 hours 30%",
        limits=(
            AccountLimit(
                limit_class="usage_over_time",
                limit_name="5h",
                limit_label="5 hours",
                usage_over_time=UsageOverTimeLimitData(
                    used_percent=30,
                    period_started_at="2026-05-12T12:00:00Z",
                    period_ends_at="2026-05-12T17:00:00Z",
                    period_duration_mins=300,
                    resets_at="2026-05-12T17:00:00Z",
                ),
                provider_limit={"window_key": "primary"},
            ),
        ),
    )

    assert status.summary() == {
        "provider": "codex",
        "account": "br",
        "home": str(tmp_path / "codex-home"),
        "check_status": "ok",
        "usage_status": "ok",
        "link_state": "verified",
        "expected_identity": {"provider_account_id": "acc_123"},
        "fetched_identity": {"provider_account_id": "acc_123"},
        "identity_match": "verified",
        "auth_summary": "Logged in using ChatGPT",
        "usage_summary": "5 hours 30%",
        "limits": [
            {
                "limit_class": "usage_over_time",
                "limit_name": "5h",
                "limit_label": "5 hours",
                "usage_over_time": {
                    "used_percent": 30,
                    "period_started_at": "2026-05-12T12:00:00Z",
                    "period_ends_at": "2026-05-12T17:00:00Z",
                    "period_duration_mins": 300,
                    "resets_at": "2026-05-12T17:00:00Z",
                },
                "provider_limit": {"window_key": "primary"},
            }
        ],
        "errors": [],
        "usage_errors": [],
    }


def test_agent_accounts_register_same_artifact_is_noop(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "auth.json"
    auth_text = _auth_json(account_id="acc_123")
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    assert json.loads(capsys.readouterr().out)["artifact_appended"] is True
    assert main(_register_args(source_auth)) == 0
    assert json.loads(capsys.readouterr().out)["artifact_appended"] is False

    artifacts = _read_jsonl(agentos_home / "accounts" / "codex" / "artifacts.jsonl")
    assert [entry["artifact_id"] for entry in artifacts] == [_sha(auth_text)]


def test_agent_accounts_register_new_hash_updates_active_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first_auth = tmp_path / "first.json"
    second_auth = tmp_path / "second.json"
    first_text = _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000)
    second_text = _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000)
    _write(first_auth, first_text)
    _write(second_auth, second_text)

    assert main(_register_args(first_auth)) == 0
    capsys.readouterr()
    assert main(_register_args(second_auth)) == 0
    capsys.readouterr()

    provider_root = agentos_home / "accounts" / "codex"
    artifacts = _read_jsonl(provider_root / "artifacts.jsonl")
    assert [entry["artifact_id"] for entry in artifacts] == [
        _sha(first_text),
        _sha(second_text),
    ]
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["br"]["active_artifact_id"] == _sha(second_text)
    assert (provider_root / "artifacts" / f"{_sha(first_text)}.auth.json").read_text(
        encoding="utf-8"
    ) == first_text
    assert (provider_root / "artifacts" / f"{_sha(second_text)}.auth.json").read_text(
        encoding="utf-8"
    ) == second_text


def test_agent_accounts_register_only_preserves_active_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    active_auth = tmp_path / "active.json"
    archived_auth = tmp_path / "archived.json"
    active_text = _auth_json(last_refresh="2026-05-12T00:00:00Z", iat=1_776_000_000)
    archived_text = _auth_json(last_refresh="2026-05-01T00:00:00Z", iat=1_775_000_000)
    _write(active_auth, active_text)
    _write(archived_auth, archived_text)

    assert main(_register_args(active_auth)) == 0
    capsys.readouterr()
    assert main(_register_args(archived_auth, register_only=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["register_only"] is True
    assert payload["artifact_appended"] is True

    provider_root = agentos_home / "accounts" / "codex"
    artifacts = _read_jsonl(provider_root / "artifacts.jsonl")
    assert [entry["artifact_id"] for entry in artifacts] == [
        _sha(active_text),
        _sha(archived_text),
    ]
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["br"]["active_artifact_id"] == _sha(active_text)
    assert (
        accounts["accounts"]["br"]["artifact_file"]
        == f"artifacts/{_sha(active_text)}.auth.json"
    )
    assert (provider_root / "artifacts" / f"{_sha(archived_text)}.auth.json").read_text(
        encoding="utf-8"
    ) == archived_text


def test_agent_accounts_register_only_new_account_has_no_active_artifact(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    auth_text = _auth_json()
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth, register_only=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["register_only"] is True
    assert payload["account_record"]["active_artifact_id"] is None

    provider_root = agentos_home / "accounts" / "codex"
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["br"]["active_artifact_id"] is None
    assert "artifact_file" not in accounts["accounts"]["br"]
    artifacts = _read_jsonl(provider_root / "artifacts.jsonl")
    assert artifacts[0]["artifact_id"] == _sha(auth_text)


def test_agent_accounts_register_refuses_account_id_mismatch_without_touching_current(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first_auth = tmp_path / "first.json"
    second_auth = tmp_path / "second.json"
    first_text = _auth_json(account_id="acc_123")
    second_text = _auth_json(account_id="acc_999")
    _write(first_auth, first_text)
    _write(second_auth, second_text)

    assert main(_register_args(first_auth)) == 0
    capsys.readouterr()
    assert main(_register_args(second_auth)) == 1
    assert "is already registered for account_id acc_123" in capsys.readouterr().err

    provider_root = agentos_home / "accounts" / "codex"
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["br"]["active_artifact_id"] == _sha(first_text)
    artifacts = _read_jsonl(provider_root / "artifacts.jsonl")
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_id"] == _sha(first_text)
    assert not (provider_root / "artifacts" / f"{_sha(second_text)}.auth.json").exists()


def test_agent_accounts_link_writes_home_auth_and_link_registry(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    auth_text = _auth_json()
    auth_sha = _sha(auth_text)
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home, json_output=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "artifact"
    assert payload["copied_auth"]["artifact_id"] == auth_sha
    assert (target_home / "auth.json").read_text(encoding="utf-8") == auth_text

    links = _read_json(agentos_home / "accounts" / "codex" / "links.json")
    link = links["links"][str(target_home.resolve())]
    assert link["account"] == "br"
    assert link["kind"] == "artifact"
    assert link["artifact_id"] == auth_sha

    assert (
        main(
            [
                "stdlib",
                "utils",
                "cmd-logger",
                "query",
                "--event-type",
                "agent.accounts.link",
                "--json",
            ]
        )
        == 0
    )
    log_payload = json.loads(capsys.readouterr().out)
    assert log_payload["count"] == 1
    event_payload = log_payload["events"][0]["payload"]
    assert event_payload["provider"] == "codex"
    assert event_payload["account"] == "br"
    assert event_payload["home"] == str(target_home.resolve())
    assert event_payload["kind"] == "artifact"
    assert event_payload["force"] is False
    assert event_payload["artifact_id"] == auth_sha
    assert event_payload["previous_link"] is None


def test_agent_accounts_link_default_output_is_short_status_message(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home)) == 0
    output = capsys.readouterr().out

    assert output == (
        f"Linked codex account br to {target_home.resolve()} "
        f"(auth copied to {target_home.resolve() / 'auth.json'}).\n"
    )


def test_agent_accounts_link_registers_known_current_auth_before_switching(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    br_source_auth = tmp_path / "br-source.json"
    jp_source_auth = tmp_path / "jp-source.json"
    target_home = tmp_path / "codex"
    old_br_auth = _auth_json(
        account_id="acc_br", email="br@example.com", last_refresh="2026-05-01T00:00:00Z"
    )
    current_br_auth = _auth_json(
        account_id="acc_br", email="br@example.com", last_refresh="2026-05-02T00:00:00Z"
    )
    jp_auth = _auth_json(
        account_id="acc_jp", email="jp@example.com", last_refresh="2026-05-03T00:00:00Z"
    )
    _write(br_source_auth, old_br_auth)
    _write(jp_source_auth, jp_auth)
    _write(target_home / "auth.json", current_br_auth)

    assert main(_register_args(br_source_auth, account="br")) == 0
    capsys.readouterr()
    assert main(_register_args(jp_source_auth, account="jp")) == 0
    capsys.readouterr()
    assert main(_link_args(target_home, account="jp", json_output=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target_before_link"]["account"] == "br"
    assert payload["target_before_link"]["action"] == "registered"
    assert (target_home / "auth.json").read_text(encoding="utf-8") == jp_auth

    provider_root = agentos_home / "accounts" / "codex"
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["br"]["active_artifact_id"] == _sha(current_br_auth)
    assert accounts["accounts"]["jp"]["active_artifact_id"] == _sha(jp_auth)
    artifacts = _read_jsonl(provider_root / "artifacts.jsonl")
    assert {entry["artifact_id"] for entry in artifacts} == {
        _sha(old_br_auth),
        _sha(current_br_auth),
        _sha(jp_auth),
    }


def test_agent_accounts_link_refuses_unknown_current_auth_without_force(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    unknown_auth = _auth_json(account_id="acc_unknown")
    _write(source_auth, _auth_json(account_id="acc_123"))
    _write(target_home / "auth.json", unknown_auth)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home)) == 1
    error_output = capsys.readouterr().err
    assert "refusing to replace unregistered codex auth" in error_output
    assert "--auth-file" in error_output
    assert (target_home / "auth.json").read_text(encoding="utf-8") == unknown_auth


def test_agent_accounts_link_force_overwrites_unknown_and_broken_auth(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    unknown_home = tmp_path / "codex-unknown"
    broken_home = tmp_path / "codex-broken"
    auth_text = _auth_json(account_id="acc_123")
    _write(source_auth, auth_text)
    _write(unknown_home / "auth.json", _auth_json(account_id="acc_unknown"))
    _write(broken_home / "auth.json", "{not-json\n")

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(unknown_home, force=True, json_output=True)) == 0
    assert (
        json.loads(capsys.readouterr().out)["target_before_link"]["classification"]
        == "unknown"
    )
    assert (unknown_home / "auth.json").read_text(encoding="utf-8") == auth_text
    assert main(_link_args(broken_home, force=True, json_output=True)) == 0
    assert (
        json.loads(capsys.readouterr().out)["target_before_link"]["classification"]
        == "broken"
    )
    assert (broken_home / "auth.json").read_text(encoding="utf-8") == auth_text


def test_agent_accounts_link_refuses_broken_current_auth_without_force(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    broken_auth = "{not-json\n"
    _write(source_auth, _auth_json(account_id="acc_123"))
    _write(target_home / "auth.json", broken_auth)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home)) == 1
    assert "invalid codex auth JSON" in capsys.readouterr().err
    assert (target_home / "auth.json").read_text(encoding="utf-8") == broken_auth


def test_agent_accounts_status_reports_home_and_registry_state(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    auth_text = _auth_json(email="person@example.com")
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home)) == 0
    capsys.readouterr()

    assert main(_status_args(target_home)) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["classification"] == "matching-active"
    assert status_payload["link_consistency"] == "verified"
    assert status_payload["auth"]["account_id"] == "acc_123"
    assert status_payload["artifact_registry_matches"][0]["artifact_id"] == _sha(
        auth_text
    )
    assert "providers" not in status_payload

    assert main(_status_args(target_home, json_output=False)) == 0
    human_output = capsys.readouterr().out
    assert human_output.startswith("Provider: codex\n")
    assert "Status: matching-active\n" in human_output
    assert "Link: verified\n" in human_output
    assert "Registered artifact matches: 1\n" in human_output
    with pytest.raises(json.JSONDecodeError):
        json.loads(human_output)


def test_build_registered_account_agent_attaches_context_without_mutating_home(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "monitor-home"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert not target_home.exists()

    agent = build_registered_account_agent(
        provider="codex",
        account="br",
        home=target_home,
    )

    assert agent.account is not None
    assert agent.account.provider == "codex"
    assert agent.account.account == "br"
    assert agent.home == target_home.resolve()
    assert agentos_home.exists()
    assert not target_home.exists()


def test_build_registered_account_agent_reuses_registry_error_for_missing_account(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    with pytest.raises(Exception) as exc_info:
        build_registered_account_agent(
            provider="codex",
            account="missing",
            home=tmp_path / "monitor-home",
        )

    assert "agent account is not registered: codex.missing" in str(exc_info.value)


def test_build_registered_account_agent_ignores_provider_profile_ambiguity(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "monitor-home"
    _write(source_auth, _auth_json())
    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {
                    "providers": {
                        "codex": {
                            "cli_command": ["/opt/homebrew/bin/codex"],
                        },
                    },
                    "instances": [
                        {
                            "provider": "codex",
                            "id": "codex-a",
                            "home": str(tmp_path / "a"),
                        },
                        {
                            "provider": "codex",
                            "id": "codex-b",
                            "home": str(tmp_path / "b"),
                        },
                    ]
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    assert agent.provider == "codex"
    assert agent.instance_id is None
    assert agent.home == target_home.resolve()
    assert agent.cli_command == ("/opt/homebrew/bin/codex",)
    assert agent.account is not None
    assert agent.account.account == "br"


def test_build_registered_account_agent_uses_provider_cli_command(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "monitor-home"
    _write(source_auth, _auth_json())
    _write(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {
                    "providers": {
                        "codex": {
                            "cli_command": ["/opt/homebrew/bin/codex"],
                        },
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    assert agent.instance_id is None
    assert agent.home == target_home.resolve()
    assert agent.cli_command == ("/opt/homebrew/bin/codex",)


def test_codex_account_status_fetches_limits_with_single_status_call(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    import agentos.codex.account_status as codex_account_status

    monkeypatch.setattr(
        codex_account_status,
        "_fetch_account_usage_app_server_payload",
        lambda agent: {
            "rateLimits": {
                "limitId": "test-limit",
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 300,
                    "resetsAt": 1_776_000_000,
                },
            }
        },
    )
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status()

    assert status.check_status == "ok"
    assert status.usage_status == "ok"
    assert status.link_state == "verified"
    assert status.identity_match == "verified"
    assert status.expected_identity.provider_account_id == "acc_123"
    assert status.fetched_identity is not None
    assert status.fetched_identity.provider_account_id == "acc_123"
    assert status.auth_summary == "Codex rate limits read"
    assert [limit.limit_name for limit in status.limits] == ["5h"]
    assert status.errors == ()
    entries = _usage_registry_entries(tmp_path / "home" / ".agentos")
    assert len(entries) == 1
    assert entries[0]["class"] == "agentos.agent.usage-record"
    assert entries[0]["provider"] == "codex"
    assert entries[0]["account"] == "br"
    assert entries[0]["home"] == str(target_home.resolve())
    assert entries[0]["source"] == "app_server"
    assert entries[0]["payload"] == {
        "rateLimits": {
            "limitId": "test-limit",
            "primary": {
                "usedPercent": 25,
                "windowDurationMins": 300,
                "resetsAt": 1_776_000_000,
            },
        }
    }


def test_agent_usage_registry_appends_monthly_jsonl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agentos.agent.usage_registry import append_usage_record

    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    path = append_usage_record(
        provider="codex",
        account="br",
        home=tmp_path / "agent-home",
        source="app_server",
        payload={"raw": {"used": 25}},
    )

    assert path.parent == agentos_home / "agent" / "usage-registry"
    assert path.name.endswith("-usage.jsonl")
    assert len(path.name) == len("202605-usage.jsonl")
    assert not (path.parent / "latest.json").exists()
    entries = _read_jsonl(path)
    assert len(entries) == 1
    assert entries[0]["schema_version"] == 1
    assert entries[0]["class"] == "agentos.agent.usage-record"
    assert entries[0]["provider"] == "codex"
    assert entries[0]["account"] == "br"
    assert entries[0]["home"] == str((tmp_path / "agent-home").resolve())
    assert entries[0]["source"] == "app_server"
    assert entries[0]["payload"] == {"raw": {"used": 25}}


def test_agent_usage_registry_latest_record_reads_newest_matching_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agentos.agent.usage_registry import append_usage_record, latest_usage_record

    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    append_usage_record(
        provider="codex",
        account="br",
        home=codex_home,
        source="app_server",
        payload={"used": 10},
    )
    append_usage_record(
        provider="claude-code",
        account="main",
        home=claude_home,
        source="statusline",
        payload={"used": 20},
    )
    append_usage_record(
        provider="claude-code",
        account="other",
        home=claude_home,
        source="oauth_usage_get",
        payload={"used": 30},
    )
    append_usage_record(
        provider="claude-code",
        account="main",
        home=claude_home,
        source="oauth_usage_get",
        payload={"used": 40},
    )
    append_usage_record(
        provider="claude-code",
        account="main",
        home=claude_home,
        source="oauth_usage_get",
        payload={"used": 50},
    )

    record = latest_usage_record(
        provider="claude-code",
        account="main",
        home=claude_home,
        source="oauth_usage_get",
    )

    assert record is not None
    assert record["payload"] == {"used": 50}
    assert latest_usage_record(
        provider="claude-code",
        account="main",
        home=tmp_path / "missing-home",
        source="oauth_usage_get",
    ) is None


def test_codex_account_status_reports_identity_mismatch_as_status_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(
        tmp_path,
        monkeypatch,
        capsys,
        account_id="acc_123",
    )
    _write(target_home / "auth.json", _auth_json(account_id="acc_other"))

    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status()

    assert status.check_status == "error"
    assert status.usage_status == "unavailable"
    assert status.identity_match == "mismatched"
    assert [error.error_type for error in status.errors] == [
        "home_link_unusable",
        "identity_mismatch",
    ]


def test_codex_account_status_parses_limits(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    import agentos.codex.account_status as codex_account_status

    monkeypatch.setattr(
        codex_account_status,
        "_fetch_account_usage_app_server_payload",
        lambda agent: {
            "rateLimitsByLimitId": {
                "test-limit": {
                    "primary": {
                        "usedPercent": 25,
                        "windowDurationMins": 300,
                        "resetsAt": 1_776_000_000,
                    },
                    "secondary": {
                        "usedPercent": 40,
                        "windowDurationMins": 10080,
                        "resetsAt": 1_776_604_800,
                    },
                }
            }
        },
    )
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status()

    assert status.check_status == "ok"
    assert status.usage_status == "ok"
    assert status.usage_errors == ()
    assert [limit.limit_name for limit in status.limits] == ["5h", "168h"]
    assert [
        limit.usage_over_time.used_percent
        for limit in status.limits
        if limit.usage_over_time
    ] == [25, 40]
    assert status.usage_summary == "5 hours 25%, 168 hours 40%"


def test_codex_account_status_app_server_uses_agent_command_model(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    import agentos.codex.account_status as codex_account_status

    observed: dict[str, object] = {}

    class FakeProcess:
        def __init__(self, command, **kwargs):
            observed["command"] = tuple(command)
            observed["env"] = kwargs["env"]
            self.args = command
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                json.dumps({"id": 1, "result": {}})
                + "\n"
                + json.dumps(
                    {
                        "id": 2,
                        "result": {
                            "rateLimits": {
                                "limitId": "test-limit",
                                "primary": {
                                    "usedPercent": 25,
                                    "windowDurationMins": 300,
                                    "resetsAt": 1_776_000_000,
                                },
                            }
                        },
                    }
                )
                + "\n"
            )
            self.stderr = io.StringIO("")

        def wait(self, timeout=None):
            del timeout
            return 0

        def poll(self):
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    monkeypatch.setattr(
        codex_account_status.select,
        "select",
        lambda read, write, error, timeout: (read, write, error),
    )
    monkeypatch.setattr(codex_account_status.subprocess, "Popen", FakeProcess)

    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )
    payload = codex_account_status._fetch_account_usage_app_server_payload(agent)

    assert observed["command"][-1] == "app-server"
    assert observed["env"]["CODEX_HOME"] == str(target_home.resolve())
    assert payload["rateLimits"]["limitId"] == "test-limit"


def test_codex_account_status_preserves_identity_when_usage_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    import agentos.codex.account_status as codex_account_status

    def fail_rate_limits(agent):
        raise AccountStatusError(
            error_type="command_failed", message="rate limit failed"
        )

    monkeypatch.setattr(
        codex_account_status, "_fetch_account_usage_app_server_payload", fail_rate_limits
    )
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status()

    assert status.check_status == "ok"
    assert status.identity_match == "verified"
    assert status.usage_status == "error"
    assert status.limits == ()
    assert [error.summary() for error in status.usage_errors] == [
        {"type": "command_failed", "message": "rate limit failed"}
    ]
    assert _usage_registry_entries(tmp_path / "home" / ".agentos") == []


def test_codex_account_status_record_usage_false_skips_usage_registry(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    import agentos.codex.account_status as codex_account_status

    monkeypatch.setattr(
        codex_account_status,
        "_fetch_account_usage_app_server_payload",
        lambda agent: {
            "rateLimits": {
                "limitId": "test-limit",
                "primary": {
                    "usedPercent": 25,
                    "windowDurationMins": 300,
                    "resetsAt": 1_776_000_000,
                },
            }
        },
    )
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status(record_usage=False)

    assert status.usage_status == "ok"
    assert _usage_registry_entries(tmp_path / "home" / ".agentos") == []


def test_agent_accounts_status_defaults_to_general_registry_view(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    auth_text = _auth_json(email="person@example.com")
    _write(source_auth, auth_text)

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_registry_status_args(json_output=False)) == 0

    output = capsys.readouterr().out
    assert output.startswith("Agent accounts\n")
    assert "Providers: 1\n" in output
    assert "Accounts: 1\n" in output
    assert "Artifacts: 1\n" in output
    assert "Links: 0\n" in output
    assert "Registered accounts:\n" in output
    assert "  - codex/br <person@example.com> auth=auth-json active=" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)

    assert main(_registry_status_args(json_output=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] is None
    assert payload["provider_count"] == 1
    assert payload["account_count"] == 1
    assert payload["artifact_count"] == 1
    assert payload["link_count"] == 0
    assert payload["accounts"][0]["provider"] == "codex"
    assert payload["accounts"][0]["active_artifact_id"] == _sha(auth_text)


def test_agent_accounts_status_reports_malformed_registry_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    provider_root = agentos_home / "accounts" / "codex"
    _write(provider_root / "accounts.json", "{not-json\n")

    assert main(_registry_status_args(provider="codex")) == 1
    error = capsys.readouterr().err
    assert "invalid account registry JSON" in error
    assert str(provider_root / "accounts.json") in error


def test_agent_accounts_register_claude_metadata_only_and_link_claimed(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    claude_home = tmp_path / "claude-home"

    assert main(_claude_register_args(label="Claude main")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "claude-code"
    assert payload["account"] == "main"

    provider_root = agentos_home / "accounts" / "claude-code"
    accounts = _read_json(provider_root / "accounts.json")
    assert accounts["accounts"]["main"]["label"] == "Claude main"
    assert accounts["accounts"]["main"]["email"] == "person@example.com"
    assert accounts["accounts"]["main"]["auth_kinds"] == ["ambient-browser-login"]
    assert accounts["accounts"]["main"]["active_artifact_id"] is None
    assert not (provider_root / "artifacts").exists()
    assert not (provider_root / "artifacts.jsonl").exists()
    assert not (provider_root / "accounts" / "main" / "manifest.json").exists()

    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "claude-code",
                "--account",
                "main",
                "--home",
                str(claude_home),
                "--json",
            ]
        )
        == 0
    )
    link_payload = json.loads(capsys.readouterr().out)
    assert link_payload["kind"] == "claimed"
    links = _read_json(provider_root / "links.json")
    assert links["links"][str(claude_home.resolve())]["kind"] == "claimed"
    assert links["links"][str(claude_home.resolve())]["account"] == "main"

    assert (
        main(
            [
                "stdlib",
                "utils",
                "cmd-logger",
                "query",
                "--event-type",
                "agent.accounts.link",
                "--json",
            ]
        )
        == 0
    )
    log_payload = json.loads(capsys.readouterr().out)
    assert log_payload["count"] == 1
    event_payload = log_payload["events"][0]["payload"]
    assert event_payload["provider"] == "claude-code"
    assert event_payload["account"] == "main"
    assert event_payload["home"] == str(claude_home.resolve())
    assert event_payload["kind"] == "claimed"
    assert event_payload["force"] is False

    assert main(_status_args(claude_home, provider="claude-code")) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["classification"] == "claimed"
    assert status_payload["link_consistency"] == "claimed-unverified"


def test_agent_accounts_register_claude_requires_email(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")

    assert main(_claude_register_args(email=None)) == 1
    assert "requires --email" in capsys.readouterr().err


def test_claude_statusline_parser_maps_subscription_limits() -> None:
    import agentos.claude.account_status as claude_account_status

    limits = claude_account_status._parse_claude_statusline_rate_limits(
        {
            "rate_limits": {
                "five_hour": {
                    "used_percentage": 12.4,
                    "resets_at": 1_776_000_000,
                },
                "seven_day": {
                    "used_percentage": 44,
                    "resets_at": 1_776_604_800,
                },
                "overage": {
                    "used_percentage": 0,
                    "resets_at": 1_776_000_000,
                },
            }
        }
    )

    assert [limit.limit_name for limit in limits] == ["burst", "weekly"]
    assert [limit.limit_label for limit in limits] == ["Burst", "Weekly"]
    assert [
        limit.usage_over_time.used_percent
        for limit in limits
        if limit.usage_over_time
    ] == [12, 44]
    assert [
        limit.usage_over_time.period_duration_mins
        for limit in limits
        if limit.usage_over_time
    ] == [300, 10_080]
    assert limits[0].usage_over_time is not None
    assert limits[0].usage_over_time.resets_at == "2026-04-12T13:20:00Z"
    assert limits[0].usage_over_time.period_started_at == "2026-04-12T08:20:00Z"
    assert limits[0].provider_limit == {"limit_type": "five_hour"}


def test_claude_usage_get_parser_maps_subscription_limits() -> None:
    import agentos.claude.account_status as claude_account_status

    limits = claude_account_status._parse_claude_usage_get_limits(
        {
            "five_hour": {
                "utilization": 20.0,
                "resets_at": "2026-05-15T20:29:59.734578+00:00",
            },
            "seven_day": {
                "utilization": 72.0,
                "resets_at": "2026-05-16T10:00:00.734604+00:00",
            },
            "seven_day_sonnet": None,
        }
    )

    assert [limit.limit_name for limit in limits] == ["burst", "weekly"]
    assert [limit.limit_label for limit in limits] == ["Burst", "Weekly"]
    assert [
        limit.usage_over_time.used_percent
        for limit in limits
        if limit.usage_over_time
    ] == [20, 72]
    assert [
        limit.usage_over_time.period_duration_mins
        for limit in limits
        if limit.usage_over_time
    ] == [300, 10_080]
    assert limits[0].usage_over_time is not None
    assert (
        limits[0].usage_over_time.resets_at
        == "2026-05-15T20:29:59.734578Z"
    )
    assert (
        limits[0].usage_over_time.period_started_at
        == "2026-05-15T15:29:59.734578Z"
    )
    assert limits[0].provider_limit == {"limit_type": "five_hour"}


def test_claude_usage_get_http_error_detail_captures_retry_after() -> None:
    import urllib.error

    import agentos.claude.account_status as claude_account_status

    before = datetime.datetime.now(tz=datetime.UTC)
    error = urllib.error.HTTPError(
        "https://api.anthropic.com/api/oauth/usage",
        429,
        "Too Many Requests",
        {"Retry-After": "2852"},
        io.BytesIO(b'{"error":{"type":"rate_limit_error"}}'),
    )

    detail = claude_account_status._read_http_error_detail(error)
    after = datetime.datetime.now(tz=datetime.UTC)
    retry_after_until = datetime.datetime.fromisoformat(
        str(detail["retry_after_until"]).replace("Z", "+00:00")
    )

    assert detail["status"] == 429
    assert detail["retry_after_sec"] == 2852
    assert detail["retry_after_margin_sec"] == 300
    assert before + datetime.timedelta(seconds=3152) <= retry_after_until
    assert retry_after_until <= after + datetime.timedelta(seconds=3152)
    assert detail["body"] == {"error": {"type": "rate_limit_error"}}


def test_claude_usage_get_throttle_path_is_metadata_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    agentos_home = tmp_path / "home" / ".agentos"

    throttle_path = claude_account_status._claude_usage_get_throttle_path(agent)
    claude_account_status._write_claude_usage_get_throttle(
        agent,
        _claude_usage_http_429_error(
            retry_after_sec=300,
            retry_after_until=_future_iso(minutes=5),
        ),
    )

    assert throttle_path == (
        agentos_home
        / "cache"
        / "account-status"
        / "claude-code"
        / "main"
        / "oauth_usage_get-throttle.json"
    )
    throttle = _read_json(throttle_path)
    assert throttle["source"] == "oauth_usage_get"
    assert throttle["retry_after_sec"] == 300
    assert "payload" not in throttle
    assert "five_hour" not in throttle
    assert "seven_day" not in throttle


def test_claude_usage_get_fetches_provider_before_registry_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    _append_claude_usage_get_record(agent, utilization=20)
    monkeypatch.setattr(
        claude_account_status,
        "_fetch_claude_usage_payload",
        lambda agent: _claude_usage_get_payload(utilization=44),
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert errors == ()
    assert [limit.limit_name for limit in limits] == ["burst"]
    assert [limit.usage_over_time.used_percent for limit in limits if limit.usage_over_time] == [
        44
    ]
    assert payload is not None
    assert record_payload == payload
    assert usage_record == {
        "status": "fresh",
        "recorded_at": None,
        "source": "oauth_usage_get",
    }


def test_claude_usage_get_fresh_fetch_does_not_write_account_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    agentos_home = tmp_path / "home" / ".agentos"
    monkeypatch.setattr(
        claude_account_status,
        "_fetch_claude_usage_payload",
        lambda agent: _claude_usage_get_payload(utilization=33),
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert errors == ()
    assert [limit.usage_over_time.used_percent for limit in limits if limit.usage_over_time] == [
        33
    ]
    assert payload is not None
    assert record_payload == _claude_usage_get_payload(utilization=33)
    assert usage_record["status"] == "fresh"
    assert not (agentos_home / "cache" / "account-status").exists()


def test_claude_usage_get_returns_live_error_when_refresh_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    _append_claude_usage_get_record(agent, utilization=20)

    def fail_fetch(agent):
        del agent
        raise _claude_usage_http_429_error()

    monkeypatch.setattr(claude_account_status, "_fetch_claude_usage_payload", fail_fetch)

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["usage_api_http_error"]
    assert payload is None
    assert record_payload is None
    assert usage_record is None


def test_claude_usage_get_active_throttle_skips_provider_fetch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    _append_claude_usage_get_record(agent, utilization=20)
    claude_account_status._write_claude_usage_get_throttle(
        agent,
        _claude_usage_http_429_error(
            retry_after_sec=1800,
            retry_after_until=_future_iso(minutes=30),
        ),
    )

    def fail_if_fetches(agent):
        del agent
        raise AssertionError("provider fetch should be skipped while throttle is active")

    monkeypatch.setattr(claude_account_status, "_fetch_claude_usage_payload", fail_if_fetches)

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["usage_api_http_error"]
    assert payload is None
    assert record_payload is None
    assert usage_record is None


def test_claude_usage_get_http_429_writes_throttle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)

    def fail_fetch(agent):
        del agent
        raise _claude_usage_http_429_error(
            retry_after_sec=900,
            retry_after_until=_future_iso(minutes=15),
        )

    monkeypatch.setattr(claude_account_status, "_fetch_claude_usage_payload", fail_fetch)

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["usage_api_http_error"]
    assert payload is None
    assert record_payload is None
    assert usage_record is None
    throttle = _read_json(claude_account_status._claude_usage_get_throttle_path(agent))
    assert throttle["reason"] == "http_429"
    assert throttle["retry_after_sec"] == 900
    assert throttle["live_error"]["message"] == "claude usage API returned HTTP 429"


def test_claude_usage_get_live_success_clears_expired_throttle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    throttle_path = claude_account_status._claude_usage_get_throttle_path(agent)
    _write(
        throttle_path,
        json.dumps(
            {
                "schema_version": 1,
                "provider": "claude-code",
                "account": "main",
                "source": "oauth_usage_get",
                "reason": "http_429",
                "captured_at": "2026-05-15T00:00:00Z",
                "retry_after_sec": 1,
                "retry_after_until": "2026-05-15T00:00:01Z",
                "live_error": {
                    "type": "usage_api_http_error",
                    "message": "claude usage API returned HTTP 429",
                    "exit_code": 429,
                    "detail": {
                        "status": 429,
                        "retry_after_sec": 1,
                        "retry_after_until": "2026-05-15T00:00:01Z",
                    },
                },
            }
        )
        + "\n",
    )
    monkeypatch.setattr(
        claude_account_status,
        "_fetch_claude_usage_payload",
        lambda agent: _claude_usage_get_payload(utilization=33),
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert errors == ()
    assert [limit.usage_over_time.used_percent for limit in limits if limit.usage_over_time] == [
        33
    ]
    assert payload is not None
    assert record_payload == payload
    assert usage_record["status"] == "fresh"
    assert not throttle_path.exists()


def test_claude_usage_get_non_429_error_does_not_write_throttle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(
        claude_account_status,
        "_fetch_claude_usage_payload",
        lambda agent: (_ for _ in ()).throw(
            AccountStatusError(
                error_type="timeout",
                message="claude usage API timed out after 5 seconds",
            )
        ),
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["timeout"]
    assert payload is None
    assert record_payload is None
    assert usage_record is None
    assert not claude_account_status._claude_usage_get_throttle_path(agent).exists()


def test_claude_account_status_refresh_failure_can_disable_registry_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.claude.account_status as claude_account_status

    claude_home = _registered_linked_claude_home(tmp_path, monkeypatch, capsys)
    agent = build_registered_account_agent(
        provider="claude-code", account="main", home=claude_home
    )
    _append_claude_statusline_record(agent, burst_used=20)

    def fail_statusline_refresh(*args, **kwargs):
        del args, kwargs
        raise AccountStatusError(
            error_type="timeout",
            message="provider command timed out after 45 seconds using model haiku",
        )

    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        fail_statusline_refresh,
    )

    status = agent.account_status(
        fallback_to_usage_registry=False,
    )

    assert status.usage_status == "error"
    assert [error.error_type for error in status.usage_errors] == ["timeout"]
    assert status.raw["usage"] is None
    assert status.raw["usage_record"] is None


def test_claude_usage_get_refresh_failure_without_registry_record_returns_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    agent = _claude_usage_get_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(
        claude_account_status,
        "_fetch_claude_usage_payload",
        lambda agent: (_ for _ in ()).throw(_claude_usage_http_429_error()),
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_GET(agent)
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["usage_api_http_error"]
    assert payload is None
    assert record_payload is None
    assert usage_record is None


def test_claude_statusline_uses_stable_system_home_workspace(tmp_path: Path) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.claude.agent import ClaudeAgent

    agent = ClaudeAgent(home=tmp_path / "claude-home")

    assert claude_account_status._claude_statusline_workspace(agent) == (
        tmp_path / "claude-home" / "agentos" / "workspaces" / "statusline-refresh"
    )


def test_claude_statusline_fetch_returns_recordable_fresh_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.claude.agent import ClaudeAgent

    agent = ClaudeAgent(home=tmp_path / "claude-home")
    captured: list[dict[str, object]] = []

    def fake_statusline_refresh(agent_arg, *, cwd, capture_path, settings_path, timeout_sec):
        assert agent_arg is agent
        assert cwd == tmp_path / "claude-home" / "agentos" / "workspaces" / "statusline-refresh"
        assert capture_path.name == "statusline.json"
        assert settings_path.is_file()
        assert timeout_sec == 45
        captured.append(json.loads(settings_path.read_text(encoding="utf-8")))
        return _claude_statusline_payload(burst_used=33, weekly_used=68)

    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        fake_statusline_refresh,
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_statusline(agent)
    )

    assert errors == ()
    assert [limit.limit_name for limit in limits] == ["burst", "weekly"]
    assert [limit.usage_over_time.used_percent for limit in limits if limit.usage_over_time] == [
        33,
        68,
    ]
    assert payload == _claude_statusline_payload(burst_used=33, weekly_used=68)
    assert record_payload == payload
    assert usage_record == {
        "status": "fresh",
        "recorded_at": None,
        "source": "statusline_rate_limits",
    }
    assert captured[0]["statusLine"]["type"] == "command"
    assert not (
        tmp_path / "claude-home" / "agentos" / "cache" / "statusline-rate-limits.json"
    ).exists()


def test_claude_statusline_process_environment_strips_parent_claude_controls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status

    monkeypatch.setenv("PATH", "/bin:/usr/bin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/wrong/claude")
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "0")
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "0")
    monkeypatch.setenv("CLAUDE_CODE_AUTO_CONNECT_IDE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example")
    monkeypatch.setenv("CMUX_CLAUDE_HOOKS_DISABLED", "1")
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")

    env = claude_account_status._claude_statusline_process_environment(
        {
            "CLAUDE_CONFIG_DIR": str(tmp_path / "system-home"),
            "CUSTOM_AGENT_ENV": "kept",
        }
    )

    assert env["PATH"] == "/bin:/usr/bin"
    assert env["HOME"] == str(tmp_path)
    assert env["LANG"] == "en_US.UTF-8"
    assert env["LC_ALL"] == "C.UTF-8"
    assert env["TERM"] == "xterm-256color"
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "system-home")
    assert env["CUSTOM_AGENT_ENV"] == "kept"
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert "CLAUDE_CODE_AUTO_CONNECT_IDE" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "CMUX_CLAUDE_HOOKS_DISABLED" not in env
    assert "NODE_OPTIONS" not in env


def test_claude_statusline_last_run_log_records_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.agent.account_status import AgentAccountContext
    from agentos.claude.agent import ClaudeAgent

    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    agent = ClaudeAgent(
        home=tmp_path / "claude-home",
        account=AgentAccountContext(provider="claude-code", account="main"),
    )
    payload = _claude_statusline_payload(burst_used=20)
    capture_path = tmp_path / "statusline.json"
    capture_path.write_text(json.dumps(payload), encoding="utf-8")
    run_log = claude_account_status._ClaudeStatusLineRunLog(
        agent=agent,
        argv=("claude", "--model", "haiku"),
        cwd=tmp_path,
        capture_path=capture_path,
        settings_path=tmp_path / "settings.json",
        timeout_sec=45,
        env={
            "CLAUDE_CONFIG_DIR": str(tmp_path / "claude-home"),
            "PATH": "/bin:/usr/bin",
            "ANTHROPIC_API_KEY": "should-not-log-value",
        },
        started_at_monotonic=claude_account_status.time.monotonic(),
        prompt_sent=True,
        transcript_text="Claude Code ready\n",
        normalized_transcript_text="claude code ready",
        statusline_payload=payload,
    )
    claude_account_status._append_claude_statusline_log_event(run_log, "capture_loaded")

    claude_account_status._finalize_claude_statusline_log(run_log, error=None)

    log_path = claude_account_status._claude_statusline_last_run_log_path()
    log = _read_json(log_path)
    assert log["status"] == "ok"
    assert log["provider"] == "claude-code"
    assert log["account"] == "main"
    assert log["argv"] == ["claude", "--model", "haiku"]
    assert log["capture"]["exists"] is True
    assert log["events"][0]["event"] == "capture_loaded"
    assert log["state"]["prompt_sent"] is True
    assert log["transcript"] == "Claude Code ready\n"
    assert log["transcript_tail"] == "Claude Code ready\n"
    assert log["normalized_transcript_tail"] == "claude code ready"
    assert log["statusline_payload"] == payload
    assert log["invalid_capture_payload"] is None
    assert log["invalid_capture_error"] is None
    assert log["env"]["ANTHROPIC_API_KEY"] == "should-not-log-value"


def test_claude_statusline_last_run_log_records_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.agent.account_status import AgentAccountContext
    from agentos.claude.agent import ClaudeAgent

    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    agent = ClaudeAgent(
        home=tmp_path / "claude-home",
        account=AgentAccountContext(provider="claude-code", account="main"),
    )
    run_log = claude_account_status._ClaudeStatusLineRunLog(
        agent=agent,
        argv=("claude", "--model", "haiku"),
        cwd=tmp_path,
        capture_path=tmp_path / "missing-statusline.json",
        settings_path=tmp_path / "settings.json",
        timeout_sec=45,
        env={"CLAUDE_CONFIG_DIR": str(tmp_path / "claude-home")},
        started_at_monotonic=claude_account_status.time.monotonic(),
        transcript_text="login required\n",
        normalized_transcript_text="login required",
    )
    error = AccountStatusError(error_type="timeout", message="provider command timed out")

    claude_account_status._finalize_claude_statusline_log(run_log, error=error)

    log = _read_json(claude_account_status._claude_statusline_last_run_log_path())
    assert log["status"] == "error"
    assert log["capture"]["exists"] is False
    assert log["transcript"] == "login required\n"
    assert log["normalized_transcript_tail"] == "login required"
    assert log["error"]["type"] == "timeout"
    assert log["error"]["message"] == "provider command timed out"


def test_claude_statusline_last_run_log_records_invalid_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.agent.account_status import AgentAccountContext
    from agentos.claude.agent import ClaudeAgent

    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    agent = ClaudeAgent(
        home=tmp_path / "claude-home",
        account=AgentAccountContext(provider="claude-code", account="main"),
    )
    capture_path = tmp_path / "statusline.json"
    invalid_payload = {
        "model": {"display_name": "Haiku 4.5"},
        "workspace": {"current_dir": str(tmp_path)},
    }
    capture_path.write_text(json.dumps(invalid_payload), encoding="utf-8")
    run_log = claude_account_status._ClaudeStatusLineRunLog(
        agent=agent,
        argv=("claude", "--model", "haiku"),
        cwd=tmp_path,
        capture_path=capture_path,
        settings_path=tmp_path / "settings.json",
        timeout_sec=45,
        env={"CLAUDE_CONFIG_DIR": str(tmp_path / "claude-home")},
        started_at_monotonic=claude_account_status.time.monotonic(),
        prompt_sent=True,
        transcript_text="Reply with OK.\n",
        normalized_transcript_text="reply with ok.",
    )

    claude_account_status._record_claude_statusline_invalid_capture(run_log)
    claude_account_status._finalize_claude_statusline_log(
        run_log,
        error=AccountStatusError(error_type="timeout", message="timed out"),
    )

    log = _read_json(claude_account_status._claude_statusline_last_run_log_path())
    assert log["invalid_capture_error"] == "capture payload is missing rate_limits"
    assert log["invalid_capture_payload"] == invalid_payload
    assert log["events"][0]["event"] == "capture_rejected"
    assert log["events"][0]["invalid_capture_error"] == (
        "capture payload is missing rate_limits"
    )
    assert log["events"][0]["invalid_capture_payload"] == invalid_payload


def test_claude_statusline_refresh_failure_returns_live_error_without_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.claude.agent import ClaudeAgent

    agent = ClaudeAgent(home=tmp_path / "claude-home")
    _write(
        tmp_path / "claude-home" / "agentos" / "cache" / "statusline-rate-limits.json",
        json.dumps(
            {
                "captured_at_epoch": 100.0,
                "statusline": {
                    "rate_limits": {
                        "five_hour": {
                            "used_percentage": 20,
                            "resets_at": 1_776_000_000,
                        },
                        "seven_day": {
                            "used_percentage": 68,
                            "resets_at": 1_776_604_800,
                        },
                    }
                },
            }
        )
        + "\n",
    )

    def fail_live_refresh(*args, **kwargs):
        del args, kwargs
        raise AccountStatusError(
            error_type="timeout",
            message="provider command timed out after 45 seconds using model haiku",
        )

    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        fail_live_refresh,
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_statusline(agent)
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["timeout"]
    assert payload is None
    assert record_payload is None
    assert usage_record is None


def test_claude_statusline_cleanup_is_disabled_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.claude.agent import ClaudeAgent

    agent = ClaudeAgent(home=tmp_path / "claude-home")
    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        lambda *args, **kwargs: _claude_statusline_payload(burst_used=20),
    )

    def fail_if_cleanup_runs(*args, **kwargs):
        del args, kwargs
        raise AssertionError("cleanup should be disabled by default")

    monkeypatch.setattr(
        claude_account_status,
        "_cleanup_claude_statusline_transcript",
        fail_if_cleanup_runs,
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_statusline(agent)
    )

    assert errors == ()
    assert [limit.limit_name for limit in limits] == ["burst"]
    assert payload == record_payload
    assert usage_record["source"] == "statusline_rate_limits"


def test_claude_statusline_cleanup_is_best_effort_when_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.claude.agent import ClaudeAgent

    agent = ClaudeAgent(home=tmp_path / "claude-home")
    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        lambda *args, **kwargs: _claude_statusline_payload(burst_used=20),
    )
    cleanup_calls: list[object] = []

    def fail_cleanup(**kwargs):
        cleanup_calls.append(kwargs["statusline_payload"])
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(
        claude_account_status,
        "_cleanup_claude_statusline_transcript",
        fail_cleanup,
    )

    limits, errors, payload, record_payload, usage_record = (
        claude_account_status._account_usage_statusline(
            agent,
            cleanup_transcript=True,
        )
    )

    assert errors == ()
    assert [limit.limit_name for limit in limits] == ["burst"]
    assert cleanup_calls == [payload]
    assert record_payload == payload
    assert usage_record["source"] == "statusline_rate_limits"


def test_claude_account_status_uses_statusline_usage_limits(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.claude.account_status as claude_account_status

    claude_home = _registered_linked_claude_home(tmp_path, monkeypatch, capsys)

    def fake_statusline_refresh(agent, *, cwd, capture_path, settings_path, timeout_sec):
        del cwd, capture_path, settings_path, timeout_sec
        assert agent.home == claude_home.resolve()
        return _claude_statusline_payload(burst_used=20, weekly_used=94)

    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        fake_statusline_refresh,
    )
    agent = build_registered_account_agent(
        provider="claude-code", account="main", home=claude_home
    )

    status = agent.account_status()

    assert status.check_status == "ok"
    assert status.usage_status == "ok"
    assert status.usage_errors == ()
    assert status.auth_summary == "Claude statusLine read"
    assert status.usage_summary == "Burst 20%, Weekly 94%"
    assert [limit.limit_name for limit in status.limits] == ["burst", "weekly"]
    assert [
        limit.usage_over_time.used_percent
        for limit in status.limits
        if limit.usage_over_time
    ] == [20, 94]
    entries = _usage_registry_entries(tmp_path / "home" / ".agentos")
    assert len(entries) == 1
    assert entries[0]["provider"] == "claude-code"
    assert entries[0]["account"] == "main"
    assert entries[0]["home"] == str(claude_home.resolve())
    assert entries[0]["source"] == "statusline_rate_limits"
    assert entries[0]["payload"] == _claude_statusline_payload(
        burst_used=20,
        weekly_used=94,
    )


def test_claude_account_status_record_usage_false_skips_usage_registry(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.claude.account_status as claude_account_status

    claude_home = _registered_linked_claude_home(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        lambda *args, **kwargs: _claude_statusline_payload(burst_used=20),
    )
    agent = build_registered_account_agent(
        provider="claude-code", account="main", home=claude_home
    )

    status = agent.account_status(record_usage=False)

    assert status.usage_status == "ok"
    assert _usage_registry_entries(tmp_path / "home" / ".agentos") == []


def test_claude_account_status_registry_fallback_returns_status_without_append(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.agent.usage_registry import append_usage_record

    agentos_home = tmp_path / "home" / ".agentos"
    claude_home = _registered_linked_claude_home(tmp_path, monkeypatch, capsys)
    append_usage_record(
        provider="claude-code",
        account="main",
        home=claude_home,
        source="statusline_rate_limits",
        payload=_claude_statusline_payload(burst_used=20),
    )

    def fail_statusline_refresh(*args, **kwargs):
        del args, kwargs
        raise AccountStatusError(
            error_type="timeout",
            message="provider command timed out after 45 seconds using model haiku",
        )

    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        fail_statusline_refresh,
    )
    agent = build_registered_account_agent(
        provider="claude-code", account="main", home=claude_home
    )

    status = agent.account_status()

    assert status.usage_status == "ok"
    assert status.auth_summary == "Claude usage registry fallback"
    assert status.raw["usage_record"]["status"] == "registry_fallback"
    assert status.raw["usage"]["rate_limits"]["five_hour"]["used_percentage"] == 20
    assert len(_usage_registry_entries(agentos_home)) == 1


def test_claude_account_status_does_not_fallback_to_get_usage_records(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.claude.account_status as claude_account_status
    from agentos.agent.usage_registry import append_usage_record

    agentos_home = tmp_path / "home" / ".agentos"
    claude_home = _registered_linked_claude_home(tmp_path, monkeypatch, capsys)
    append_usage_record(
        provider="claude-code",
        account="main",
        home=claude_home,
        source="oauth_usage_get",
        payload=_claude_usage_get_payload(utilization=20),
    )

    def fail_statusline_refresh(*args, **kwargs):
        del args, kwargs
        raise AccountStatusError(
            error_type="timeout",
            message="provider command timed out after 45 seconds using model haiku",
        )

    monkeypatch.setattr(
        claude_account_status,
        "_run_claude_statusline_refresh_session",
        fail_statusline_refresh,
    )
    agent = build_registered_account_agent(
        provider="claude-code", account="main", home=claude_home
    )

    status = agent.account_status()

    assert status.usage_status == "error"
    assert [error.error_type for error in status.usage_errors] == ["timeout"]
    assert status.raw["usage"] is None
    assert status.raw["usage_record"] is None
    assert len(_usage_registry_entries(agentos_home)) == 1


def test_agent_accounts_monitor_once_prints_account_status(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from agentos.agent.usage_registry import append_usage_record

    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    _stub_monitor_account_status(monkeypatch)
    append_usage_record(
        provider="codex",
        account="br",
        home=agentos_home / "agent" / "homes" / "codex" / "br",
        source="app_server",
        payload=_codex_usage_payload(),
    )

    assert main(["agent", "accounts", "monitor", "--once"]) == 0
    output = capsys.readouterr().out
    assert "Agent accounts monitor" in output
    assert "Tick: 1" in output
    assert "limits-tracking" in output
    assert "refresh_interval_sec: 60" not in output
    assert "    ⬢ codex/br:            | " in output
    assert " ago" in output
    assert "refreshed | fresh" not in output
    assert "      usage/time           |  3% /" in output
    assert " | Burst" in output
    assert "          resets           | " in output
    assert "      usage/time           |  1% /" in output
    assert " | Weekly" in output
    assert "under construction" not in output


def test_agent_accounts_monitor_once_prints_registry_fallback_refresh_time(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from agentos.agent.usage_registry import append_usage_record

    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    _stub_monitor_account_status(monkeypatch)
    append_usage_record(
        provider="codex",
        account="br",
        home=agentos_home / "agent" / "homes" / "codex" / "br",
        source="app_server",
        payload=_codex_usage_payload(),
    )

    assert main(["agent", "accounts", "monitor", "--once"]) == 0
    output = capsys.readouterr().out
    assert "    ⬢ codex/br:" in output
    assert "refreshed | " not in output
    assert " ago" in output
    assert "          fetch error      |" not in output


def test_limits_tracking_setup_primes_from_usage_registry_without_provider_fetch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agentos.agent.monitor.workflows as monitor_workflows
    from agentos.agent.monitor import (
        LimitsTrackingWorkflow,
        MonitorFrame,
        MonitorState,
        MonitorTarget,
        MonitorWorkflowConfig,
    )
    from agentos.agent.usage_registry import append_usage_record

    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    target_home = tmp_path / "codex-home"
    append_usage_record(
        provider="codex",
        account="br",
        home=target_home,
        source="app_server",
        payload=_codex_usage_payload(burst_used=25, weekly_used=40),
    )
    monkeypatch.setattr(
        monitor_workflows,
        "build_registered_account_agent",
        lambda **kwargs: pytest.fail(f"provider fetch during setup: {kwargs}"),
    )
    workflow = LimitsTrackingWorkflow(
        MonitorWorkflowConfig(
            name="limits-tracking",
            targets=(
                MonitorTarget(provider="codex", account="br", home=target_home),
            ),
            refresh_interval_sec=60,
            raw_config={},
        )
    )
    frame = MonitorFrame()
    state = MonitorState()

    workflow.setup(state, frame)

    assert state.workflow_run_counts == {}
    target = frame.blocks[0]["data"]["targets"][0]
    assert target["status"] == "ok"
    assert target["account_status"]["raw"]["usage_record"]["status"] == "registry_latest"
    assert frame.blocks[0]["lines"][0].startswith("  ⬢ codex/br: | ")
    assert any("usage/time | 25%" in line for line in frame.blocks[0]["lines"])


def test_agent_accounts_monitor_rows_use_fixed_columns() -> None:
    from agentos.agent.monitor import (
        MonitorAccountRow,
        MonitorFrame,
        MonitorInfoRow,
        format_monitor_frame,
    )

    frame = MonitorFrame(tick=1)
    frame.add_block(
        "limits-tracking",
        rows=[
            MonitorAccountRow(
                label="  claude-code/browser-jp:",
                value="Fri 05-15 16:51",
                suffix="2h 47m ago",
            ),
            MonitorInfoRow(
                label="        fetch error",
                value="claude usage API returned HTTP 429 [retry in 39m]",
            ),
            MonitorAccountRow(label="  ⬢ codex/br:", value="fresh"),
        ],
    )

    lines = format_monitor_frame(frame).splitlines()
    column_lines = [line for line in lines if "|" in line]

    assert len(column_lines) == 3
    assert {line.index("|") for line in column_lines} == {27}
    assert "claude-code/browser-jp" in column_lines[0]
    assert "claude usage API returne" in column_lines[1]
    assert "fresh" in column_lines[2]


def test_agent_accounts_monitor_row_animation_moves_overflowing_cells() -> None:
    from agentos.agent.monitor import MonitorInfoRow

    row = MonitorInfoRow(
        label="        fetch error",
        value="claude usage API returned HTTP 429 [retry in 39m]",
    )
    first = row.render_frame()

    row.step_animation()
    second = row.render_frame()

    assert first != second
    assert "claude usage API returne" in first
    assert "laude usage API returned" in second


def test_agent_accounts_monitor_row_animation_wraps_periodically() -> None:
    from agentos.agent.monitor import MonitorInfoRow, MonitorRenderContext

    row = MonitorInfoRow(label="x", value="hello agentos, we are amazing")
    context = MonitorRenderContext(label_width=1, value_width=19, suffix_width=1)
    row.animation_tick = 18

    assert "are amazing | hello" in row.render_frame(context)
    row.step_animation()
    assert "re amazing | hello " in row.render_frame(context)
    row.step_animation()
    assert "e amazing | hello a" in row.render_frame(context)


def test_agent_accounts_monitor_row_animation_keeps_short_cells_stable() -> None:
    from agentos.agent.monitor import MonitorInfoRow

    row = MonitorInfoRow(label="    usage", value="fresh")
    first = row.render_frame()

    for _ in range(5):
        row.step_animation()

    assert row.render_frame() == first


def test_agent_accounts_monitor_loop_steps_visible_frame_animation_after_draw() -> None:
    from agentos.agent.monitor import (
        MonitorFrame,
        MonitorInfoRow,
        MonitorLoop,
        MonitorState,
        format_monitor_frame,
    )

    second_run_release = Event()
    rendered: list[str] = []

    class LongRowWorkflow:
        name = "long-row"

        def __init__(self) -> None:
            self.runs = 0

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state
            self._write_frame(frame)

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del trigger, state
            self.runs += 1
            if self.runs > 1:
                second_run_release.wait(timeout=0.2)
                return
            self._write_frame(frame)

        def _write_frame(self, frame: MonitorFrame) -> None:
            frame.add_block(
                "long-row",
                rows=[
                    MonitorInfoRow(
                        label="        fetch error",
                        value="claude usage API returned HTTP 429 [retry in 39m]",
                    )
                ],
            )

    workflow = LongRowWorkflow()

    def record_render(frame: MonitorFrame, state: MonitorState) -> None:
        del state
        rendered.append(format_monitor_frame(frame))
        if len(rendered) == 2:
            second_run_release.set()

    MonitorLoop(
        workflows=(workflow,),
        interval_sec=0.01,
        max_ticks=2,
    ).run(on_tick=record_render, wait_for_first_frame=True)

    assert len(rendered) == 2
    assert rendered[0] != rendered[1]
    assert "claude usage API returne" in rendered[0]
    assert "laude usage API returned" in rendered[1]


def test_agent_accounts_monitor_loop_preserves_animation_across_republished_rows() -> None:
    from agentos.agent.monitor import (
        MONITOR_ENTER_ALARM,
        MonitorFrame,
        MonitorInfoRow,
        MonitorLoop,
        MonitorState,
        format_monitor_frame,
    )

    rendered: list[str] = []

    class FastWorkflow:
        name = "fast"

        def __init__(self) -> None:
            self.runs = 0

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state
            self._write_frame(frame)

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del trigger, state
            self.runs += 1
            self._write_frame(frame)

        def _write_frame(self, frame: MonitorFrame) -> None:
            frame.add_block(
                "fast",
                rows=[
                    MonitorInfoRow(
                        label="        fetch error",
                        value="claude usage API returned HTTP 429 [retry in 39m]",
                    )
                ],
            )

    workflow = FastWorkflow()
    loop = MonitorLoop(
        workflows=(workflow,),
        interval_sec=0.01,
        max_ticks=3,
    )

    def record_render(frame: MonitorFrame, state: MonitorState) -> None:
        del state
        rendered.append(format_monitor_frame(frame))
        if len(rendered) == 1:
            loop.set_alarm(MONITOR_ENTER_ALARM)

    loop.run(on_tick=record_render, wait_for_first_frame=True)

    assert workflow.runs >= 2
    assert "claude usage API returne" in rendered[0]
    assert any("laude usage API returned" in output for output in rendered[1:])


def test_agent_accounts_monitor_manual_requests_coalesce_while_workflow_runs() -> None:
    from agentos.agent.monitor import (
        MONITOR_ENTER_ALARM,
        MonitorFrame,
        MonitorLoop,
        MonitorState,
    )

    started = Event()
    release = Event()

    class SlowWorkflow:
        name = "slow"

        def __init__(self) -> None:
            self.runs = 0

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, trigger
            self.runs += 1
            if self.runs == 1:
                started.set()
                release.wait(timeout=0.2)
            frame.add_block("slow", [f"run {self.runs}"])

    workflow = SlowWorkflow()
    loop = MonitorLoop(
        workflows=(workflow,),
        interval_sec=0.01,
        max_ticks=4,
    )

    def record_render(frame: MonitorFrame, state: MonitorState) -> None:
        del frame, state
        if started.is_set() and not release.is_set():
            loop.set_alarm(MONITOR_ENTER_ALARM)
            loop.set_alarm(MONITOR_ENTER_ALARM)
            loop.set_alarm(MONITOR_ENTER_ALARM)
            release.set()

    loop.run(on_tick=record_render)

    assert workflow.runs == 2


def test_agent_accounts_monitor_json_preserves_state_and_frame_across_ticks(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first_auth = tmp_path / "first.json"
    second_auth = tmp_path / "second.json"
    _write(first_auth, _auth_json(account_id="acc_br", email="br@example.com"))
    _write(second_auth, _auth_json(account_id="acc_jp", email="jp@example.com"))

    assert main(_register_args(first_auth, account="br")) == 0
    capsys.readouterr()
    assert main(_register_args(second_auth, account="jp")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "refresh_interval_sec": 60,
                "targets": [
                    {"provider": "codex", "account": "br"},
                    {
                        "provider": "codex",
                        "account": "jp",
                        "home": str(tmp_path / "jp-home"),
                    },
                ],
            },
        ],
    )
    calls = _stub_monitor_account_status(monkeypatch)

    assert (
        main(
            [
                "agent",
                "accounts",
                "monitor",
                "--max-ticks",
                "3",
                "--interval-sec",
                "0.01",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tick"] == 3
    assert payload["workflow_run_counts"] == {"limits-tracking": 1}
    assert payload["state"]["limits-tracking"]["last_tick"] == 1
    assert payload["state"]["limits-tracking"]["run_count"] == 1
    assert payload["state"]["limits-tracking"]["refresh_interval_sec"] == 60
    assert len(calls) == 2
    assert payload["frame"]["tick"] == 3
    assert len(payload["frame"]["blocks"]) == 1
    assert payload["frame"]["blocks"][0]["lines"][0] == "  ⬢ codex/br: | fresh"
    assert payload["frame"]["blocks"][0]["rows"][0] == {
        "kind": "account",
        "text": "  ⬢ codex/br: | fresh",
        "label": "  ⬢ codex/br:",
        "value": "fresh",
    }
    assert any(
        row["kind"] == "usage_time" for row in payload["frame"]["blocks"][0]["rows"]
    )
    assert any(row["kind"] == "reset" for row in payload["frame"]["blocks"][0]["rows"])
    assert "  ⬢ codex/br: | fresh" in payload["frame"]["blocks"][0]["lines"]
    assert "  ⬢ codex/jp: | fresh" in payload["frame"]["blocks"][0]["lines"]
    assert payload["frame"]["blocks"][0]["data"]["run_count"] == 1
    assert payload["frame"]["blocks"][0]["data"]["targets"][0]["home"] == str(
        agentos_home / "agent" / "homes" / "codex" / "br"
    )
    assert payload["frame"]["blocks"][0]["data"]["targets"][1]["home"] == str(
        (tmp_path / "jp-home").resolve()
    )
    assert payload["frame"]["blocks"][0]["data"]["targets"][0]["status"] == "ok"
    assert (
        payload["frame"]["blocks"][0]["data"]["targets"][0]["account_status"][
            "usage_status"
        ]
        == "ok"
    )


def test_agent_accounts_monitor_frame_prepare_resets_render_data() -> None:
    from agentos.agent.monitor import MonitorFrame

    frame = MonitorFrame(tick=9)
    frame.status_lines.append("old status")
    frame.warnings.append("old warning")
    frame.errors.append("old error")
    frame.add_block("old", ["stale"])

    frame.prepare(tick=12)

    assert frame.tick == 12
    assert frame.status_lines == []
    assert frame.warnings == []
    assert frame.errors == []
    assert frame.blocks == []


def test_agent_accounts_monitor_loop_publishes_working_frame_and_shared_state() -> None:
    from agentos.agent.monitor import MonitorFrame, MonitorLoop, MonitorState

    seen_frames: list[int] = []
    seen_states: list[int] = []

    class RecordingWorkflow:
        name = "recording"

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            seen_frames.append(id(frame))
            seen_states.append(id(state))
            state.data["recording"] = state.data.get("recording", 0) + 1
            frame.add_block("recording", ["created"])

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, frame, trigger

    loop = MonitorLoop(
        workflows=(RecordingWorkflow(),),
        interval_sec=0,
        max_ticks=1,
    )
    frame, state = loop.run(wait_for_first_frame=True)

    assert frame is loop.visible_frame
    assert state is loop.state
    assert len(set(seen_frames)) == 1
    assert len(set(seen_states)) == 1
    assert seen_frames[0] == id(frame)
    assert frame.tick == 1
    assert state.tick == 1
    assert state.data["recording"] == 1


def test_agent_accounts_monitor_setup_frame_is_visible_before_slow_loop() -> None:
    from agentos.agent.monitor import MonitorFrame, MonitorLoop, MonitorState

    started = Event()
    release = Event()
    rendered: list[tuple[int, tuple[str, ...]]] = []

    class SlowWorkflow:
        name = "slow"

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state
            frame.add_block("slow", ["setup ready"])

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, trigger
            started.set()
            release.wait(timeout=0.2)
            frame.add_block("slow", ["loop ready"])

    def record_tick(frame: MonitorFrame, state: MonitorState) -> None:
        rendered.append((state.tick, tuple(frame.blocks[0]["lines"])))
        if started.is_set():
            release.set()

    MonitorLoop(
        workflows=(SlowWorkflow(),),
        interval_sec=0.01,
        max_ticks=3,
    ).run(on_tick=record_tick, wait_for_first_frame=True)

    assert rendered[0] == (1, ("setup ready",))
    assert rendered[-1] == (3, ("loop ready",))


def test_agent_accounts_monitor_slow_workflow_does_not_block_render_ticks() -> None:
    from agentos.agent.monitor import MonitorFrame, MonitorLoop, MonitorState

    started = Event()
    release = Event()
    finished = Event()
    rendered: list[tuple[int, bool, bool, tuple[str, ...]]] = []

    class SlowWorkflow:
        name = "slow"

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del trigger
            started.set()
            release.wait(timeout=0.2)
            frame.add_block("slow", [f"finished at {state.tick}"])
            finished.set()

    def record_tick(frame: MonitorFrame, state: MonitorState) -> None:
        rendered.append(
            (
                state.tick,
                bool(frame.blocks),
                finished.is_set(),
                tuple(frame.status_lines),
            )
        )
        if len(rendered) == 2:
            release.set()

    loop = MonitorLoop(
        workflows=(SlowWorkflow(),),
        interval_sec=0.01,
        max_ticks=3,
    )

    loop.run(on_tick=record_tick)

    assert started.is_set()
    assert [row[:3] for row in rendered] == [
        (1, False, False),
        (2, False, False),
        (3, True, True),
    ]
    assert any(
        "workflow: fetching account data" in status_lines
        for _, _, is_finished, status_lines in rendered
        if not is_finished
    )
    assert "workflow: fetching account data" not in rendered[-1][3]
    assert finished.is_set()
    assert loop._workflow_thread is not None
    assert not loop._workflow_thread.is_alive()


def test_agent_accounts_monitor_once_uses_loop_max_ticks(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    _stub_monitor_account_status(monkeypatch)

    assert main(["agent", "accounts", "monitor", "--once", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tick"] == 1
    assert payload["workflow_run_counts"] == {}
    assert payload["frame"]["blocks"][0]["data"]["targets"][0]["status"] == "pending"


def test_agent_accounts_monitor_max_ticks_uses_same_loop_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    calls = _stub_monitor_account_status(monkeypatch)

    assert (
        main(
            [
                "agent",
                "accounts",
                "monitor",
                "--max-ticks",
                "3",
                "--interval-sec",
                "0.01",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tick"] == 3
    assert payload["workflow_run_counts"] == {"limits-tracking": 1}
    assert len(calls) == 1


def test_agent_accounts_monitor_clock_one_shot_alarm_fires_once() -> None:
    from agentos.agent.monitor import MONITOR_ENTER_ALARM, MonitorClock

    clock = MonitorClock()
    clock.set_one_shot(MONITOR_ENTER_ALARM)

    first = clock.step()
    second = clock.step()

    assert first.tick == 1
    assert first.fired(MONITOR_ENTER_ALARM)
    assert first.alarms[MONITOR_ENTER_ALARM].armed is False
    assert not second.fired(MONITOR_ENTER_ALARM)


def test_agent_accounts_monitor_clock_periodic_alarm_rearms() -> None:
    from agentos.agent.monitor import LIMITS_TRACKING_PERIODIC_ALARM, MonitorClock

    clock = MonitorClock()
    clock.set_periodic(LIMITS_TRACKING_PERIODIC_ALARM, period_ticks=2)

    first = clock.step()
    second = clock.step()
    third = clock.step()

    assert not first.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert first.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 1
    assert second.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert second.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 2
    assert not third.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert third.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 1


def test_agent_accounts_monitor_limits_periodic_alarm_adapts_after_automatic_fire() -> None:
    from agentos.agent.monitor import (
        LIMITS_TRACKING_PERIODIC_ALARM,
        MONITOR_STARTUP_ALARM,
        MonitorFrame,
        MonitorLoop,
        MonitorState,
    )

    class PeriodicWorkflow:
        name = "limits-tracking"
        periodic_alarm_name = LIMITS_TRACKING_PERIODIC_ALARM
        refresh_interval_sec = 2

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, frame, trigger

    loop = MonitorLoop(
        workflows=(PeriodicWorkflow(),),
        interval_sec=1,
        max_ticks=1,
    )

    startup = loop._apply_adaptive_alarm_policy(loop.clock.step())
    first_refresh = loop._apply_adaptive_alarm_policy(loop.clock.step())
    waiting = loop._apply_adaptive_alarm_policy(loop.clock.step())
    waiting_again = loop._apply_adaptive_alarm_policy(loop.clock.step())
    second_refresh = loop._apply_adaptive_alarm_policy(loop.clock.step())

    assert startup.fired(MONITOR_STARTUP_ALARM)
    assert startup.alarms[LIMITS_TRACKING_PERIODIC_ALARM].period_ticks == 2
    assert first_refresh.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert first_refresh.alarms[LIMITS_TRACKING_PERIODIC_ALARM].period_ticks == 3
    assert first_refresh.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 3
    assert not waiting.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert not waiting_again.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert second_refresh.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert second_refresh.alarms[LIMITS_TRACKING_PERIODIC_ALARM].period_ticks == 4


def test_agent_accounts_monitor_enter_resets_adaptive_limits_period() -> None:
    from agentos.agent.monitor import (
        LIMITS_TRACKING_PERIODIC_ALARM,
        MONITOR_ENTER_ALARM,
        MonitorFrame,
        MonitorLoop,
        MonitorState,
    )

    class PeriodicWorkflow:
        name = "limits-tracking"
        periodic_alarm_name = LIMITS_TRACKING_PERIODIC_ALARM
        refresh_interval_sec = 2

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, frame, trigger

    loop = MonitorLoop(
        workflows=(PeriodicWorkflow(),),
        interval_sec=1,
        max_ticks=1,
    )

    loop._apply_adaptive_alarm_policy(loop.clock.step())
    loop._apply_adaptive_alarm_policy(loop.clock.step())
    loop.set_alarm(MONITOR_ENTER_ALARM)
    manual = loop._apply_adaptive_alarm_policy(loop.clock.step())

    assert manual.fired(MONITOR_ENTER_ALARM)
    assert manual.alarms[LIMITS_TRACKING_PERIODIC_ALARM].period_ticks == 2
    assert manual.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 2


def test_agent_accounts_monitor_enter_wins_over_simultaneous_periodic_alarm() -> None:
    from agentos.agent.monitor import (
        LIMITS_TRACKING_PERIODIC_ALARM,
        MONITOR_ENTER_ALARM,
        MonitorFrame,
        MonitorLoop,
        MonitorState,
    )

    class PeriodicWorkflow:
        name = "limits-tracking"
        periodic_alarm_name = LIMITS_TRACKING_PERIODIC_ALARM
        refresh_interval_sec = 2

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, frame, trigger

    loop = MonitorLoop(
        workflows=(PeriodicWorkflow(),),
        interval_sec=1,
        max_ticks=1,
    )

    loop._apply_adaptive_alarm_policy(loop.clock.step())
    loop.set_alarm(MONITOR_ENTER_ALARM)
    simultaneous = loop._apply_adaptive_alarm_policy(loop.clock.step())

    assert simultaneous.fired(MONITOR_ENTER_ALARM)
    assert simultaneous.fired(LIMITS_TRACKING_PERIODIC_ALARM)
    assert simultaneous.alarms[LIMITS_TRACKING_PERIODIC_ALARM].period_ticks == 2
    assert simultaneous.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 2


def test_agent_accounts_monitor_startup_does_not_increase_limits_period() -> None:
    from agentos.agent.monitor import (
        LIMITS_TRACKING_PERIODIC_ALARM,
        MONITOR_STARTUP_ALARM,
        MonitorFrame,
        MonitorLoop,
        MonitorState,
    )

    class PeriodicWorkflow:
        name = "limits-tracking"
        periodic_alarm_name = LIMITS_TRACKING_PERIODIC_ALARM
        refresh_interval_sec = 2

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, frame, trigger

    loop = MonitorLoop(
        workflows=(PeriodicWorkflow(),),
        interval_sec=1,
        max_ticks=1,
    )

    startup = loop._apply_adaptive_alarm_policy(loop.clock.step())

    assert startup.fired(MONITOR_STARTUP_ALARM)
    assert startup.alarms[LIMITS_TRACKING_PERIODIC_ALARM].period_ticks == 2
    assert startup.alarms[LIMITS_TRACKING_PERIODIC_ALARM].remaining_ticks == 1


def test_agent_accounts_monitor_refreshes_after_clock_periodic_alarm(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "refresh_interval_sec": 0.02,
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    calls = _stub_monitor_account_status(monkeypatch)

    assert (
        main(
            [
                "agent",
                "accounts",
                "monitor",
                "--max-ticks",
                "3",
                "--interval-sec",
                "0.01",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert len(calls) == 2
    target_states = payload["state"]["limits-tracking"]["targets"]
    target_state = next(iter(target_states.values()))
    assert target_state["refresh_count"] == 2
    assert target_state["last_refresh_tick"] == 2
    assert payload["frame"]["blocks"][0]["title"].startswith(
        "limits-tracking | next in "
    )


def test_agent_accounts_monitor_manual_trigger_forces_limits_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agentos.agent.monitor import (
        LimitsTrackingWorkflow,
        MONITOR_ENTER_ALARM,
        MonitorLoop,
        MonitorTarget,
        MonitorWorkflowConfig,
    )

    calls = _stub_monitor_account_status(monkeypatch)
    loop = MonitorLoop(
        workflows=(
            LimitsTrackingWorkflow(
                MonitorWorkflowConfig(
                    name="limits-tracking",
                    targets=(
                        MonitorTarget(
                            provider="codex",
                            account="br",
                            home=tmp_path / "home",
                        ),
                    ),
                    refresh_interval_sec=60,
                    raw_config={},
                )
            ),
        ),
        interval_sec=0.01,
        max_ticks=5,
    )

    def request_manual_refresh(frame, state) -> None:
        del frame, state
        if len(calls) == 1:
            loop.set_alarm(MONITOR_ENTER_ALARM)

    loop.run(on_tick=request_manual_refresh, wait_for_first_frame=True)

    assert len(calls) == 2


def test_agent_accounts_monitor_unrelated_alarm_runs_workflow_without_provider_fetch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agentos.agent.monitor import (
        LimitsTrackingWorkflow,
        MonitorLoop,
        MonitorTarget,
        MonitorWorkflowConfig,
    )

    calls = _stub_monitor_account_status(monkeypatch)
    loop = MonitorLoop(
        workflows=(
            LimitsTrackingWorkflow(
                MonitorWorkflowConfig(
                    name="limits-tracking",
                    targets=(
                        MonitorTarget(
                            provider="codex",
                            account="br",
                            home=tmp_path / "home",
                        ),
                    ),
                    refresh_interval_sec=60,
                    raw_config={},
                )
            ),
        ),
        interval_sec=0.01,
        max_ticks=5,
    )

    def request_scheduled_refresh(frame, state) -> None:
        del frame, state
        if loop.state.workflow_run_counts.get("limits-tracking") == 1:
            loop.set_alarm("custom.service")

    _, state = loop.run(on_tick=request_scheduled_refresh, wait_for_first_frame=True)

    assert len(calls) == 1
    assert state.workflow_run_counts == {"limits-tracking": 2}


def test_agent_accounts_monitor_target_error_is_workflow_owned(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first_auth = tmp_path / "first.json"
    second_auth = tmp_path / "second.json"
    _write(first_auth, _auth_json(account_id="acc_br", email="br@example.com"))
    _write(second_auth, _auth_json(account_id="acc_jp", email="jp@example.com"))

    assert main(_register_args(first_auth, account="br")) == 0
    capsys.readouterr()
    assert main(_register_args(second_auth, account="jp")) == 0
    capsys.readouterr()
    br_home = agentos_home / "agent" / "homes" / "codex" / "br"
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [
                    {"provider": "codex", "account": "br"},
                    {"provider": "codex", "account": "jp"},
                ],
            },
        ],
    )
    _stub_monitor_account_status(monkeypatch, failures={f"codex/br@{br_home}"})

    assert (
        main(
            [
                "agent",
                "accounts",
                "monitor",
                "--max-ticks",
                "3",
                "--interval-sec",
                "0.01",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert "workflow_errors" not in payload["state"]
    assert payload["frame"]["errors"] == []
    targets = payload["frame"]["blocks"][0]["data"]["targets"]
    assert [target["status"] for target in targets] == ["error", "ok"]
    assert targets[0]["error"]["type"] == "RuntimeError"
    assert targets[0]["error"]["message"] == "cannot refresh br"
    assert "    error | cannot refresh br" in payload["frame"]["blocks"][0]["lines"]


def test_agent_accounts_monitor_workflow_error_goes_to_state_and_frame() -> None:
    from agentos.agent.monitor import MonitorFrame, MonitorLoop, MonitorState

    class FailingWorkflow:
        name = "failing"

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del state, frame, trigger
            raise RuntimeError("boom")

    class PassingWorkflow:
        name = "passing"

        def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
            del state, frame

        def loop(self, state: MonitorState, frame: MonitorFrame, trigger) -> None:
            del trigger
            frame.add_block("passing", [f"status: ok at {frame.tick}"])

    loop = MonitorLoop(
        workflows=(FailingWorkflow(), PassingWorkflow()),
        interval_sec=0.01,
        max_ticks=2,
    )

    frame, state = loop.run(wait_for_first_frame=True)

    assert frame.errors == [
        "unexpected workflow loop error: failing: RuntimeError: boom",
    ]
    assert frame.blocks[0]["title"] == "passing"
    assert state.data["workflow_errors"] == [
        {
            "tick": 1,
            "workflow": "failing",
            "phase": "loop",
            "error_type": "RuntimeError",
            "message": "boom",
        },
    ]


def test_agent_accounts_monitor_runs_workflows_in_config_order(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "br"}],
            },
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    _stub_monitor_account_status(monkeypatch)

    assert (
        main(
            [
                "agent",
                "accounts",
                "monitor",
                "--max-ticks",
                "3",
                "--interval-sec",
                "0.01",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["frame"]["blocks"][0]["title"].startswith(
        "limits-tracking | next in "
    )
    assert payload["frame"]["blocks"][0]["data"]["run_count"] == 1
    assert payload["workflow_run_counts"] == {"limits-tracking": 1}


def test_agent_accounts_monitor_reports_unknown_workflow(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "future-workflow",
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )

    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert "unknown monitor workflow 'future-workflow'" in capsys.readouterr().err


def test_agent_accounts_monitor_reports_invalid_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    _write_monitor_config(
        agentos_home, [{"workflow": "limits-tracking", "targets": []}]
    )

    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].targets must not be empty" in capsys.readouterr().err
    )


@pytest.mark.parametrize("refresh_interval_sec", [0, -1, True, "slow"])
def test_agent_accounts_monitor_reports_invalid_refresh_interval(
    tmp_path: Path,
    monkeypatch,
    capsys,
    refresh_interval_sec: object,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    _write(source_auth, _auth_json())

    assert main(_register_args(source_auth, account="br")) == 0
    capsys.readouterr()
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "refresh_interval_sec": refresh_interval_sec,
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )

    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].refresh_interval_sec must be a positive number"
        in capsys.readouterr().err
    )


def test_agent_accounts_monitor_reports_missing_registered_account(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    agentos_home = _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "missing"}],
            },
        ],
    )

    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert "agent account is not registered: codex.missing" in capsys.readouterr().err
