from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "agentos" / "chatlas"

# Provider-native discovery entry points: calling these reads a provider-native
# data home. Per the Provider.Home.Adapter [CT], only the adapter module may
# invoke them — every other Chatlas system answers from the depot or goes
# through the adapter.
_HOME_TOUCHING_ATTRIBUTES = (
    "discover_session_refs",
    "find_session_ref_by_id",
)

_ALLOWED = {"provider_home_adapter.py"}


def test_provider_home_contact_only_in_adapter_module():
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for attribute in _HOME_TOUCHING_ATTRIBUTES:
            if attribute in text:
                offenders.append(f"{path.relative_to(SRC_ROOT)}: {attribute}")
    assert not offenders, (
        "provider-home contact outside Provider.Home.Adapter:\n  "
        + "\n  ".join(offenders)
    )
