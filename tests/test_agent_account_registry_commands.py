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
from agentos._core.process import ProcessResult
from agentos.agent.account_status import (
    AccountIdentity,
    AccountLimit,
    AccountStatus,
    AccountStatusError,
    UsageOverTimeLimitData,
)
from agentos.agent.providers import build_registered_account_agent
from agentos.agent.run_runtime import AgentRunResult
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


def _link_args(home: Path, *, account: str = "br", force: bool = False) -> list[str]:
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
    _set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source_auth = tmp_path / "source.json"
    target_home = tmp_path / "codex-home"
    _write(source_auth, _auth_json(account_id=account_id))

    assert main(_register_args(source_auth)) == 0
    capsys.readouterr()
    assert main(_link_args(target_home)) == 0
    capsys.readouterr()
    return target_home


def _stub_codex_login_status(monkeypatch, target_home: Path):
    import agentos.codex.account_status as codex_account_status

    def fake_execute_agent_command(command, *, run_config):
        assert command.env_overrides["CODEX_HOME"] == str(target_home.resolve())
        assert command.argv[-2:] == ("login", "status")
        assert run_config.process_mode == "capture"
        return ProcessResult(exit_code=0, stdout="Logged in using ChatGPT\n", stderr="")

    monkeypatch.setattr(
        codex_account_status, "execute_agent_command", fake_execute_agent_command
    )
    return codex_account_status


def _monitor_account_status(
    *, provider: str, account: str, home: Path
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
    monkeypatch, *, failures: set[str] | None = None
) -> list[str]:
    import agentos.agent.monitor.workflows as monitor_workflows

    calls: list[str] = []
    failed_targets = set() if failures is None else failures

    class FakeAgent:
        def __init__(self, *, provider: str, account: str, home: Path) -> None:
            self.provider = provider
            self.account = account
            self.home = home

        def account_status(self, *, refresh_usage: bool = False) -> AccountStatus:
            assert refresh_usage is True
            key = f"{self.provider}/{self.account}@{self.home}"
            calls.append(key)
            if key in failed_targets:
                raise RuntimeError(f"cannot refresh {self.account}")
            return _monitor_account_status(
                provider=self.provider, account=self.account, home=self.home
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
    assert main(_link_args(target_home)) == 0
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
    assert main(_link_args(target_home, account="jp")) == 0
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
    assert main(_link_args(unknown_home, force=True)) == 0
    assert (
        json.loads(capsys.readouterr().out)["target_before_link"]["classification"]
        == "unknown"
    )
    assert (unknown_home / "auth.json").read_text(encoding="utf-8") == auth_text
    assert main(_link_args(broken_home, force=True)) == 0
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
    assert agent.account is not None
    assert agent.account.account == "br"


def test_codex_account_status_reports_auth_check_without_usage_refresh(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    _stub_codex_login_status(monkeypatch, target_home)
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status()

    assert status.check_status == "ok"
    assert status.usage_status == "unavailable"
    assert status.link_state == "verified"
    assert status.identity_match == "verified"
    assert status.expected_identity.provider_account_id == "acc_123"
    assert status.fetched_identity is not None
    assert status.fetched_identity.provider_account_id == "acc_123"
    assert status.auth_summary == "Logged in using ChatGPT"
    assert status.limits == ()
    assert status.errors == ()


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

    _stub_codex_login_status(monkeypatch, target_home)
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


def test_codex_account_status_refresh_usage_parses_limits(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    codex_account_status = _stub_codex_login_status(monkeypatch, target_home)
    monkeypatch.setattr(
        codex_account_status,
        "_read_codex_account_rate_limits",
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

    status = agent.account_status(refresh_usage=True)

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
    payload = codex_account_status._read_codex_account_rate_limits(agent)

    assert observed["command"][-1] == "app-server"
    assert observed["env"]["CODEX_HOME"] == str(target_home.resolve())
    assert payload["rateLimits"]["limitId"] == "test-limit"


def test_codex_account_status_preserves_auth_when_usage_refresh_errors(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_home = _registered_linked_codex_home(tmp_path, monkeypatch, capsys)
    codex_account_status = _stub_codex_login_status(monkeypatch, target_home)

    def fail_rate_limits(agent):
        raise AccountStatusError(
            error_type="command_failed", message="rate limit failed"
        )

    monkeypatch.setattr(
        codex_account_status, "_read_codex_account_rate_limits", fail_rate_limits
    )
    agent = build_registered_account_agent(
        provider="codex", account="br", home=target_home
    )

    status = agent.account_status(refresh_usage=True)

    assert status.check_status == "ok"
    assert status.identity_match == "verified"
    assert status.usage_status == "error"
    assert status.limits == ()
    assert [error.summary() for error in status.usage_errors] == [
        {"type": "command_failed", "message": "rate limit failed"}
    ]


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


def test_claude_account_status_refresh_usage_uses_statusline_limits(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.claude.account_status as claude_account_status

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

    def fake_execute_agent_command(command, *, run_config):
        del command, run_config
        return AgentRunResult(exit_code=0, stdout="745\n", stderr="")

    def fake_collect_statusline_payload(agent):
        assert agent.home == claude_home.resolve()
        return {
            "rate_limits": {
                "five_hour": {
                    "used_percentage": 20,
                    "resets_at": 1_776_000_000,
                },
                "seven_day": {
                    "used_percentage": 94,
                    "resets_at": 1_776_604_800,
                },
            }
        }

    monkeypatch.setattr(
        claude_account_status, "execute_agent_command", fake_execute_agent_command
    )
    monkeypatch.setattr(
        claude_account_status,
        "_collect_claude_statusline_payload",
        fake_collect_statusline_payload,
    )
    agent = build_registered_account_agent(
        provider="claude-code", account="main", home=claude_home
    )

    status = agent.account_status(refresh_usage=True)

    assert status.check_status == "ok"
    assert status.usage_status == "ok"
    assert status.usage_errors == ()
    assert status.usage_summary == "Burst 20%, Weekly 94%"
    assert [limit.limit_name for limit in status.limits] == ["burst", "weekly"]
    assert [
        limit.usage_over_time.used_percent
        for limit in status.limits
        if limit.usage_over_time
    ] == [20, 94]


def test_agent_accounts_monitor_once_prints_account_status(
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

    assert main(["agent", "accounts", "monitor", "--once"]) == 0
    output = capsys.readouterr().out
    assert "Agent accounts monitor" in output
    assert "Tick: 1" in output
    assert "limits-tracking" in output
    assert "refresh_interval_sec: 60" not in output
    assert "    ⬢ codex/br:" in output
    assert "      usage/time |  3% / 37% = 0.1 | Burst" in output
    assert "          resets | " in output
    assert "      usage/time |  1% / 18% = 0.1 | Weekly" in output
    assert "under construction" not in output


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
                "0",
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
    assert payload["frame"]["blocks"][0]["lines"][0] == "  ⬢ codex/br:"
    assert payload["frame"]["blocks"][0]["rows"][0] == {
        "kind": "text",
        "text": "  ⬢ codex/br:",
    }
    assert any(
        row["kind"] == "usage_time" for row in payload["frame"]["blocks"][0]["rows"]
    )
    assert any(row["kind"] == "reset" for row in payload["frame"]["blocks"][0]["rows"])
    assert "  ⬢ codex/br:" in payload["frame"]["blocks"][0]["lines"]
    assert "  ⬢ codex/jp:" in payload["frame"]["blocks"][0]["lines"]
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

        def run(self, state: MonitorState, frame: MonitorFrame) -> None:
            seen_frames.append(id(frame))
            seen_states.append(id(state))
            state.data["recording"] = state.data.get("recording", 0) + 1
            if not frame.blocks:
                frame.add_block("recording", ["created"])

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


def test_agent_accounts_monitor_slow_workflow_does_not_block_render_ticks() -> None:
    from agentos.agent.monitor import MonitorFrame, MonitorLoop, MonitorState

    started = Event()
    release = Event()
    finished = Event()
    rendered: list[tuple[int, bool, bool]] = []

    class SlowWorkflow:
        name = "slow"

        def run(self, state: MonitorState, frame: MonitorFrame) -> None:
            started.set()
            release.wait(timeout=0.2)
            frame.add_block("slow", [f"finished at {state.tick}"])
            finished.set()

    def record_tick(frame: MonitorFrame, state: MonitorState) -> None:
        rendered.append((state.tick, bool(frame.blocks), finished.is_set()))
        if len(rendered) == 2:
            release.set()

    loop = MonitorLoop(
        workflows=(SlowWorkflow(),),
        interval_sec=0.01,
        max_ticks=2,
    )

    loop.run(on_tick=record_tick)

    assert started.is_set()
    assert rendered == [(1, False, False), (2, False, False)]
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
    assert payload["workflow_run_counts"] == {"limits-tracking": 1}


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
                "2",
                "--interval-sec",
                "0",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tick"] == 2
    assert payload["workflow_run_counts"] == {"limits-tracking": 1}
    assert len(calls) == 1


def test_agent_accounts_monitor_refreshes_after_workflow_interval(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import agentos.agent.monitor.workflows as monitor_workflows

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
                "refresh_interval_sec": 1,
                "targets": [{"provider": "codex", "account": "br"}],
            },
        ],
    )
    calls = _stub_monitor_account_status(monkeypatch)
    monotonic_values = iter([0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 1.1, 1.1])
    monkeypatch.setattr(
        monitor_workflows.time, "monotonic", lambda: next(monotonic_values)
    )

    assert (
        main(
            [
                "agent",
                "accounts",
                "monitor",
                "--max-ticks",
                "3",
                "--interval-sec",
                "0",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert len(calls) == 1
    target_states = payload["state"]["limits-tracking"]["targets"]
    target_state = next(iter(target_states.values()))
    assert target_state["refresh_count"] == 1
    assert target_state["last_refresh_tick"] == 1


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

    assert main(["agent", "accounts", "monitor", "--once", "--json"]) == 0
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

        def run(self, state: MonitorState, frame: MonitorFrame) -> None:
            raise RuntimeError("boom")

    class PassingWorkflow:
        name = "passing"

        def run(self, state: MonitorState, frame: MonitorFrame) -> None:
            frame.add_block("passing", [f"status: ok at {frame.tick}"])

    loop = MonitorLoop(
        workflows=(FailingWorkflow(), PassingWorkflow()),
        interval_sec=0,
        max_ticks=1,
    )

    frame, state = loop.run(wait_for_first_frame=True)

    assert frame.errors == [
        "unexpected workflow error: failing: RuntimeError: boom",
    ]
    assert frame.blocks[0]["title"] == "passing"
    assert state.data["workflow_errors"] == [
        {
            "tick": 1,
            "workflow": "failing",
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

    assert main(["agent", "accounts", "monitor", "--once", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [block["title"] for block in payload["frame"]["blocks"]] == [
        "limits-tracking"
    ]
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
