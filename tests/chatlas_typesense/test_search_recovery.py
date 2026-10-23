"""Search stays responsive at the client boundary when the engine stalls."""

import json
import os
from pathlib import Path
import subprocess
import sys

from tarav.l2.chatlas_typesense import TypesenseConfig, TypesenseIndex


# tarav.breadcrumb 9326abafe1b7
def test_search_bypasses_unused_curation_stage(tmp_path, engine):
    config = TypesenseConfig(normal_model_root=tmp_path, api_key=engine["key"], url=engine["url"])
    result = TypesenseIndex(config).search(
        "writing concise documentation with one idea per line", side="user", limit=5,
    )
    assert result == {"found": 0, "search_time_ms": 2, "hits": []}
    query = engine["searches"][-1]
    assert query["query_by"] == ["text,embedding"]
    assert query["filter_by"] == ["side:=user"]
    assert query["enable_curations"] == ["false"]


# tarav.breadcrumb adfa38b46051
def test_cli_stalled_search_fails_promptly_despite_long_import_timeout(tmp_path, engine):
    engine["stall_search"] = True
    key = tmp_path / "api-key"
    key.write_text(engine["key"])
    config = tmp_path / "typesense.json"
    config.write_text(json.dumps({"url": engine["url"], "api_key_file": str(key), "timeout": 600}))
    env = {k: v for k, v in os.environ.items() if not k.startswith("TARAV_TYPESENSE_")}
    env.update(TARAV_HOME=str(tmp_path / "home"), TARAV_CLI_NO_ROUTE="1")
    try:
        result = subprocess.run(
            [str(Path(sys.executable).with_name("tarav")), "chatlas", "typesense", "search",
             "writing concise documentation with one idea per line", "--limit", "5", "--side", "user",
             "--config", str(config)],
            env=env, text=True, capture_output=True, timeout=25,
        )
    finally:
        engine["search_release"].set()
    assert result.returncode == 1
    assert "timed out after 15s" in result.stderr
    assert "Traceback" not in result.stderr and engine["key"] not in result.stderr
