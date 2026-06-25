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

from agentos.agent import auth_registry as R
from agentos.agent.auth_method_registry import auth_method_for_class
from agentos.agent.config import load_agent_profile_entries


@dataclass(frozen=True)
class HomeTarget:
    home: Path
    provider: str
    candidates: frozenset[str]  # "<account-id>/<method>" addresses


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

    # try each distinct candidate method-class; first non-empty read wins
    for candidate in sorted(target.candidates):
        account_hint, _, method_hint = candidate.partition("/")
        auth_class = R.method_class(provider, account_hint, method_hint)
        method = auth_method_for_class(provider, auth_class) if auth_class else None
        if method is None:
            continue
        auth = method.read_auth_data(target.home)
        if auth is None:
            continue
        identity = method.extract_identity(auth)
        account = (
            R.resolve_account_by_identity(provider, identity) if identity is not None else None
        )
        if account is None or account not in candidate_accounts:
            return _entry(target, status="error:unlisted-account", account=account, reason="identity not among candidates")
        # the candidate method for the resolved account
        method_name = next(
            (c.split("/", 1)[1] for c in target.candidates if c.split("/", 1)[0] == account),
            method_hint,
        )
        active = R.active_artifact_id(provider, account, method_name)
        if active is not None and active == auth.content_id():
            return _entry(target, status="aligned", account=account, method=method_name)
        reason = (
            "home Auth.Data is not the active one"
            if active is not None
            else "no active artifact registered for this account/method"
        )
        return _entry(target, status="drift", account=account, method=method_name, reason=reason)

    return _entry(target, status="undeterminable", reason="no Auth.Data could be read from the home")


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
