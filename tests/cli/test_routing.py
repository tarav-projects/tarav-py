"""Routes execute through the installed CLI, including SSH's shell boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest


CLI = Path(sys.executable).with_name("tarav")


def invoke(tmp_path: Path, arguments: list[str], routes=None, *, stdin="", bypass=False):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    if routes is not None:
        (home / "cli-routes.json").write_text(json.dumps({"routes": routes}))
    environment = {**os.environ, "TARAV_HOME": str(home)}
    environment.pop("TARAV_CLI_NO_ROUTE", None)
    if bypass:
        environment["TARAV_CLI_NO_ROUTE"] = "1"
    return subprocess.run([str(CLI), *arguments], input=stdin, text=True,
                          capture_output=True, env=environment, cwd=tmp_path, timeout=20)


# tarav.breadcrumb fba9609aff40
def test_route_preserves_arguments_streams_cwd_and_exit_status(tmp_path):
    script = ("import json,os,sys; print(json.dumps([sys.argv[1:],sys.stdin.read(),os.getcwd()])); "
              "print('child diagnostic',file=sys.stderr); sys.exit(17)")
    target = [sys.executable, "-c", script]
    arguments = ["two words", "", "'quoted'", "$(touch SHOULD_NOT_EXIST)", "a;b", "--flag"]
    result = invoke(tmp_path, ["chatlas", "future-vector", *arguments],
                    [{"command": ["chatlas", "future-vector"], "argv": target}], stdin="payload\n")
    assert result.returncode == 17
    assert json.loads(result.stdout) == [arguments, "payload\n", str(tmp_path)]
    assert result.stderr == f"Routed to: {shlex.join(target + arguments)}\nchild diagnostic\n"
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


# tarav.breadcrumb fb1acb351e97
def test_ssh_shaped_route_preserves_the_remote_argv(tmp_path, monkeypatch):
    scripts = tmp_path / "bin"
    scripts.mkdir()
    ssh = scripts / "ssh"
    ssh.write_text(f"#!{sys.executable}\nimport subprocess,sys\n"
                   "assert sys.argv[1]=='studio-pereiro'\n"
                   "assert len(sys.argv)==3\n"
                   "sys.exit(subprocess.call(['/bin/sh','-c',sys.argv[2]]))\n")
    remote = scripts / "tarav"
    remote.write_text(f"#!{sys.executable}\nimport json,os,sys\n"
                      "assert os.environ['TARAV_CLI_NO_ROUTE']=='1'\n"
                      "print(json.dumps(sys.argv[1:]))\n")
    ssh.chmod(0o755)
    remote.chmod(0o755)
    monkeypatch.setenv("PATH", str(scripts) + os.pathsep + os.environ["PATH"])
    arguments = ["query", "two words", "", "'", "$HOME", "$(touch INJECTED)", "x;y", "line\nbreak"]
    result = invoke(tmp_path, ["chatlas", "future-vector", *arguments], [{
        "command": ["chatlas", "future-vector"], "argv": ["ssh", "studio-pereiro"],
        "shell_command": ["env", "TARAV_CLI_NO_ROUTE=1", "tarav", "chatlas", "future-vector"],
    }])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["chatlas", "future-vector", *arguments]
    assert result.stderr.startswith("Routed to: ssh studio-pereiro ")
    assert not (tmp_path / "INJECTED").exists()


def test_most_specific_route_wins_and_unmatched_commands_stay_local(tmp_path):
    routes = [
        {"command": ["chatlas"], "argv": ["/usr/bin/printf", "broad"]},
        {"command": ["chatlas", "future-vector"], "argv": ["/usr/bin/printf", "specific"]},
    ]
    result = invoke(tmp_path, ["chatlas", "future-vector"], routes)
    assert (result.returncode, result.stdout) == (0, "specific")
    assert "Routed to:" in result.stderr
    result = invoke(tmp_path, ["--version"])
    assert result.returncode == 0 and result.stdout.strip() == "tarav 0.1.0"
    assert "Routed to:" not in result.stderr


def test_matching_uses_tokens_not_text_prefixes(tmp_path):
    result = invoke(tmp_path, ["chatlas-extra"], [
        {"command": ["chatlas"], "argv": ["/usr/bin/printf", "WRONG"]},
    ])
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert "Routed to:" not in result.stderr and result.stdout == ""


def test_no_route_file_preserves_local_cli_and_does_not_create_one(tmp_path):
    result = invoke(tmp_path, ["--version"])
    assert (result.returncode, result.stdout.strip()) == (0, "tarav 0.1.0")
    assert "Routed to:" not in result.stderr
    assert not (tmp_path / "home/cli-routes.json").exists()


@pytest.mark.parametrize("route", [
    {"command": [], "argv": ["echo"]},
    {"command": ["chatlas"], "argv": []},
    {"command": ["chatlas"], "argv": [123]},
    {"command": ["chatlas"], "argv": ["echo"], "typo": True},
    {"command": ["chatlas"], "argv": ["echo"], "shell_command": []},
    {"command": ["chatlas"], "argv": ["echo", "bad\x00arg"]},
    {"command": ["chatlas future-vector"], "argv": ["echo"]},
])
def test_malformed_routes_fail_before_running_a_command(tmp_path, route):
    result = invoke(tmp_path, ["--version"], [route])
    assert result.returncode == 1
    assert "cli-routes.json" in result.stderr and "error:" in result.stderr
    assert "Traceback" not in result.stderr and result.stdout == ""


def test_duplicate_matches_are_rejected(tmp_path):
    route = {"command": ["chatlas"], "argv": ["echo"]}
    result = invoke(tmp_path, ["--version"], [route, route])
    assert result.returncode == 1 and "duplicate" in result.stderr


def test_explicit_bypass_ignores_even_a_broken_config(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "cli-routes.json").write_text("{broken")
    failed = invoke(tmp_path, ["--version"])
    assert failed.returncode == 1 and "cli-routes.json" in failed.stderr
    result = invoke(tmp_path, ["--version"], bypass=True)
    assert (result.returncode, result.stdout.strip()) == (0, "tarav 0.1.0")
    assert "Routed to:" not in result.stderr


def test_self_route_runs_child_once_with_routing_bypassed(tmp_path):
    result = invoke(tmp_path, ["--version"], [
        {"command": ["--version"], "argv": [str(CLI), "--version"]},
    ])
    assert result.returncode == 0 and result.stdout.strip() == "tarav 0.1.0"
    assert result.stderr.count("Routed to:") == 1


def test_missing_executable_reports_failure_after_the_banner(tmp_path):
    result = invoke(tmp_path, ["remote-only"], [
        {"command": ["remote-only"], "argv": [str(tmp_path / "missing-command")]},
    ])
    assert result.returncode == 1
    assert result.stderr.startswith("Routed to:") and "error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_child_signal_has_shell_exit_status(tmp_path):
    result = invoke(tmp_path, ["remote-only"], [{
        "command": ["remote-only"],
        "argv": [sys.executable, "-c", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)"],
    }])
    assert result.returncode == 143
