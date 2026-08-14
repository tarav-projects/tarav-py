"""The CLI must be a pure connector — no runtime logic, only `main`."""

from tarav.iterante import cli


def test_cli_holds_no_runtime_logic():
    leaked = [
        n for n in (
            "cmd_init", "cmd_submit", "cmd_request", "cmd_dev_step",
            "_resolve_token", "_run_turn", "_find_mission_dir",
            "_missions_roots", "render_frame", "_show",
        )
        if hasattr(cli, n)
    ]
    assert leaked == [], f"CLI leaked runtime logic: {leaked}"


def test_cli_exposes_main():
    assert callable(cli.main)
