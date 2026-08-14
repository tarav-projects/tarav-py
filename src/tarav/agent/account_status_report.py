# $kw: --from Account.Management
"""Home-centric, read-only account status — the all-homes drift report.

For every home declared by a profile, read its `Home.State`, project to an
`Auth.Ref`, and check it against the `Auth.Registry`. Never writes a home and
makes no provider/network call. Profiles supply the home paths, the provider,
and the candidate accounts (the allow-list); deeper profile-expectation
semantics are deferred.

Per-home status (V1): ``undeterminable`` | ``aligned`` | ``drift`` | ``error:unlisted-account``.
See `Account.Management` (`Auth.Data.Aligned` / `Auth.Data.Drift`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarav.agent import auth_registry as R
from tarav.agent.auth_method_registry import read_home_auth
from tarav.agent.config import load_agent_profile_entries
from tarav.agent.rotation import drift_against_active


@dataclass(frozen=True)
class HomeTarget:
    home: Path
    provider: str
    candidates: frozenset[str]


def collect_home_targets(provider: str) -> list[HomeTarget]:
    """Union of all profile homes for a provider, deduped, with merged candidate sets."""

    merged: dict[Path, set[str]] = {}
    for entry in load_agent_profile_entries():
        raw = entry.raw_profile
        if raw.get("provider") != provider:
            continue
        candidates = {a for a in raw.get("accounts", []) if isinstance(a, str)}
        for home in raw.get("homes", []):
            if not isinstance(home, str):
                continue
            key = Path(home).expanduser().resolve()
            merged.setdefault(key, set()).update(candidates)
    return [
        HomeTarget(home=home, provider=provider, candidates=frozenset(cands))
        for home, cands in sorted(merged.items(), key=lambda kv: str(kv[0]))
    ]


def status_for_home(target: HomeTarget) -> dict[str, object]:
    provider = target.provider
    candidate_accounts = {c.split("/", 1)[0] for c in target.candidates}

    found = read_home_auth(provider, target.home)
    if found is None:
        return _entry(target, status="undeterminable", reason="no Auth.Data could be read from the home")

    account = (
        R.resolve_account_by_identity(provider, found.identity) if found.identity is not None else None
    )
    if account is None or account not in candidate_accounts:
        return _entry(target, status="error:unlisted-account", account=account, reason="identity not among candidates")

    method_name = R.method_for_class(provider, account, found.method.name) or found.method.name
    active = R.active_ref(provider, account, method_name)
    if active is None:
        return _entry(target, status="drift:no-active", account=account, method=method_name,
                      reason="no active ref registered for this account/method — rotate")
    if active == found.method.ref_id(found.auth):
        return _entry(target, status="aligned", account=account, method=method_name)

    direction = drift_against_active(provider, account, method_name, found.method, found.auth)
    if direction == "newer":
        return _entry(target, status="drift:home-newer", account=account, method=method_name,
                      reason="home credential is newer than active — rotate")
    if direction == "older":
        return _entry(target, status="drift:home-older", account=account, method=method_name,
                      reason="active credential is newer than home — materialize")
    return _entry(target, status="drift", account=account, method=method_name,
                  reason="home differs from active but freshness is unorderable")


def _entry(target: HomeTarget, *, status: str, account: str | None = None,
           method: str | None = None, reason: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"home": str(target.home), "status": status}
    if account is not None:
        payload["account"] = account
    if method is not None:
        payload["method"] = method
    if reason is not None:
        payload["reason"] = reason
    return payload


def build_status_report(provider: str) -> dict[str, object]:
    homes = [status_for_home(t) for t in collect_home_targets(provider)]
    return {"command": "agent accounts status", "provider": provider, "homes": homes}


def format_status_report(payload: dict[str, object]) -> str:
    lines = [f"Account status — {payload.get('provider', '<unknown>')}"]
    homes = payload.get("homes")
    if not isinstance(homes, list) or not homes:
        lines.append("  (no homes declared by profiles)")
        return "\n".join(lines)
    for item in homes:
        if not isinstance(item, dict):
            continue
        status = item.get("status", "<unknown>")
        who = item.get("account")
        method = item.get("method")
        tag = f" {who}/{method}" if who and method else (f" {who}" if who else "")
        line = f"  [{status}]{tag}  {item.get('home', '')}"
        reason = item.get("reason")
        if reason and status != "aligned":
            line += f"  — {reason}"
        lines.append(line)
    return "\n".join(lines)


__all__ = ["build_status_report", "format_status_report", "collect_home_targets", "status_for_home", "HomeTarget"]
