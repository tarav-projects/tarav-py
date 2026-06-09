from __future__ import annotations

from pathlib import Path
from typing import Iterable

from agentos._core.errors import CliError
from agentos.agent.account_status import AgentAccountContext


def allowed_account_ids(accounts: Iterable[AgentAccountContext]) -> tuple[str, ...]:
    return tuple(account.account for account in accounts)


def allowed_home_paths(homes: Iterable[Path]) -> tuple[str, ...]:
    return tuple(str(home.expanduser().resolve()) for home in homes)


def format_allowed_values(values: Iterable[str]) -> str:
    return ", ".join(sorted(values))


def validate_account_override(
    *,
    profile_id: str,
    allowed_accounts: Iterable[AgentAccountContext],
    account: str | None,
) -> None:
    if account is None:
        return
    normalized_account = account.strip()
    if not normalized_account:
        return
    allowed = allowed_account_ids(allowed_accounts)
    if not allowed or normalized_account in allowed:
        return
    raise CliError(
        f"profile {profile_id} allows accounts: {format_allowed_values(allowed)}; "
        f"cannot use --account {normalized_account}"
    )


def select_allowed_home(
    *,
    profile_id: str,
    allowed_homes: Iterable[Path],
    home: Path | str,
) -> Path:
    normalized_home = Path(home).expanduser().resolve()
    allowed = {path: Path(path) for path in allowed_home_paths(allowed_homes)}
    if not allowed:
        raise CliError(f"profile {profile_id} does not allow home overrides")
    selected_home = allowed.get(str(normalized_home))
    if selected_home is None:
        raise CliError(
            f"profile {profile_id} allows homes: {format_allowed_values(allowed)}; "
            f"cannot use --home {normalized_home}"
        )
    return selected_home
