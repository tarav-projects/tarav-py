# $kw: ^agent-account-command-boundary --from Agentos.Hook --note [DC] provider lifecycle hook reporting enters through the general hook command rather than a parallel account command --supp ^c20260811-47u
"""`agent accounts` lifecycle commands (capture, activate, rotate, materialize, status)."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent._cli_common import format_json_output
from agentos.agent.commands._shared import (
    _AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
)
from agentos.agent.commands.monitor import _register_monitor_command


def _split_account_method(account: str, command_label: str) -> tuple[str, str]:
    """Parse ``<account-id>/<method>``, raising a uniform CliError when malformed."""
    account_id, sep, method = account.partition("/")
    if not sep or not account_id or not method:
        raise CliError(f"{command_label} requires --account <account-id>/<method>")
    return account_id, method


def _resolve_providers(provider: str | None) -> tuple[str, ...]:
    """The given provider, else every provider with an auth-method."""
    from agentos.agent.auth_method_registry import providers_with_auth_methods

    if provider is not None:
        return (provider,)
    return tuple(providers_with_auth_methods())


def _short(ref: str | None) -> str:
    """12-char short form of a ref_id; ``-`` for a missing ref."""
    return (ref or "-")[:12]


def _cmd_agent_accounts_materialize(args: argparse.Namespace) -> int:
    if args.provider in ("claude-code", "codex"):
        return _materialize_account(args, args.provider)
    raise CliError(
        f"agent accounts materialize is not supported for provider {args.provider}"
    )


def _cmd_agent_accounts_capture(args: argparse.Namespace) -> int:
    if getattr(args, "global_sweep", False):
        return _cmd_agent_accounts_capture_global(args)

    from agentos.agent.capture import capture_home

    if args.provider is None:
        raise CliError("agent accounts capture requires --provider (or --global)")
    if args.home is None:
        raise CliError("agent accounts capture requires --home (or --global)")
    provider = args.provider
    home = Path(args.home)
    dry_run = getattr(args, "dry_run", False)
    result = capture_home(provider, home, dry_run=dry_run)
    if result is None:
        raise CliError(f"no Auth.Data could be read from home: {home}")
    payload = {
        "command": "agent accounts capture",
        "provider": provider,
        "home": str(home),
        "account": result.account,
        "method": result.method,
        "ref_id": result.ref_id,
        "artifact_id": result.artifact_id,
        "dry_run": dry_run,
    }
    if args.json:
        print(format_json_output(payload))
    else:
        prefix = "[dry-run] would capture" if dry_run else "Captured"
        print(
            f"{prefix} {provider} {result.account}/{result.method} <- {home} "
            f"(ref {_short(result.ref_id)})"
        )
    return 0


def _cmd_agent_accounts_capture_global(args: argparse.Namespace) -> int:
    from agentos.agent.capture import capture_all_homes

    if args.home is not None:
        raise CliError(
            "agent accounts capture: --global and --home are mutually exclusive"
        )
    dry_run = getattr(args, "dry_run", False)
    providers = _resolve_providers(args.provider)
    results = [
        r
        for provider in providers
        for r in capture_all_homes(provider, dry_run=dry_run)
    ]
    new_count = sum(1 for r in results if r.is_new)
    if args.json:
        payload = {
            "command": "agent accounts capture --global",
            "providers": list(providers),
            "dry_run": dry_run,
            "captured": [
                {
                    "provider": r.provider,
                    "home": str(r.home),
                    "account": r.account,
                    "method": r.method,
                    "ref_id": r.ref_id,
                    "artifact_id": r.artifact_id,
                    "new": r.is_new,
                }
                for r in results
            ],
            "new": new_count,
        }
        print(format_json_output(payload))
    else:
        prefix = "[dry-run] would capture" if dry_run else "Captured"
        for r in results:
            state = "new" if r.is_new else "already"
            print(
                f"{prefix} {r.provider} {r.account}/{r.method} <- {r.home} "
                f"(ref {_short(r.ref_id)}, {state})"
            )
        verb = "Would sweep" if dry_run else "Swept"
        print(
            f"{verb} {len(results)} home(s) across {len(providers)} provider(s); {new_count} new."
        )
    return 0


def _cmd_agent_accounts_list(args: argparse.Namespace) -> int:
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    if args.account is not None and args.provider is None:
        raise CliError("agent accounts list --account requires --provider")
    providers = _resolve_providers(args.provider)

    pools: list[dict[str, object]] = []
    for provider in providers:
        for account_id, method in _account_method_pairs(provider, args.account):
            active = R.active_ref(provider, account_id, method)
            head_result = rotate(provider, account_id, method, dry_run=True)
            head = head_result.new_active if not head_result.skipped else None
            entries = [
                {
                    "index": i,
                    "ref_id": e["ref_id"],
                    "ts": e["ts"],
                    "active": e["ref_id"] == active,
                    "head": e["ref_id"] == head,
                }
                for i, e in enumerate(R.pool_for(provider, account_id, method))
            ]
            pools.append(
                {
                    "provider": provider,
                    "account": f"{account_id}/{method}",
                    "entries": entries,
                }
            )

    if args.json:
        print(format_json_output({"command": "agent accounts list", "pools": pools}))
    else:
        for pool in pools:
            print(f"{pool['provider']} {pool['account']}")
            if not pool["entries"]:
                print("  (no captures)")
            for e in pool["entries"]:
                marks = " ".join(
                    m for m, on in (("active", e["active"]), ("head", e["head"])) if on
                )
                suffix = f"  ({marks})" if marks else ""
                print(f"  {e['index']}  {_short(e['ref_id'])}  {e['ts']}{suffix}")
    return 0


def _account_method_pairs(provider: str, account: str | None) -> list[tuple[str, str]]:
    from agentos.agent import auth_registry as R

    if account is not None:
        return [_split_account_method(account, "agent accounts list")]
    accounts = R.load_settings(provider).get("accounts")
    pairs: list[tuple[str, str]] = []
    if isinstance(accounts, dict):
        for account_id, record in accounts.items():
            methods = record.get("auth_methods") if isinstance(record, dict) else None
            if isinstance(methods, dict):
                pairs.extend((account_id, method) for method in methods)
    return pairs


def _cmd_agent_accounts_orphans(args: argparse.Namespace) -> int:
    from agentos.agent import auth_registry as R

    providers = _resolve_providers(args.provider)


    groups = [
        {
            "provider": provider,
            "identity": g["identity"],
            "auth_class": g["auth_class"],
            "refs": g["refs"],
        }
        for provider in providers
        for g in R.orphan_groups(provider)
    ]

    if args.json:

        orphans = []
        for g in groups:
            refs = []
            for r in g["refs"]:
                artifact_id = r.get("artifact_id")
                auth = (
                    R.read_artifact(g["provider"], artifact_id)
                    if isinstance(artifact_id, str)
                    else None
                )
                refs.append(
                    {**r, "auth_data": dict(auth.payload) if auth is not None else None}
                )
            orphans.append({**g, "refs": refs})
        print(
            format_json_output(
                {
                    "command": "agent accounts orphans",
                    "providers": list(providers),
                    "orphans": orphans,
                }
            )
        )
    else:
        for provider in providers:
            print(provider)
            provider_groups = [g for g in groups if g["provider"] == provider]
            if not provider_groups:
                print("  (no orphans)")
                continue
            for g in provider_groups:
                ident = g["identity"] if isinstance(g["identity"], dict) else {}
                who = ident.get("provider_account_id") or "(no identity)"
                extra = "  ".join(
                    str(x) for x in (ident.get("email"), ident.get("label")) if x
                )
                header = f"  {who}  [{g['auth_class']}]"
                print(f"{header}  {extra}".rstrip())
                for r in g["refs"]:
                    print(f"    {_short(str(r['ref_id']))}  {r.get('ts')}")
    return 0


def _cmd_agent_accounts_rotate(args: argparse.Namespace) -> int:
    from agentos.agent.capture import capture_all_homes
    from agentos.agent.materialization import MaterializeResult, materialize_all
    from agentos.agent.rotation import RotateResult, rotate, rotate_all

    dry_run = getattr(args, "dry_run", False)
    no_capture = getattr(args, "no_capture", False)
    do_materialize = getattr(args, "materialize", False)
    if args.account is not None and args.provider is None:
        raise CliError("agent accounts rotate --account requires --provider")
    providers = _resolve_providers(args.provider)

    results: list[RotateResult] = []
    materialized: list[MaterializeResult] = []
    for provider in providers:


        if not no_capture:
            capture_all_homes(provider, dry_run=dry_run)
        if args.account is not None:
            account_id, method = _split_account_method(
                args.account, "agent accounts rotate"
            )
            results.append(rotate(provider, account_id, method, dry_run=dry_run))
        else:
            results.extend(rotate_all(provider, dry_run=dry_run))



        if do_materialize:
            materialized.extend(materialize_all(provider, check=dry_run))

    changed = sum(1 for r in results if r.changed)
    written = sum(1 for m in materialized if m.status in ("materialized", "check"))
    if args.json:
        payload = {
            "command": "agent accounts rotate",
            "providers": list(providers),
            "dry_run": dry_run,
            "rotated": [
                {
                    "provider": r.provider,
                    "account": r.account,
                    "method": r.method,
                    "previous_active": r.previous_active,
                    "new_active": r.new_active,
                    "changed": r.changed,
                    "skipped": r.skipped,
                }
                for r in results
            ],
            "changed": changed,
            "materialized": [
                {
                    "provider": m.provider,
                    "account": m.account,
                    "method": m.method,
                    "home": str(m.home),
                    "active_ref": m.active_ref,
                    "status": m.status,
                }
                for m in materialized
            ],
        }
        print(format_json_output(payload))
    else:
        for r in results:
            if r.skipped:
                state = "skipped"
            elif r.changed:
                prefix = "[dry-run] would rotate" if dry_run else "rotated"
                state = (
                    f"{prefix} {_short(r.previous_active)} -> {_short(r.new_active)}"
                )
            else:
                state = "unchanged"
            print(f"{r.provider} {r.account}/{r.method}: {state}")
        verb = "Would change" if dry_run else "Changed"
        print(
            f"{verb} {changed} active pointer(s) across {len(results)} account/method(s)."
        )
        if do_materialize:
            for m in materialized:
                if m.status == "materialized":
                    label = "[dry-run] would materialize" if dry_run else "materialized"
                    detail = f"{label} (ref {_short(m.active_ref)})"
                elif m.status == "check":
                    detail = f"[dry-run] would materialize (ref {_short(m.active_ref)})"
                else:
                    detail = m.status
                print(f"  {m.provider} {m.home}: {detail}")
            mverb = "Would materialize" if dry_run else "Materialized"
            print(f"{mverb} {written} home(s).")
    return 0


def _cmd_agent_accounts_activate(args: argparse.Namespace) -> int:
    from agentos.agent.activation import activate

    provider = args.provider
    account_id, method = _split_account_method(args.account, f"{provider} activate")
    result = activate(provider, account_id, method, args.ref)
    payload = {
        "command": "agent accounts activate",
        "provider": provider,
        "account": args.account,
        "ref_id": result.ref_id,
    }
    if args.json:
        print(format_json_output(payload))
    else:
        print(f"Activated {provider} {args.account} -> {_short(result.ref_id)}")
    return 0


def _materialize_account(args: argparse.Namespace, provider: str) -> int:
    from agentos.agent.materialization import materialize_account

    account_id, method = _split_account_method(args.account, f"{provider} materialize")

    result = materialize_account(
        provider, account_id, method, Path(args.home), check=args.check
    )

    payload = {
        "command": "agent accounts materialize",
        "provider": provider,
        "account": args.account,
        "home": str(result.home),
        "active_ref": result.active_ref,
        "captured_ref": result.captured_ref,
        "status": result.status,
    }
    if args.json:
        print(format_json_output(payload))
    else:
        verb = {
            "materialized": "Materialized",
            "check": "Would materialize",
            "aligned": "Already aligned",
        }[result.status]
        line = f"{verb} {provider} {args.account} -> {result.home} (ref {_short(result.active_ref)})"
        if result.captured_ref is not None:
            line += f"; captured-first {_short(result.captured_ref)}"
        print(line)
    return 0


def _cmd_agent_accounts_status(args: argparse.Namespace) -> int:
    from agentos.agent.account_status_report import (
        build_status_report,
        format_status_report,
    )

    providers = (
        (args.provider,)
        if args.provider is not None
        else _AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES
    )
    home_filter = (
        str(Path(args.home).expanduser().resolve()) if args.home is not None else None
    )

    reports = []
    for provider in providers:
        payload = build_status_report(provider)
        if home_filter is not None:
            homes = [h for h in payload["homes"] if h.get("home") == home_filter]
            payload = {**payload, "homes": homes}
        reports.append(payload)

    if args.json:
        print(
            format_json_output(
                reports[0] if args.provider is not None else {"reports": reports}
            )
        )
    else:
        print("\n".join(format_status_report(p) for p in reports))
    return 0


def _register_accounts_commands(agent_subparsers) -> None:
    accounts_parser = agent_subparsers.add_parser(
        "accounts",
        help="Query configured account status across supported providers.",
    )
    accounts_subparsers = accounts_parser.add_subparsers(
        dest="agent_accounts_command",
        required=True,
    )

    accounts_list_parser = accounts_subparsers.add_parser(
        "list",
        help="List the captured Auth.Refs (ref_ids) for an account/method, newest first.",
    )
    accounts_list_parser.add_argument(
        "--provider",
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family. Without it, list every provider with an auth-method.",
    )
    accounts_list_parser.add_argument(
        "--account",
        help="Scope to one account as <account-id>/<method> (requires --provider).",
    )
    accounts_list_parser.add_argument(
        "--json", action="store_true", help="Output as JSON."
    )
    accounts_list_parser.set_defaults(handler=_cmd_agent_accounts_list)

    accounts_orphans_parser = accounts_subparsers.add_parser(
        "orphans",
        help="List captured orphans (the _unknown bucket) grouped by identity, for manual adoption.",
    )
    accounts_orphans_parser.add_argument(
        "--provider",
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family. Without it, list orphans for every provider with an auth-method.",
    )
    accounts_orphans_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON, including the full Auth.Data payload per ref (secrets).",
    )
    accounts_orphans_parser.set_defaults(handler=_cmd_agent_accounts_orphans)

    accounts_capture_parser = accounts_subparsers.add_parser(
        "capture",
        help="Capture (archive) the Auth.Data present in a provider home. Read-only on the home.",
    )
    accounts_capture_parser.add_argument(
        "--provider",
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family. Required unless --global (which scopes the sweep if given).",
    )
    accounts_capture_parser.add_argument(
        "--home", help="Provider home to capture from."
    )
    accounts_capture_parser.add_argument(
        "--global",
        dest="global_sweep",
        action="store_true",
        help="Sweep every profile home (all providers with an auth-method) instead of one --home.",
    )
    accounts_capture_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Report what would be captured without writing to the registry (read-only).",
    )
    accounts_capture_parser.add_argument(
        "--json", action="store_true", help="Output as JSON."
    )
    accounts_capture_parser.set_defaults(handler=_cmd_agent_accounts_capture)

    accounts_activate_parser = accounts_subparsers.add_parser(
        "activate",
        help="Set a captured artifact as the active Auth.Data for an account/method.",
    )
    accounts_activate_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family.",
    )
    accounts_activate_parser.add_argument(
        "--account",
        required=True,
        help="Target account as <account-id>/<method>.",
    )
    accounts_activate_parser.add_argument(
        "--ref",
        required=True,
        help="Auth.Ref id (ref_id) to activate.",
    )
    accounts_activate_parser.add_argument(
        "--json", action="store_true", help="Output as JSON."
    )
    accounts_activate_parser.set_defaults(handler=_cmd_agent_accounts_activate)

    accounts_rotate_parser = accounts_subparsers.add_parser(
        "rotate",
        help="Activate the head-of-line captured artifact per account/method. Captures first; homes read-only.",
    )
    accounts_rotate_parser.add_argument(
        "--provider",
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family. Without it, rotate every provider with an auth-method.",
    )
    accounts_rotate_parser.add_argument(
        "--account",
        help="Scope to one account as <account-id>/<method> (requires --provider).",
    )
    accounts_rotate_parser.add_argument(
        "--no-capture",
        dest="no_capture",
        action="store_true",
        help="Rotate the existing capture pool only; do not capture homes first.",
    )
    accounts_rotate_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Report the intended active flips without writing (read-only).",
    )
    accounts_rotate_parser.add_argument(
        "--materialize",
        action="store_true",
        help="After rotating, reconcile homes — push each home's active Auth.Ref into stale homes.",
    )
    accounts_rotate_parser.add_argument(
        "--json", action="store_true", help="Output as JSON."
    )
    accounts_rotate_parser.set_defaults(handler=_cmd_agent_accounts_rotate)

    accounts_materialize_parser = accounts_subparsers.add_parser(
        "materialize",
        help="Materialize a managed provider account credential into a provider runtime target.",
    )
    accounts_materialize_parser.add_argument(
        "--provider",
        required=True,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to materialize.",
    )
    accounts_materialize_parser.add_argument(
        "--home",
        required=True,
        help="Provider home to receive credential materialization.",
    )
    accounts_materialize_parser.add_argument(
        "--account",
        required=True,
        help="Local AgentOS account alias to materialize.",
    )
    accounts_materialize_parser.add_argument(
        "--check",
        action="store_true",
        help="Report intended materialization without mutating the provider home.",
    )
    accounts_materialize_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )
    accounts_materialize_parser.set_defaults(handler=_cmd_agent_accounts_materialize)

    accounts_status_parser = accounts_subparsers.add_parser(
        "status",
        help="Inspect provider home auth state against managed account storage.",
    )
    accounts_status_parser.add_argument(
        "--provider",
        default=None,
        choices=_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES,
        help="Provider family to inspect. Omit with no --home to show all account registry status.",
    )
    accounts_status_parser.add_argument(
        "--home",
        default=None,
        help="Provider home to inspect. Requires --provider.",
    )
    accounts_status_parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw status payload as JSON.",
    )
    accounts_status_parser.set_defaults(handler=_cmd_agent_accounts_status)

    _register_monitor_command(accounts_subparsers)
