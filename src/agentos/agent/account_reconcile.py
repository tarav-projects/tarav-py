from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AccountReconcileRequest:
    provider: str
    account: str | None = None
    home: Path | None = None
    start_path: Path | str = "."
    register_discovered: bool = True
    sync_homes: bool = True
    check: bool = False
    argv: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountReconcileAction:
    kind: str
    home: str | None = None
    account: str | None = None
    artifact_id: str | None = None
    message: str | None = None
    detail: dict[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind}
        if self.home is not None:
            payload["home"] = self.home
        if self.account is not None:
            payload["account"] = self.account
        if self.artifact_id is not None:
            payload["artifact_id"] = self.artifact_id
        if self.message is not None:
            payload["message"] = self.message
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class AccountReconcileWarning:
    kind: str
    home: str | None = None
    account: str | None = None
    message: str | None = None
    detail: dict[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind}
        if self.home is not None:
            payload["home"] = self.home
        if self.account is not None:
            payload["account"] = self.account
        if self.message is not None:
            payload["message"] = self.message
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class AccountReconcileResult:
    provider: str
    scanned_homes: tuple[dict[str, object], ...] = ()
    actions: tuple[AccountReconcileAction, ...] = ()
    warnings: tuple[AccountReconcileWarning, ...] = ()
    active_artifacts: tuple[dict[str, object], ...] = ()
    check: bool = False

    def summary(self) -> dict[str, object]:
        return {
            "status": "ok",
            "command": "agent accounts reconcile",
            "provider": self.provider,
            "check": self.check,
            "scanned_count": len(self.scanned_homes),
            "action_count": len(self.actions),
            "warning_count": len(self.warnings),
            "homes": list(self.scanned_homes),
            "actions": [action.summary() for action in self.actions],
            "warnings": [warning.summary() for warning in self.warnings],
            "active_artifacts": list(self.active_artifacts),
        }
